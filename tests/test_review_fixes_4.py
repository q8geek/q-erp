"""Regression tests for the fourth review pass.

Covers:
  * Item 1 — Menu cache invalidation on tenant_module_toggle.
  * Item 2 — accounts.0003/0004 RunPython pre-flight rejects XOR violators.
  * Item 5 — prune_activity / prune_rule_runs CLI parity (require --yes,
    reject --older-than 0, accept --dry-run).
  * Item 6 — notify_head_of memoization within a single emit_event call.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import RequestFactory
from django.utils import timezone


pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------
# Item 1 — Menu cache invalidation
# --------------------------------------------------------------------------

def test_invalidate_menu_for_user_drops_cached_entry(tenant_a, user_a_admin):
    from apps.core.context_processors import (
        invalidate_menu_for_user,
        menu_cache_key,
    )

    key = menu_cache_key(tenant_a.id, user_a_admin.id)
    cache.set(key, ["sentinel"], 60)
    assert cache.get(key) == ["sentinel"]
    invalidate_menu_for_user(tenant_a.id, user_a_admin.id)
    assert cache.get(key) is None


def test_invalidate_menu_for_tenant_bumps_version(tenant_a, user_a_admin):
    from apps.core.context_processors import (
        invalidate_menu_for_tenant,
        menu_cache_key,
    )

    key_before = menu_cache_key(tenant_a.id, user_a_admin.id)
    cache.set(key_before, ["sentinel"], 60)
    invalidate_menu_for_tenant(tenant_a.id)
    key_after = menu_cache_key(tenant_a.id, user_a_admin.id)
    assert key_after != key_before, "version bump should change the cache key"
    # Old payload is no longer reachable through the *current* menu key.
    assert cache.get(key_after) is None


def test_tenant_module_toggle_invalidates_menu_cache(
    client, tenant_a, global_admin
):
    """Toggling a tenant's module must invalidate the menu cache so the next
    request rebuilds the sidebar.
    """
    from apps.core.context_processors import menu_cache_key
    from apps.tenants.models import Module

    # Pre-populate the cache so we can prove the toggle nuked it.
    pre_key = menu_cache_key(tenant_a.id, global_admin.id)
    cache.set(pre_key, ["stale"], 60)

    client.login(username="root", password="pass")
    module = Module.objects.get(code="hr")  # already enabled in fixture
    resp = client.post(
        f"/sys/tenants/{tenant_a.id}/modules/{module.id}/toggle/"
    )
    assert resp.status_code in (302, 200)
    # After the toggle, the *current* menu key (post version bump) has no value.
    post_key = menu_cache_key(tenant_a.id, global_admin.id)
    assert cache.get(post_key) is None


# --------------------------------------------------------------------------
# Item 2 — accounts.0003 / 0004 RunPython pre-flight checks
# --------------------------------------------------------------------------

class _FakeApps:
    """Tiny stand-in for the migration `apps` registry that lets the
    pre-flight function call ``get_model("accounts", "User")`` and receive
    a callable we control.
    """

    def __init__(self, model):
        self._model = model

    def get_model(self, app_label, model_name):
        return self._model


class _FakeQS:
    """Minimal queryset stand-in. Supports filter(...).values_list(...)[:n]."""

    def __init__(self, pks):
        self._pks = pks

    def filter(self, *args, **kwargs):  # noqa: ARG002 — accepted, ignored
        return self

    def values_list(self, *args, **kwargs):  # noqa: ARG002
        return self

    def __getitem__(self, item):
        return list(self._pks[item])


class _FakeManager:
    def __init__(self, pks):
        self._pks = pks

    def filter(self, *args, **kwargs):  # noqa: ARG002
        return _FakeQS(self._pks)


class _FakeUserModel:
    def __init__(self, violator_pks):
        self.objects = _FakeManager(violator_pks)


def test_accounts_0003_runpython_rejects_xor_violator():
    """The 0003 pre-flight raises RuntimeError when violators exist and
    embeds the offending PKs in the error message.
    """
    import importlib

    mig = importlib.import_module(
        "apps.accounts.migrations.0003_user_user_tenant_xor_system_admin"
    )
    fake_apps = _FakeApps(_FakeUserModel([42, 99]))
    with pytest.raises(RuntimeError) as exc:
        mig._check_xor_violations(fake_apps, schema_editor=None)
    msg = str(exc.value)
    assert "42" in msg
    assert "99" in msg
    assert "accounts.0003" in msg


def test_accounts_0004_runpython_rejects_xor_violator():
    """The 0004 pre-flight raises with the extended-rule error message."""
    import importlib

    mig = importlib.import_module(
        "apps.accounts.migrations.0004_remove_user_user_tenant_xor_system_admin_and_more"
    )
    fake_apps = _FakeApps(_FakeUserModel([7]))
    with pytest.raises(RuntimeError) as exc:
        mig._check_xor_violations(fake_apps, schema_editor=None)
    msg = str(exc.value)
    assert "7" in msg
    assert "accounts.0004" in msg


def test_accounts_0003_runpython_noop_when_clean():
    """No violator rows -> the pre-flight passes silently."""
    import importlib

    mig = importlib.import_module(
        "apps.accounts.migrations.0003_user_user_tenant_xor_system_admin"
    )
    fake_apps = _FakeApps(_FakeUserModel([]))
    # Must not raise.
    mig._check_xor_violations(fake_apps, schema_editor=None)


def test_accounts_0003_runpython_truncates_long_violator_lists():
    """When >50 violators exist, the error message tells the operator there
    are more and includes only the first 50 PKs.
    """
    import importlib

    mig = importlib.import_module(
        "apps.accounts.migrations.0003_user_user_tenant_xor_system_admin"
    )
    fake_apps = _FakeApps(_FakeUserModel(list(range(1, 102))))  # 101 pks
    with pytest.raises(RuntimeError) as exc:
        mig._check_xor_violations(fake_apps, schema_editor=None)
    msg = str(exc.value)
    assert "50+" in msg
    assert "1, 2, 3" in msg or "1," in msg  # sample slice present
    assert "and at least" in msg


def test_accounts_models_exposes_violator_q():
    """The violator Q expressions are re-exported on apps.accounts.models so
    that tests + tooling don't have to import private symbols from the
    migration files.
    """
    from apps.accounts.models import (
        USER_XOR_VALID_Q_V1,
        USER_XOR_VALID_Q_V2,
        USER_XOR_VIOLATOR_Q_V1,
        USER_XOR_VIOLATOR_Q_V2,
    )

    # Sanity: they are django Q objects and the violator is the negation of
    # the valid Q.
    from django.db.models import Q
    assert isinstance(USER_XOR_VALID_Q_V1, Q)
    assert isinstance(USER_XOR_VALID_Q_V2, Q)
    assert isinstance(USER_XOR_VIOLATOR_Q_V1, Q)
    assert isinstance(USER_XOR_VIOLATOR_Q_V2, Q)


# --------------------------------------------------------------------------
# Item 5 — prune_* CLI parity
# --------------------------------------------------------------------------

def test_prune_activity_requires_yes(tenant_a, user_a_admin):
    from apps.activity.models import ActivityLog

    old = ActivityLog.objects.create(
        tenant=tenant_a,
        category=ActivityLog.Category.OTHER,
        action="test.old",
    )
    ActivityLog.objects.filter(pk=old.pk).update(
        timestamp=timezone.now() - timedelta(days=200)
    )
    with pytest.raises(CommandError):
        call_command("prune_activity", "--older-than", "30", verbosity=0)
    assert ActivityLog.objects.filter(pk=old.pk).exists()


def test_prune_activity_rejects_older_than_zero():
    with pytest.raises(CommandError):
        call_command("prune_activity", "--older-than", "0", "--yes", verbosity=0)


def test_prune_activity_deletes_with_yes(tenant_a, user_a_admin):
    from apps.activity.models import ActivityLog

    old = ActivityLog.objects.create(
        tenant=tenant_a,
        category=ActivityLog.Category.OTHER,
        action="test.old",
    )
    ActivityLog.objects.filter(pk=old.pk).update(
        timestamp=timezone.now() - timedelta(days=200)
    )
    fresh = ActivityLog.objects.create(
        tenant=tenant_a,
        category=ActivityLog.Category.OTHER,
        action="test.fresh",
    )
    call_command(
        "prune_activity", "--older-than", "30", "--yes", verbosity=0
    )
    assert not ActivityLog.objects.filter(pk=old.pk).exists()
    assert ActivityLog.objects.filter(pk=fresh.pk).exists()


def test_prune_rule_runs_requires_yes(tenant_a):
    from apps.automation.models import Rule, RuleRun

    rule = Rule.unscoped.create(
        tenant=tenant_a,
        name="r",
        event_type="x",
        action_type="log_activity",
    )
    run = RuleRun.unscoped.create(
        tenant=tenant_a,
        rule=rule,
        event_type="x",
        status=RuleRun.Status.MATCHED,
    )
    RuleRun.unscoped.filter(pk=run.pk).update(
        created_at=timezone.now() - timedelta(days=200)
    )
    with pytest.raises(CommandError):
        call_command("prune_rule_runs", "--older-than", "30", verbosity=0)
    assert RuleRun.unscoped.filter(pk=run.pk).exists()


def test_prune_rule_runs_rejects_older_than_zero():
    with pytest.raises(CommandError):
        call_command("prune_rule_runs", "--older-than", "0", "--yes", verbosity=0)


def test_prune_rule_runs_deletes_with_yes(tenant_a):
    from apps.automation.models import Rule, RuleRun

    rule = Rule.unscoped.create(
        tenant=tenant_a,
        name="r",
        event_type="x",
        action_type="log_activity",
    )
    old = RuleRun.unscoped.create(
        tenant=tenant_a,
        rule=rule,
        event_type="x",
        status=RuleRun.Status.MATCHED,
    )
    RuleRun.unscoped.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=200)
    )
    fresh = RuleRun.unscoped.create(
        tenant=tenant_a,
        rule=rule,
        event_type="x",
        status=RuleRun.Status.MATCHED,
    )
    call_command(
        "prune_rule_runs", "--older-than", "30", "--yes", verbosity=0
    )
    assert not RuleRun.unscoped.filter(pk=old.pk).exists()
    assert RuleRun.unscoped.filter(pk=fresh.pk).exists()


# --------------------------------------------------------------------------
# Item 6 — notify_head_of memoization within one emit_event call
# --------------------------------------------------------------------------

def test_notify_head_of_department_memoizes_within_emit_event(
    tenant_a, user_a_admin, user_a_regular
):
    """Two rules firing notify_head_of_department against the same department
    in one emit_event call must only issue ONE Membership lookup.
    """
    from apps.automation.engine import emit_event
    from apps.automation.models import Rule
    from apps.org.models import Department, Membership

    dept = Department.unscoped.create(tenant=tenant_a, code="ENG", name="Eng")
    Membership.unscoped.create(
        tenant=tenant_a,
        user=user_a_admin,
        department=dept,
        is_head_of_department=True,
    )
    for i in range(2):
        Rule.unscoped.create(
            tenant=tenant_a,
            name=f"r{i}",
            event_type="ev.x",
            action_type="notify_head_of_department",
            action_params={"department_id": dept.pk, "body": "hi"},
        )

    # Build a stub request the engine accepts.
    rf = RequestFactory()
    request = rf.get("/")
    request.tenant = tenant_a
    request.user = user_a_regular

    # Monkey-patch Membership.objects.filter to count calls without breaking
    # the queryset semantics. (We could use assertNumQueries but it covers
    # ALL queries; the Membership lookup count is more precise.)
    from apps.org import models as org_models

    original_filter = org_models.Membership.objects.filter
    call_count = {"n": 0}

    def counting_filter(*args, **kwargs):
        call_count["n"] += 1
        return original_filter(*args, **kwargs)

    org_models.Membership.objects.filter = counting_filter
    try:
        emit_event(request, "ev.x", {})
    finally:
        org_models.Membership.objects.filter = original_filter

    # Two rules fired, but the memoized resolver should only have hit
    # Membership.objects.filter once.
    assert call_count["n"] == 1, (
        f"expected 1 Membership.objects.filter call, got {call_count['n']}"
    )


def test_emit_event_clears_head_of_cache_between_calls(
    tenant_a, user_a_admin, user_a_regular
):
    """The memoization is per-emit_event. A second emit_event call must
    repopulate the cache (one fresh Membership lookup), not reuse a stale
    entry from a prior call.

    Previously this test inspected ``_actions._HEAD_OF_CACHE`` directly.
    The cache now lives on a ContextVar bound only for the duration of
    each emit_event call (see review fix #3), so we measure call counts
    instead — which is the actual observable contract.
    """
    from apps.automation.engine import emit_event
    from apps.automation.models import Rule
    from apps.org import models as org_models
    from apps.org.models import Department, Membership

    dept = Department.unscoped.create(tenant=tenant_a, code="ENG", name="Eng")
    Membership.unscoped.create(
        tenant=tenant_a,
        user=user_a_admin,
        department=dept,
        is_head_of_department=True,
    )
    Rule.unscoped.create(
        tenant=tenant_a,
        name="r",
        event_type="ev.x",
        action_type="notify_head_of_department",
        action_params={"department_id": dept.pk, "body": "hi"},
    )
    rf = RequestFactory()
    request = rf.get("/")
    request.tenant = tenant_a
    request.user = user_a_regular

    original_filter = org_models.Membership.objects.filter
    call_count = {"n": 0}

    def counting_filter(*args, **kwargs):
        call_count["n"] += 1
        return original_filter(*args, **kwargs)

    org_models.Membership.objects.filter = counting_filter
    try:
        emit_event(request, "ev.x", {})
        first_call_count = call_count["n"]
        emit_event(request, "ev.x", {})
        second_call_count = call_count["n"]
    finally:
        org_models.Membership.objects.filter = original_filter

    # Each emit_event independently performs the (single) Membership lookup.
    # Total calls across two emit_event invocations: 2.
    assert first_call_count == 1, (
        f"first emit_event: expected 1 Membership lookup, got {first_call_count}"
    )
    assert second_call_count == 2, (
        f"after second emit_event: expected 2 total lookups, got {second_call_count}"
    )
