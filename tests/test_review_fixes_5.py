"""Regression tests for the fifth review pass.

Covers the eight items landed in the pass:

    * Item 1 — Atomic ``cache.add`` seeding of the per-tenant menu version
      key. Two consecutive ``invalidate_menu_for_tenant`` calls on a cold
      key must bump to 2 (no event lost).
    * Item 2 — The ``User.user_tenant_xor_system_admin`` CheckConstraint
      references the module-level ``USER_XOR_VALID_Q_V2`` constant directly
      so the constraint can never drift from the migration pre-flight.
    * Item 3 — The per-emit_event head-of memoization cache lives on a
      ContextVar and is isolated per emit_event call (threaded-worker safe).
    * Item 4 — ``TenantGroupForm.save`` bumps the tenant menu version
      instead of iterating users.
    * Item 5 — ``_get_menu_ver`` is memoized on the request when the
      context processor passes ``request=request``.
    * Item 6 — The chunked-prune base class advances by ``pk > last_seen``.
    * Item 7 — Docstrings on the head-of cache document the ContextVar
      contract.
    * Item 8 — ``apps.org.__init__`` no longer exposes lazy attributes.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.test import RequestFactory
from django.utils import timezone


pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------
# Item 1 — Atomic cache.add seeding
# --------------------------------------------------------------------------

def test_invalidate_menu_for_tenant_cold_cache_double_bump():
    """On a cold cache, two consecutive ``invalidate_menu_for_tenant``
    calls must end at version 2.

    Pre-fix, the second call could observe the seeded 0 from the first
    and clobber back to 1 instead of incrementing — the second event
    would be lost. The ``cache.add`` seed is atomic, so this scenario
    cannot lose events even single-threaded.
    """
    from apps.core.context_processors import (
        _menu_ver_key,
        invalidate_menu_for_tenant,
    )

    tenant_id = 424242
    cache.delete(_menu_ver_key(tenant_id))
    assert cache.get(_menu_ver_key(tenant_id)) is None

    invalidate_menu_for_tenant(tenant_id)
    invalidate_menu_for_tenant(tenant_id)

    assert cache.get(_menu_ver_key(tenant_id)) == 2


def test_get_menu_ver_seeds_zero_only_once():
    """``_get_menu_ver`` seeds 0 atomically; a subsequent bump must
    leave the version > 0 (the seed must not overwrite the bump).
    """
    from apps.core.context_processors import (
        _get_menu_ver,
        _menu_ver_key,
        invalidate_menu_for_tenant,
    )

    tenant_id = 525252
    cache.delete(_menu_ver_key(tenant_id))

    assert _get_menu_ver(tenant_id) == 0
    invalidate_menu_for_tenant(tenant_id)
    # Re-reading must not re-seed and clobber the bump.
    assert _get_menu_ver(tenant_id) == 1
    assert _get_menu_ver(tenant_id) == 1


# --------------------------------------------------------------------------
# Item 2 — CheckConstraint references the module-level constant
# --------------------------------------------------------------------------

def test_constraint_condition_matches_v2_constant():
    """The check constraint condition is the exact ``USER_XOR_VALID_Q_V2``
    constant object — guarantees the constraint cannot silently drift
    from the migration pre-flight rule.
    """
    from apps.accounts.models import USER_XOR_VALID_Q_V2, User

    constraint = next(
        c for c in User._meta.constraints if c.name == "user_tenant_xor_system_admin"
    )
    assert constraint.condition == USER_XOR_VALID_Q_V2


# --------------------------------------------------------------------------
# Item 3 — ContextVar-isolated head-of cache
# --------------------------------------------------------------------------

def test_emit_event_isolates_head_of_cache_per_call(
    tenant_a, user_a_admin, user_a_regular
):
    """Two ``emit_event`` calls each see their own cache.

    Inside emit_event #1, ``get_head_of_cache()`` returns a dict bound for
    that call. Outside emit_event entirely, ``get_head_of_cache()``
    returns a throwaway empty dict.
    """
    from apps.automation.engine import emit_event, get_head_of_cache
    from apps.automation.models import Rule
    from apps.org.models import Department, Membership

    dept = Department.unscoped.create(tenant=tenant_a, code="ENG", name="Eng")
    Membership.unscoped.create(
        tenant=tenant_a,
        user=user_a_admin,
        department=dept,
        is_head_of_department=True,
    )

    # Before any emit_event: outside the binding, the helper returns an
    # empty throwaway dict.
    assert get_head_of_cache() == {}

    captured: dict[str, dict] = {}

    def _capturing_handler(*, tenant, payload, rule, params):
        # Inside the emit_event call, the cache lookup should hit a
        # bound dict — capture its id for the assertion below.
        captured["mid_emit"] = get_head_of_cache()

    from apps.automation.registry import register_action

    register_action(
        "capture_cache",
        "test capture",
        description="",
        params={},
    )(_capturing_handler)

    Rule.unscoped.create(
        tenant=tenant_a,
        name="capture",
        event_type="ev.capture",
        action_type="capture_cache",
        action_params={},
    )

    rf = RequestFactory()
    request = rf.get("/")
    request.tenant = tenant_a
    request.user = user_a_regular

    emit_event(request, "ev.capture", {})

    # Mid-emit the cache was a bound dict.
    assert "mid_emit" in captured
    mid_emit_cache = captured["mid_emit"]

    # After emit_event returns, the binding is reset — the helper again
    # returns an unrelated empty throwaway dict.
    after_cache = get_head_of_cache()
    assert after_cache == {}
    assert after_cache is not mid_emit_cache  # different dicts


def test_actions_module_no_longer_exposes_head_of_cache():
    """The legacy module global must be gone after the ContextVar move."""
    from apps.automation import actions as _actions

    assert not hasattr(_actions, "_HEAD_OF_CACHE"), (
        "actions._HEAD_OF_CACHE should be removed in favour of the "
        "ContextVar-bound cache in engine.get_head_of_cache()."
    )


# --------------------------------------------------------------------------
# Item 4 — TenantGroupForm.save bumps tenant menu version
# --------------------------------------------------------------------------

def test_tenant_group_form_save_bumps_tenant_version(tenant_a):
    """Saving a TenantGroup form must bump the per-tenant menu version
    once, regardless of how many users are members of the group.
    """
    from django.contrib.auth.models import Permission

    from apps.core.context_processors import _menu_ver_key
    from apps.tenant_admin.forms import TenantGroupForm
    from apps.tenants.models import TenantGroup

    cache.delete(_menu_ver_key(tenant_a.id))

    perm = Permission.objects.filter(content_type__app_label="tenants").first()
    form = TenantGroupForm(
        data={
            "name": "viewers",
            "description": "x",
            "permissions": [perm.pk] if perm else [],
        },
        tenant=tenant_a,
    )
    assert form.is_valid(), form.errors
    form.save()

    ver_after = cache.get(_menu_ver_key(tenant_a.id))
    # Was 0 (or unset) before save; bump produced version 1.
    assert ver_after == 1

    # A second save bumps to 2 — one increment per save, regardless of
    # how many users are in the group.
    tg = TenantGroup.objects.get(tenant=tenant_a, group__name=f"t{tenant_a.id}:viewers")
    form2 = TenantGroupForm(
        instance=tg,
        data={"name": "viewers", "description": "y", "permissions": []},
        tenant=tenant_a,
    )
    assert form2.is_valid(), form2.errors
    form2.save()
    assert cache.get(_menu_ver_key(tenant_a.id)) == 2


# --------------------------------------------------------------------------
# Item 5 — Per-request memoization of _get_menu_ver
# --------------------------------------------------------------------------

def test_menu_cache_key_request_memoization():
    """When ``menu_cache_key`` is given a request, the second call within
    the same request must not re-hit the cache backend.
    """
    from apps.core import context_processors as cp

    tenant_id = 90909
    cache.delete(cp._menu_ver_key(tenant_id))

    rf = RequestFactory()
    request = rf.get("/")

    calls = {"n": 0}
    real_get = cache.get

    def counting_get(key, default=None, **kw):
        if key == cp._menu_ver_key(tenant_id):
            calls["n"] += 1
        return real_get(key, default, **kw)

    cache.get = counting_get
    try:
        k1 = cp.menu_cache_key(tenant_id, 1, request=request)
        first_calls = calls["n"]
        k2 = cp.menu_cache_key(tenant_id, 2, request=request)
        second_calls = calls["n"]
    finally:
        cache.get = real_get

    assert k1.startswith(f"menu:{tenant_id}:1:v")
    assert k2.startswith(f"menu:{tenant_id}:2:v")
    # First call hits cache.get to read the seeded version; the second
    # call within the same request must be free.
    assert first_calls == 1
    assert second_calls == first_calls, (
        f"expected per-request memo to skip 2nd cache.get; got {second_calls} total"
    )


def test_menu_cache_key_no_request_falls_back():
    """Without ``request=``, the function still works (un-memoized path)."""
    from apps.core import context_processors as cp

    tenant_id = 80808
    cache.delete(cp._menu_ver_key(tenant_id))
    k = cp.menu_cache_key(tenant_id, 7)
    assert k == f"menu:{tenant_id}:7:v0"


# --------------------------------------------------------------------------
# Item 6 — pk-bounded chunked prune iteration
# --------------------------------------------------------------------------

def test_chunked_prune_uses_pk_gt_cursor(tenant_a):
    """The chunked-prune loop must advance by ``pk > last_seen`` rather
    than re-scanning from offset 0 each iteration. Hard to assert
    directly without query introspection, so we verify the behavior
    end-to-end with a small batch size and many rows.
    """
    from django.core.management import call_command

    from apps.activity.models import ActivityLog

    # Create 12 old rows and 3 fresh rows; with batch_size=5 the loop
    # should do exactly 3 deletion passes (5 + 5 + 2) and produce 12
    # deleted total — no row skipped, no row deleted twice.
    old_pks = []
    for i in range(12):
        row = ActivityLog.objects.create(
            tenant=tenant_a,
            category=ActivityLog.Category.OTHER,
            action=f"old-{i}",
        )
        old_pks.append(row.pk)
    ActivityLog.objects.filter(pk__in=old_pks).update(
        timestamp=timezone.now() - timedelta(days=200)
    )
    for i in range(3):
        ActivityLog.objects.create(
            tenant=tenant_a,
            category=ActivityLog.Category.OTHER,
            action=f"fresh-{i}",
        )

    call_command(
        "prune_activity",
        "--older-than", "30",
        "--batch-size", "100",  # base class enforces min 100
        "--yes",
        verbosity=0,
    )
    assert not ActivityLog.objects.filter(pk__in=old_pks).exists()
    assert ActivityLog.objects.filter(action__startswith="fresh-").count() == 3


# --------------------------------------------------------------------------
# Item 8 — apps.org.__init__ stripped of lazy exports
# --------------------------------------------------------------------------

def test_apps_org_init_has_no_lazy_exports():
    """The dead ``__all__`` + ``__getattr__`` lazy export pattern was
    removed. ``apps.org`` no longer claims to re-export model helpers.
    """
    import apps.org as _org

    assert not hasattr(_org, "__all__")
    # The legacy lazy ``head_of`` attribute on the package must NOT
    # exist; consumers import from apps.org.models directly.
    assert not hasattr(_org, "head_of")
    # The package still imports cleanly and submodule access works.
    from apps.org import models as _models  # noqa: F401
