"""Permission enforcement tests."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, Permission


pytestmark = pytest.mark.django_db


def test_regular_user_without_perms_is_blocked(client, user_a_regular, tenant_a):
    client.login(username="alpha-user", password="pass")
    resp = client.get(f"/t/{tenant_a.slug}/finance/account/")
    assert resp.status_code == 403


def test_user_with_view_perm_can_list(client, user_a_regular, tenant_a):
    perm = Permission.objects.get(codename="view_finance", content_type__app_label="finance")
    group = Group.objects.create(name=f"t{tenant_a.id}:viewers")
    from apps.tenants.models import TenantGroup
    TenantGroup.objects.create(tenant=tenant_a, group=group)
    group.permissions.add(perm)
    user_a_regular.groups.add(group)
    client.login(username="alpha-user", password="pass")
    resp = client.get(f"/t/{tenant_a.slug}/finance/account/")
    assert resp.status_code == 200


def test_tenant_admin_can_create_account(client, user_a_admin, tenant_a):
    client.login(username="alpha-admin", password="pass")
    resp = client.post(
        f"/t/{tenant_a.slug}/finance/account/new/",
        {"code": "1000", "name": "Cash", "type": "ASSET", "is_active": "on"},
    )
    assert resp.status_code == 302
    from apps.finance.models import Account
    assert Account.unscoped.filter(tenant=tenant_a, code="1000").exists()
