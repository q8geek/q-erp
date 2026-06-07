"""Subscription enforcement and seat limit tests."""
from __future__ import annotations

import pytest

from apps.accounts.models import User
from apps.tenants.models import Module, Subscription, TenantModule

pytestmark = pytest.mark.django_db


def test_core_modules_auto_attached(tenant_a):
    codes = tenant_a.active_module_codes()
    assert "finance" in codes
    assert "inventory" in codes
    assert "procurement" in codes


def test_subscription_middleware_blocks_inactive_module(client, user_a_admin, tenant_a):
    # hr is active for tenant_a fixture, but let's disable inventory and confirm blocking
    inv = Module.objects.get(code="inventory")
    tm = TenantModule.objects.get(tenant=tenant_a, module=inv)
    from django.utils import timezone
    tm.disabled_at = timezone.now()
    tm.save()
    client.login(username="alpha-admin", password="pass")
    resp = client.get(f"/t/{tenant_a.slug}/inventory/warehouse/")
    assert resp.status_code == 403


def test_dashboard_accessible_when_modules_disabled(client, user_a_admin, tenant_a):
    client.login(username="alpha-admin", password="pass")
    resp = client.get(f"/t/{tenant_a.slug}/dashboard/")
    assert resp.status_code == 200


def test_seat_limit_enforced(tenant_a, plan_growth):
    sub = Subscription.objects.create(tenant=tenant_a, plan=plan_growth)
    # Plan growth seat_limit is 3
    assert tenant_a.effective_seat_limit() == 3
    for i in range(3):
        User.objects.create_user(username=f"user{i}", email=f"u{i}@x.test", password="x", tenant=tenant_a)
    assert tenant_a.active_user_count() == 3
    assert not tenant_a.has_seat_available()
