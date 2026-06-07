"""System admin scoping tests."""
from __future__ import annotations

import pytest

from apps.accounts.models import SystemAdminTenant, User

pytestmark = pytest.mark.django_db


def test_global_admin_sees_all_tenants(global_admin, tenant_a, tenant_b):
    tenants = list(global_admin.accessible_tenants())
    assert tenant_a in tenants
    assert tenant_b in tenants


def test_scoped_admin_sees_only_assigned(tenant_a, tenant_b):
    sa = User(username="sa1", email="sa1@x.test", is_system_admin=True, is_global_admin=False)
    sa.set_password("x")
    sa.save()
    SystemAdminTenant.objects.create(user=sa, tenant=tenant_a)
    tenants = list(sa.accessible_tenants())
    assert tenant_a in tenants
    assert tenant_b not in tenants


def test_non_sysadmin_cannot_access_sys(client, user_a_regular):
    client.login(username="alpha-user", password="pass")
    resp = client.get("/sys/")
    assert resp.status_code == 403


def test_global_admin_can_access_sys(client, global_admin):
    client.login(username="root", password="pass")
    resp = client.get("/sys/")
    assert resp.status_code == 200
