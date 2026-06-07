"""UI-gating regression: view-only users must not see manage buttons.

These tests load list/detail pages as both a view-only and a manage-capable
user and assert the rendered HTML for the expected buttons. Two layers must
agree:

  * Server-side enforcement (already covered by other tests via
    ``enforce_tenant_manage``).
  * Template-side hiding (this file).

The pattern relies on ``apps.core.templatetags.qerp_extras.can_manage_module``.
"""
from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, Permission

from apps.finance.models import Account
from apps.tenants.models import TenantGroup


pytestmark = pytest.mark.django_db


def _give_view_only(user, tenant, module_codes):
    """Wire `user` up as a view-only user on the given modules in `tenant`."""
    group_name = f"t{tenant.id}:viewers"
    group, _ = Group.objects.get_or_create(name=group_name)
    TenantGroup.objects.get_or_create(tenant=tenant, group=group)
    perms = Permission.objects.filter(
        content_type__app_label__in=module_codes,
        codename__startswith="view_",
    )
    group.permissions.add(*perms)
    user.groups.add(group)


def test_view_only_user_sees_no_new_or_edit_buttons_in_list(
    client, tenant_a, user_a_regular
):
    """View-only finance user reaches the list but should see no manage buttons."""
    _give_view_only(user_a_regular, tenant_a, ["finance"])
    # Seed one row so the row-level action cells render
    Account.objects.create(
        tenant=tenant_a, code="1000", name="Cash", type=Account.Type.ASSET
    )
    client.login(username="alpha-user", password="pass")

    resp = client.get(f"/t/{tenant_a.slug}/finance/account/")
    assert resp.status_code == 200
    html = resp.content.decode()
    # The "+ New" button is gated
    assert "New account" not in html
    # The "view" button still appears
    assert ">view<" in html
    # The "edit"/"del" buttons are gated
    assert ">edit<" not in html
    assert ">del<" not in html


def test_manager_sees_new_edit_delete_buttons(client, tenant_a, user_a_admin):
    """Tenant admin sees every action button."""
    Account.objects.create(
        tenant=tenant_a, code="1000", name="Cash", type=Account.Type.ASSET
    )
    client.login(username="alpha-admin", password="pass")

    resp = client.get(f"/t/{tenant_a.slug}/finance/account/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "New account" in html
    assert ">edit<" in html
    assert ">del<" in html


def test_view_only_user_detail_page_hides_edit_delete(
    client, tenant_a, user_a_regular
):
    _give_view_only(user_a_regular, tenant_a, ["finance"])
    acc = Account.objects.create(
        tenant=tenant_a, code="2000", name="AR", type=Account.Type.ASSET
    )
    client.login(username="alpha-user", password="pass")

    resp = client.get(f"/t/{tenant_a.slug}/finance/account/{acc.pk}/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert ">edit<" not in html
    assert ">delete<" not in html
    # Back button still there
    assert "back" in html


def test_view_only_user_does_not_see_tenant_admin_sidebar(
    client, tenant_a, user_a_regular
):
    """The 'Tenant Admin' sidebar section is gated by perms.tenants.manage_tenant."""
    _give_view_only(user_a_regular, tenant_a, ["finance"])
    client.login(username="alpha-user", password="pass")

    resp = client.get(f"/t/{tenant_a.slug}/dashboard/")
    assert resp.status_code == 200
    html = resp.content.decode()
    # The sidebar section header should be gated out.
    assert "Tenant Admin" not in html
    # And so should the admin URLs.
    assert f"/t/{tenant_a.slug}/admin/users/" not in html
    assert f"/t/{tenant_a.slug}/admin/settings/" not in html


def test_admin_sees_tenant_admin_sidebar(client, tenant_a, user_a_admin):
    client.login(username="alpha-admin", password="pass")
    resp = client.get(f"/t/{tenant_a.slug}/dashboard/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Tenant Admin" in html
    assert f"/t/{tenant_a.slug}/admin/users/" in html


def test_user_list_hides_self_delete_button(client, tenant_a, user_a_admin):
    """An admin viewing the user list shouldn't see a delete button on their own row."""
    client.login(username="alpha-admin", password="pass")
    resp = client.get(f"/t/{tenant_a.slug}/admin/users/")
    assert resp.status_code == 200
    html = resp.content.decode()
    # Their own row's del button should be absent. The admin's username
    # (alpha-admin) appears once in the row; we rely on the template
    # ``{% if u.id != user.id %}`` guard wrapping the del anchor for that
    # row only. We assert by counting: there's at least one user shown
    # (themselves), so if no del anchors render at all the guard worked.
    # Other tenant users may exist and would still show delete; ensure the
    # admin's own row text appears and there's no orphan delete anchor on
    # it. Easiest check: every del button URL we see does NOT point at the
    # admin's pk.
    import re
    pattern = re.compile(
        rf'/t/{tenant_a.slug}/admin/users/(\d+)/delete/'
    )
    bad = [m for m in pattern.findall(html) if int(m) == user_a_admin.pk]
    assert bad == [], f"Admin's own delete URL leaked into the user list: {bad}"


def test_template_tag_can_manage_module():
    """Direct unit test of the filter."""
    from django.contrib.auth.models import AnonymousUser
    from apps.core.templatetags.qerp_extras import can_manage_module

    assert can_manage_module(AnonymousUser(), "finance") is False
    assert can_manage_module(None, "finance") is False
