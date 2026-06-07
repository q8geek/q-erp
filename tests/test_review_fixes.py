"""Regression tests for findings landed from the second review pass."""
from __future__ import annotations

import pytest
from django.urls import reverse


pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------
# CRITICAL: anonymous user enumeration on /messaging/new/
# --------------------------------------------------------------------------

def test_anonymous_cannot_reach_messaging_new_direct(client, tenant_a, user_a_regular):
    """Previously the form's recipient <select> leaked every active user."""
    resp = client.get(f"/t/{tenant_a.slug}/messaging/new/")
    assert resp.status_code in (302, 403)  # redirected to login or denied
    # And the rendered HTML must NOT include the user's identifier.
    if resp.status_code == 200:
        assert user_a_regular.email.encode() not in resp.content
        assert user_a_regular.username.encode() not in resp.content


def test_anonymous_cannot_reach_thread_detail(client, tenant_a):
    resp = client.get(f"/t/{tenant_a.slug}/messaging/threads/1/")
    assert resp.status_code in (302, 403, 404)


# --------------------------------------------------------------------------
# CRITICAL: NOTIFICATION threads reject POST replies server-side
# --------------------------------------------------------------------------

def test_notification_thread_post_reply_is_forbidden(client, tenant_a, user_a_admin, user_a_regular):
    from apps.messaging.models import send_notification

    msg = send_notification(tenant=tenant_a, recipient=user_a_admin, body="ping")
    client.login(username="alpha-admin", password="pass")
    resp = client.post(
        f"/t/{tenant_a.slug}/messaging/threads/{msg.thread_id}/",
        {"body": "I should not be able to reply"},
    )
    assert resp.status_code == 403
    # And the message count is unchanged.
    from apps.messaging.models import Message
    assert Message.unscoped.filter(thread_id=msg.thread_id).count() == 1


# --------------------------------------------------------------------------
# CRITICAL: write-gate helper rejects disabled users
# --------------------------------------------------------------------------

def test_disabled_user_blocked_from_crud_write(client, tenant_a, user_a_admin):
    """A user marked is_disabled=True must NOT be able to create/edit/delete
    via the generic CRUD scaffold, even if they hold the required permission.
    Previously the write paths only checked `has_perm` and let disabled users
    through.
    """
    user_a_admin.is_disabled = True
    user_a_admin.save(update_fields=["is_disabled"])
    client.login(username="alpha-admin", password="pass")
    resp = client.post(
        f"/t/{tenant_a.slug}/finance/account/new/",
        {"code": "9999", "name": "Should fail", "type": "ASSET", "is_active": "on"},
    )
    assert resp.status_code in (302, 403)  # 302 = login redirect, 403 = denied
    from apps.finance.models import Account
    assert not Account.unscoped.filter(tenant=tenant_a, code="9999").exists()


def test_inactive_user_blocked_from_crud_write(client, tenant_a, user_a_admin):
    user_a_admin.is_active = False
    user_a_admin.save(update_fields=["is_active"])
    client.login(username="alpha-admin", password="pass")
    resp = client.post(
        f"/t/{tenant_a.slug}/finance/account/new/",
        {"code": "9998", "name": "Should fail", "type": "ASSET", "is_active": "on"},
    )
    # Login redirects authenticated check, so we get a 302 to login here.
    assert resp.status_code in (302, 403)
    from apps.finance.models import Account
    assert not Account.unscoped.filter(tenant=tenant_a, code="9998").exists()


# --------------------------------------------------------------------------
# Back-fill: sync_modules attaches new core modules to existing tenants
# --------------------------------------------------------------------------

def test_sync_modules_backfills_core_to_existing_tenants(tenant_a):
    """Imagine `org` is newly promoted to core. Strip it from tenant_a, then
    re-run sync_modules and assert it gets re-attached automatically.
    """
    from apps.tenants.models import Module, TenantModule
    org = Module.objects.get(code="org")
    TenantModule.objects.filter(tenant=tenant_a, module=org).delete()
    assert not TenantModule.objects.filter(tenant=tenant_a, module=org).exists()
    from django.core.management import call_command
    call_command("sync_modules", verbosity=0)
    assert TenantModule.objects.filter(tenant=tenant_a, module=org).exists()


