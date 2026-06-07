"""Tests for the tenant-admin sidebar reorder UI + the underlying ordering contract."""
from __future__ import annotations

import pytest

from apps.tenants.models import Module, TenantModule


pytestmark = pytest.mark.django_db


def _active_codes_in_order(tenant):
    """Return tenant module codes in the same order the sidebar context processor sees them."""
    return list(
        TenantModule.objects
        .filter(tenant=tenant, disabled_at__isnull=True)
        .order_by("sort_order", "module__name")
        .values_list("module__code", flat=True)
    )


def _get_tm(tenant, code):
    return TenantModule.objects.get(tenant=tenant, module__code=code)


# ---------------------------------------------------------------------------
# Model-level contract
# ---------------------------------------------------------------------------

def test_next_sort_order_starts_at_10_when_empty(tenant_a):
    # tenant_a fixture activates a handful of modules already (core + hr/crm/sales),
    # so the "empty" case needs an isolated tenant.
    from apps.tenants.models import Tenant
    t = Tenant.objects.create(slug="empty-org", name="Empty Org")
    # The post_save signal attaches core modules with sort_order populated.
    # For testing the helper on a truly empty tenant, wipe the rows first.
    TenantModule.objects.filter(tenant=t).delete()
    assert TenantModule.next_sort_order_for(t) == 10


def test_next_sort_order_is_one_step_past_the_max(tenant_a):
    # tenant_a has multiple modules already (with sort_order set by the signal).
    current = TenantModule.objects.filter(tenant=tenant_a).order_by("-sort_order").first()
    assert current is not None
    assert TenantModule.next_sort_order_for(tenant_a) == current.sort_order + 10


def test_signal_assigns_distinct_sort_orders_on_tenant_creation(module_seed):
    """Newly created tenants must not have every core module tied at 0.

    Depends on ``module_seed`` so ``Module`` rows exist before the signal
    runs; otherwise the signal sees an empty catalogue and attaches nothing.
    """
    from apps.tenants.models import Tenant
    t = Tenant.objects.create(slug="fresh-tenant", name="Fresh")
    orders = list(
        TenantModule.objects.filter(tenant=t).values_list("sort_order", flat=True)
    )
    assert len(orders) > 1
    assert len(set(orders)) == len(orders), f"sort_orders are not distinct: {orders}"


# ---------------------------------------------------------------------------
# Reorder view
# ---------------------------------------------------------------------------

def test_reorder_view_renders_active_modules_in_order(client, tenant_a, user_a_admin):
    from django.utils.html import escape

    client.login(username="alpha-admin", password="pass")
    resp = client.get(f"/t/{tenant_a.slug}/admin/modules/reorder/")
    assert resp.status_code == 200
    # Every active module name appears in the rendered table. We compare
    # the HTML-escaped form because Django's template auto-escape turns
    # e.g. "Finance & Accounting" into "Finance &amp; Accounting".
    html = resp.content.decode()
    for code in _active_codes_in_order(tenant_a):
        m = Module.objects.get(code=code)
        assert escape(m.name) in html, (
            f"Module {m.name!r} (escaped: {escape(m.name)!r}) missing from reorder page"
        )


def test_reorder_view_denied_for_view_only_user(client, tenant_a, user_a_regular):
    """A non-admin tenant user should get 403 on the reorder page."""
    client.login(username="alpha-user", password="pass")
    resp = client.get(f"/t/{tenant_a.slug}/admin/modules/reorder/")
    assert resp.status_code in (302, 403)


def test_reorder_move_down_swaps_with_next_neighbour(client, tenant_a, user_a_admin):
    client.login(username="alpha-admin", password="pass")
    before = _active_codes_in_order(tenant_a)
    assert len(before) >= 2

    first_tm = _get_tm(tenant_a, before[0])

    # Move the top module down by one.
    resp = client.post(
        f"/t/{tenant_a.slug}/admin/modules/reorder/",
        {"tm_id": first_tm.id, "direction": "down"},
    )
    assert resp.status_code == 302

    after = _active_codes_in_order(tenant_a)
    # The first two slots have swapped; everything else is unchanged.
    assert after[0] == before[1]
    assert after[1] == before[0]
    assert after[2:] == before[2:]


def test_reorder_move_up_swaps_with_prev_neighbour(client, tenant_a, user_a_admin):
    client.login(username="alpha-admin", password="pass")
    before = _active_codes_in_order(tenant_a)
    assert len(before) >= 2

    last_tm = _get_tm(tenant_a, before[-1])

    resp = client.post(
        f"/t/{tenant_a.slug}/admin/modules/reorder/",
        {"tm_id": last_tm.id, "direction": "up"},
    )
    assert resp.status_code == 302

    after = _active_codes_in_order(tenant_a)
    # The last two slots have swapped; everything else is unchanged.
    assert after[-1] == before[-2]
    assert after[-2] == before[-1]
    assert after[:-2] == before[:-2]


