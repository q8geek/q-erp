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


def _has_url(html: str, url_path: str) -> bool:
    """Test whether a given URL is anchored in the HTML.

    Robust to UI-button label changes (text vs icon vs emoji): we only
    care that the user has (or hasn't) been given a way to navigate to
    the URL.
    """
    return f'href="{url_path}"' in html


def test_view_only_user_sees_no_new_or_edit_buttons_in_list(
    client, tenant_a, user_a_regular
):
    """View-only finance user reaches the list but should see no manage anchors."""
    _give_view_only(user_a_regular, tenant_a, ["finance"])
    acc = Account.objects.create(
        tenant=tenant_a, code="1000", name="Cash", type=Account.Type.ASSET
    )
    client.login(username="alpha-user", password="pass")

    resp = client.get(f"/t/{tenant_a.slug}/finance/account/")
    assert resp.status_code == 200
    html = resp.content.decode()
    # The "create new" link is gated.
    assert not _has_url(html, f"/t/{tenant_a.slug}/finance/account/new/")
    # The "view" link still appears for the existing row.
    assert _has_url(html, f"/t/{tenant_a.slug}/finance/account/{acc.pk}/")
    # The "edit" / "delete" links are gated.
    assert not _has_url(html, f"/t/{tenant_a.slug}/finance/account/{acc.pk}/edit/")
    assert not _has_url(html, f"/t/{tenant_a.slug}/finance/account/{acc.pk}/delete/")


def test_manager_sees_new_edit_delete_buttons(client, tenant_a, user_a_admin):
    """Tenant admin sees every action anchor."""
    acc = Account.objects.create(
        tenant=tenant_a, code="1000", name="Cash", type=Account.Type.ASSET
    )
    client.login(username="alpha-admin", password="pass")

    resp = client.get(f"/t/{tenant_a.slug}/finance/account/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert _has_url(html, f"/t/{tenant_a.slug}/finance/account/new/")
    assert _has_url(html, f"/t/{tenant_a.slug}/finance/account/{acc.pk}/edit/")
    assert _has_url(html, f"/t/{tenant_a.slug}/finance/account/{acc.pk}/delete/")


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
    assert not _has_url(html, f"/t/{tenant_a.slug}/finance/account/{acc.pk}/edit/")
    assert not _has_url(html, f"/t/{tenant_a.slug}/finance/account/{acc.pk}/delete/")
    # Back button still there.
    assert _has_url(html, f"/t/{tenant_a.slug}/finance/account/")


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


# ---------------------------------------------------------------------------
# User display-name rendering
# ---------------------------------------------------------------------------

def test_user_str_prefers_full_name_over_username_or_email(tenant_a):
    """``User.__str__`` should return 'First Last' when both are set."""
    from apps.accounts.models import User

    u = User.objects.create_user(
        username="someuser",
        email="someuser@x.test",
        password="pass",
        tenant=tenant_a,
        first_name="Alex",
        last_name="Patel",
    )
    assert str(u) == "Alex Patel"


def test_user_str_falls_back_to_username_when_no_name(tenant_a):
    from apps.accounts.models import User

    u = User.objects.create_user(
        username="nameless",
        email="nameless@x.test",
        password="pass",
        tenant=tenant_a,
    )
    assert str(u) == "nameless"


# ---------------------------------------------------------------------------
# Friendlier list-view header labels
# ---------------------------------------------------------------------------

def test_list_view_uses_friendly_header_labels(client, tenant_a, user_a_admin):
    """`is_active` should render as 'Active' (not 'is_active' or 'Is active')."""
    Account.objects.create(
        tenant=tenant_a, code="1000", name="Cash", type=Account.Type.ASSET
    )
    client.login(username="alpha-admin", password="pass")
    resp = client.get(f"/t/{tenant_a.slug}/finance/account/")
    assert resp.status_code == 200
    html = resp.content.decode()
    # The header is the cleaned-up label.
    assert "<th>Active</th>" in html
    # The raw field name and Django's default verbose ('Is active')
    # should NOT leak.
    assert "<th>is_active</th>" not in html
    assert "<th>Is active</th>" not in html


# ---------------------------------------------------------------------------
# Org department / team detail pages
# ---------------------------------------------------------------------------

def test_department_detail_shows_teams_and_members_cards(
    client, tenant_a, user_a_admin, user_a_regular
):
    from apps.org.models import Department, Membership, Team

    dept = Department.objects.create(tenant=tenant_a, code="ENG", name="Engineering")
    team = Team.objects.create(
        tenant=tenant_a, code="ENG-A", name="Engineering Team A", department=dept,
    )
    # Give admin a head-of-department membership.
    Membership.objects.create(
        tenant=tenant_a, user=user_a_admin, department=dept, team=None,
        title="Engineering Manager", is_head_of_department=True,
    )
    # Give regular a team membership.
    user_a_regular.first_name = "Pat"
    user_a_regular.last_name = "Lee"
    user_a_regular.save()
    Membership.objects.create(
        tenant=tenant_a, user=user_a_regular, department=dept, team=team,
        title="Software Engineer",
    )

    client.login(username="alpha-admin", password="pass")
    resp = client.get(f"/t/{tenant_a.slug}/org/department/{dept.pk}/")
    assert resp.status_code == 200
    html = resp.content.decode()

    # Teams card content.
    assert "Teams in this department" in html
    assert "Engineering Team A" in html
    # Link to the team's own detail page.
    assert _has_url(html, f"/t/{tenant_a.slug}/org/team/{team.pk}/")

    # Members card content.
    assert "Pat Lee" in html  # regular's full name
    assert "Engineering Manager" in html  # admin's title
    assert "Head of dept." in html  # role badge


def test_team_detail_shows_member_list(
    client, tenant_a, user_a_admin, user_a_regular
):
    from apps.org.models import Department, Membership, Team

    dept = Department.objects.create(tenant=tenant_a, code="OPS", name="Operations")
    team = Team.objects.create(
        tenant=tenant_a, code="OPS-A", name="Ops Team A", department=dept,
    )
    user_a_regular.first_name = "Sam"
    user_a_regular.last_name = "Khan"
    user_a_regular.save()
    Membership.objects.create(
        tenant=tenant_a, user=user_a_regular, department=dept, team=team,
        title="SRE", is_head_of_team=True,
    )

    client.login(username="alpha-admin", password="pass")
    resp = client.get(f"/t/{tenant_a.slug}/org/team/{team.pk}/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Team members" in html
    assert "Sam Khan" in html
    assert "SRE" in html
    assert "Head of team" in html