# --------------------------------------------------------------------------
# Automation: lifecycle events (created / updated / deleted) fire
# --------------------------------------------------------------------------

def test_automation_emits_created_then_updated_then_deleted(
    client, tenant_a, user_a_admin, user_a_regular
):
    from apps.automation.models import Rule, RuleRun

    Rule.unscoped.create(
        tenant=tenant_a,
        name="watch creates",
        event_type="inventory.item.created",
        action_type="send_notification",
        action_params={"recipient_user_id": user_a_admin.pk, "body": "created {sku}"},
    )
    Rule.unscoped.create(
        tenant=tenant_a,
        name="watch updates",
        event_type="inventory.item.updated",
        action_type="send_notification",
        action_params={"recipient_user_id": user_a_admin.pk, "body": "updated {sku}"},
    )
    Rule.unscoped.create(
        tenant=tenant_a,
        name="watch deletes",
        event_type="inventory.item.deleted",
        action_type="send_notification",
        action_params={"recipient_user_id": user_a_admin.pk, "body": "deleted"},
    )

    client.login(username="alpha-admin", password="pass")
    # Create
    resp = client.post(
        f"/t/{tenant_a.slug}/inventory/item/new/",
        {"sku": "LF-1", "name": "Lifecycle item", "uom": "EA", "is_active": "on"},
    )
    assert resp.status_code == 302
    # Update
    from apps.inventory.models import Item
    item = Item.unscoped.get(tenant=tenant_a, sku="LF-1")
    resp = client.post(
        f"/t/{tenant_a.slug}/inventory/item/{item.pk}/edit/",
        {"sku": "LF-1", "name": "renamed", "uom": "EA", "is_active": "on"},
    )
    assert resp.status_code == 302
    # Delete
    resp = client.post(f"/t/{tenant_a.slug}/inventory/item/{item.pk}/delete/")
    assert resp.status_code == 302

    statuses = list(RuleRun.unscoped.filter(tenant=tenant_a).values_list("event_type", flat=True))
    assert "inventory.item.created" in statuses
    assert "inventory.item.updated" in statuses
    assert "inventory.item.deleted" in statuses


# --------------------------------------------------------------------------
# Engine: payload normalization at the engine boundary
# --------------------------------------------------------------------------

def test_engine_coerces_decimals_and_dates():
    from datetime import date
    from decimal import Decimal

    from apps.automation.engine import coerce_for_event

    out = coerce_for_event(
        {
            "amount": Decimal("12.50"),
            "when": date(2026, 6, 1),
            "nested": {"d": Decimal("0.01")},
            "list": [Decimal("1"), "x"],
        }
    )
    assert out == {
        "amount": "12.50",
        "when": "2026-06-01",
        "nested": {"d": "0.01"},
        "list": ["1", "x"],
    }


# --------------------------------------------------------------------------
# TicketCategory.default_assignee is applied when creating a ticket
# --------------------------------------------------------------------------

def test_ticket_inherits_default_assignee_from_category(tenant_a, user_a_admin):
    from apps.support_tickets.models import Ticket, TicketCategory

    cat = TicketCategory.unscoped.create(
        tenant=tenant_a, code="GEN", name="General", default_assignee=user_a_admin
    )
    t = Ticket.unscoped.create(
        tenant=tenant_a,
        number="T-1",
        subject="Help",
        category=cat,
    )
    assert t.assignee_id == user_a_admin.id


def test_ticket_explicit_assignee_overrides_default(tenant_a, user_a_admin, user_a_regular):
    from apps.support_tickets.models import Ticket, TicketCategory

    cat = TicketCategory.unscoped.create(
        tenant=tenant_a, code="GEN", name="General", default_assignee=user_a_admin
    )
    t = Ticket.unscoped.create(
        tenant=tenant_a,
        number="T-2",
        subject="Pick me",
        category=cat,
        assignee=user_a_regular,
    )
    assert t.assignee_id == user_a_regular.id


