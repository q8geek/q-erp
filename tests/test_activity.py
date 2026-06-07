"""Activity log scoping tests."""
from __future__ import annotations

import pytest

from apps.activity.models import ActivityLog

pytestmark = pytest.mark.django_db


def test_login_creates_auth_log(client, user_a_regular):
    initial = ActivityLog.objects.count()
    client.login(username="alpha-user", password="pass")
    # POST through the login view to fire the signal
    resp = client.post("/accounts/login/", {"username": "alpha-user", "password": "pass"})
    assert resp.status_code in (200, 302)
    assert ActivityLog.objects.filter(category=ActivityLog.Category.AUTH).count() >= 1


def test_tenant_admin_sees_only_own_tenant_activity(client, user_a_admin, tenant_a, tenant_b):
    # Seed cross-tenant logs
    ActivityLog.objects.create(tenant=tenant_a, action="finance.account.list", category=ActivityLog.Category.MODULE_READ)
    ActivityLog.objects.create(tenant=tenant_b, action="finance.account.list", category=ActivityLog.Category.MODULE_READ)
    client.login(username="alpha-admin", password="pass")
    resp = client.get(f"/t/{tenant_a.slug}/admin/activity/")
    assert resp.status_code == 200
    content = resp.content.decode()
    # The tenant slug column shows alpha rows only
    assert "finance.account.list" in content
    # Should not contain beta's pk
    assert str(tenant_b.id) not in content or content.count("finance.account.list") == 1
