"""Pytest fixtures for q-erp tests."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command

from apps.accounts.models import SystemAdminTenant, User
from apps.tenants.models import Module, Plan, Subscription, Tenant, TenantGroup, TenantModule


@pytest.fixture
def module_seed(db):
    call_command("sync_modules", verbosity=0)


@pytest.fixture
def tenant_a(db, module_seed):
    t = Tenant.objects.create(slug="alpha", name="Alpha Inc")
    # Activate add-on modules manually for tests (no plan)
    for code in ["hr", "crm", "sales"]:
        m = Module.objects.get(code=code)
        TenantModule.objects.get_or_create(tenant=t, module=m)
    return t


@pytest.fixture
def tenant_b(db, module_seed):
    t = Tenant.objects.create(slug="beta", name="Beta LLC")
    return t


@pytest.fixture
def plan_growth(db, module_seed):
    p = Plan.objects.create(code="test-growth", name="Growth", seat_limit=3, price=0)
    p.modules.set(Module.objects.filter(code__in=["finance", "inventory", "procurement", "hr", "crm"]))
    return p


@pytest.fixture
def tenant_admin_group(tenant_a):
    return TenantGroup.objects.get(tenant=tenant_a, is_system_managed=True).group


@pytest.fixture
def user_a_admin(tenant_a, tenant_admin_group):
    u = User.objects.create_user(username="alpha-admin", email="a@a.test", password="pass", tenant=tenant_a)
    u.groups.add(tenant_admin_group)
    return u


@pytest.fixture
def user_a_regular(tenant_a):
    return User.objects.create_user(username="alpha-user", email="u@a.test", password="pass", tenant=tenant_a)


@pytest.fixture
def user_b_regular(tenant_b):
    return User.objects.create_user(username="beta-user", email="u@b.test", password="pass", tenant=tenant_b)


@pytest.fixture
def global_admin(db):
    u = User(username="root", email="root@sys.test", is_system_admin=True, is_global_admin=True)
    u.set_password("pass")
    u.save()
    return u