# --------------------------------------------------------------------------
# unread_count is computed in a single query and memoized on the request
# --------------------------------------------------------------------------

def test_unread_count_memoized_on_request(rf, tenant_a, user_a_admin, user_a_regular):
    """The aggregate query must be cached on the request so two callers
    (inbox + statistics widget) don't re-issue it."""
    from apps.messaging.models import send_direct_message
    from apps.messaging.views import unread_count

    send_direct_message(tenant=tenant_a, sender=user_a_regular, recipient=user_a_admin, body="x")
    req = rf.get("/")
    req.tenant = tenant_a
    req.user = user_a_admin
    # First call computes
    n = unread_count(req)
    # Override the participants queryset to a sentinel; cached value should win.
    req._qerp_unread_count = 9999
    assert unread_count(req) == 9999
    # The first call returned the real count (>=1)
    assert n >= 1


@pytest.fixture
def rf():
    from django.test import RequestFactory
    return RequestFactory()


# --------------------------------------------------------------------------
# Lifecycle ordering: on a single create, both `.created` and `.saved`
# rules fire — and `.created` runs first.
# --------------------------------------------------------------------------

def test_lifecycle_created_and_saved_both_fire_on_create(
    client, tenant_a, user_a_admin
):
    """A rule on `.created` AND a rule on `.saved` must both match a single
    create. The view emits the specific event before the generic one, so
    `.created` must appear earlier (lower pk) in RuleRun history.
    """
    from apps.automation.models import Rule, RuleRun

    Rule.unscoped.create(
        tenant=tenant_a,
        name="created-watcher",
        event_type="inventory.item.created",
        action_type="log_activity",
        action_params={"action": "lf.created", "note": "{sku}"},
    )
    Rule.unscoped.create(
        tenant=tenant_a,
        name="saved-watcher",
        event_type="inventory.item.saved",
        action_type="log_activity",
        action_params={"action": "lf.saved", "note": "{sku}"},
    )

    client.login(username="alpha-admin", password="pass")
    resp = client.post(
        f"/t/{tenant_a.slug}/inventory/item/new/",
        {"sku": "LF-2", "name": "lifecycle pair", "uom": "EA", "is_active": "on"},
    )
    assert resp.status_code == 302

    runs = list(
        RuleRun.unscoped.filter(tenant=tenant_a).order_by("pk").values_list(
            "event_type", flat=True
        )
    )
    # Both events fired
    assert "inventory.item.created" in runs
    assert "inventory.item.saved" in runs
    # And .created was emitted before .saved
    assert runs.index("inventory.item.created") < runs.index("inventory.item.saved")


def test_lifecycle_updated_and_saved_both_fire_on_update(
    client, tenant_a, user_a_admin
):
    from apps.automation.models import Rule, RuleRun
    from apps.inventory.models import Item

    Rule.unscoped.create(
        tenant=tenant_a,
        name="updated-watcher",
        event_type="inventory.item.updated",
        action_type="log_activity",
        action_params={"action": "lf.updated", "note": "{sku}"},
    )
    Rule.unscoped.create(
        tenant=tenant_a,
        name="saved-watcher-2",
        event_type="inventory.item.saved",
        action_type="log_activity",
        action_params={"action": "lf.saved", "note": "{sku}"},
    )

    # Create the item directly (bypassing the create rule path).
    item = Item.unscoped.create(tenant=tenant_a, sku="LF-3", name="x", uom="EA")

    client.login(username="alpha-admin", password="pass")
    resp = client.post(
        f"/t/{tenant_a.slug}/inventory/item/{item.pk}/edit/",
        {"sku": "LF-3", "name": "renamed", "uom": "EA", "is_active": "on"},
    )
    assert resp.status_code == 302

    runs = list(
        RuleRun.unscoped.filter(tenant=tenant_a).order_by("pk").values_list(
            "event_type", flat=True
        )
    )
    assert "inventory.item.updated" in runs
    assert "inventory.item.saved" in runs
    assert runs.index("inventory.item.updated") < runs.index("inventory.item.saved")