def test_reorder_first_cannot_move_up(client, tenant_a, user_a_admin):
    """Trying to move the top item up is a no-op with an informational message."""
    client.login(username="alpha-admin", password="pass")
    before = _active_codes_in_order(tenant_a)
    first_tm = _get_tm(tenant_a, before[0])
    resp = client.post(
        f"/t/{tenant_a.slug}/admin/modules/reorder/",
        {"tm_id": first_tm.id, "direction": "up"},
    )
    assert resp.status_code == 302
    assert _active_codes_in_order(tenant_a) == before  # unchanged


def test_reorder_last_cannot_move_down(client, tenant_a, user_a_admin):
    client.login(username="alpha-admin", password="pass")
    before = _active_codes_in_order(tenant_a)
    last_tm = _get_tm(tenant_a, before[-1])
    resp = client.post(
        f"/t/{tenant_a.slug}/admin/modules/reorder/",
        {"tm_id": last_tm.id, "direction": "down"},
    )
    assert resp.status_code == 302
    assert _active_codes_in_order(tenant_a) == before  # unchanged


def test_reorder_invalid_direction_is_rejected(client, tenant_a, user_a_admin):
    client.login(username="alpha-admin", password="pass")
    before = _active_codes_in_order(tenant_a)
    first_tm = _get_tm(tenant_a, before[0])
    resp = client.post(
        f"/t/{tenant_a.slug}/admin/modules/reorder/",
        {"tm_id": first_tm.id, "direction": "sideways"},
    )
    assert resp.status_code == 302
    assert _active_codes_in_order(tenant_a) == before  # unchanged


def test_reorder_unknown_tm_id_is_rejected(client, tenant_a, user_a_admin):
    client.login(username="alpha-admin", password="pass")
    before = _active_codes_in_order(tenant_a)
    resp = client.post(
        f"/t/{tenant_a.slug}/admin/modules/reorder/",
        {"tm_id": 99999, "direction": "up"},
    )
    assert resp.status_code == 302
    assert _active_codes_in_order(tenant_a) == before  # unchanged


def test_reorder_handles_ties_by_renumbering(client, tenant_a, user_a_admin):
    """Two modules with identical sort_order (e.g. legacy data) get renumbered
    before the swap so the user-visible order is preserved deterministically.
    """
    # Force a tie on the top two modules.
    before = _active_codes_in_order(tenant_a)
    tm_a = _get_tm(tenant_a, before[0])
    tm_b = _get_tm(tenant_a, before[1])
    TenantModule.objects.filter(pk__in=[tm_a.pk, tm_b.pk]).update(sort_order=0)

    client.login(username="alpha-admin", password="pass")
    resp = client.post(
        f"/t/{tenant_a.slug}/admin/modules/reorder/",
        {"tm_id": tm_a.id, "direction": "down"},
    )
    assert resp.status_code == 302
    # After the renumber-then-swap, tm_b should now be in slot 0 and tm_a in slot 1.
    after = _active_codes_in_order(tenant_a)
    assert after[0] == before[1]
    assert after[1] == before[0]
    # Sort orders are now distinct.
    tm_a.refresh_from_db()
    tm_b.refresh_from_db()
    assert tm_a.sort_order != tm_b.sort_order


def test_reorder_writes_activity_log(client, tenant_a, user_a_admin):
    """Reorder action should land in the tenant's activity log."""
    from apps.activity.models import ActivityLog

    client.login(username="alpha-admin", password="pass")
    before_codes = _active_codes_in_order(tenant_a)
    first_tm = _get_tm(tenant_a, before_codes[0])
    client.post(
        f"/t/{tenant_a.slug}/admin/modules/reorder/",
        {"tm_id": first_tm.id, "direction": "down"},
    )
    assert ActivityLog.objects.filter(
        tenant=tenant_a, action="tenant_admin.module.reorder",
    ).exists()


def test_sidebar_menu_respects_sort_order(client, tenant_a, user_a_admin):
    """The sidebar menu (rendered into every tenant page) should show modules
    in the configured sort_order, not alphabetically.
    """
    from apps.core.context_processors import invalidate_menu_for_tenant

    client.login(username="alpha-admin", password="pass")
    # Move the last active module to the top.
    before = _active_codes_in_order(tenant_a)
    last_tm = _get_tm(tenant_a, before[-1])
    # Move it to the front by setting its sort_order to 1.
    TenantModule.objects.filter(pk=last_tm.pk).update(sort_order=1)
    invalidate_menu_for_tenant(tenant_a.id)

    resp = client.get(f"/t/{tenant_a.slug}/dashboard/")
    assert resp.status_code == 200
    html = resp.content.decode()

    # The relocated module's name must appear before any of the others
    # in the rendered HTML (the sidebar renders in order).
    relocated = Module.objects.get(code=before[-1])
    other_names = [
        Module.objects.get(code=c).name for c in before[:-1]
    ]
    relocated_pos = html.find(relocated.name)
    assert relocated_pos != -1
    for other in other_names:
        # The relocated module must come BEFORE every other module name
        # the first time both appear in the sidebar. We compare positions
        # to detect ordering changes without relying on exact HTML structure.
        other_pos = html.find(other)
        if other_pos == -1:
            continue
        assert relocated_pos < other_pos, (
            f"Sidebar order broken: '{relocated.name}' should appear "
            f"before '{other}', but found at positions {relocated_pos} vs {other_pos}"
        )
