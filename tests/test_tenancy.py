"""Tenant isolation and access tests."""
from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.core.scope import tenant_scope
from apps.finance.models import Account


pytestmark = pytest.mark.django_db


def test_user_clean_enforces_mutual_exclusion(tenant_a):
    u = User(username="bad", email="b@b.test", is_system_admin=True, tenant=tenant_a)
    with pytest.raises(Exception):
        u.full_clean()


def test_tenant_owned_manager_scopes_to_current_tenant(tenant_a, tenant_b):
    with tenant_scope(tenant_a):
        Account.objects.create(tenant=tenant_a, code="1000", name="Cash A")
    with tenant_scope(tenant_b):
        Account.objects.create(tenant=tenant_b, code="1000", name="Cash B")

    with tenant_scope(tenant_a):
        codes = list(Account.objects.values_list("code", flat=True))
        assert codes == ["1000"]
        assert Account.objects.first().name == "Cash A"

    # Unscoped sees both
    assert Account.unscoped.count() == 2


def test_no_tenant_in_scope_returns_empty(tenant_a):
    with tenant_scope(tenant_a):
        Account.objects.create(tenant=tenant_a, code="2000", name="AR")
    # Outside any scope
    assert list(Account.objects.all()) == []
    assert Account.unscoped.count() == 1


def test_login_redirects_tenant_user_to_dashboard(client, user_a_regular, tenant_a):
    client.login(username="alpha-user", password="pass")
    resp = client.get(reverse("post_login_redirect"))
    assert resp.status_code == 302
    assert f"/t/{tenant_a.slug}/dashboard/" in resp.url


def test_login_redirects_system_admin_to_sys(client, global_admin):
    client.login(username="root", password="pass")
    resp = client.get(reverse("post_login_redirect"))
    assert resp.status_code == 302
    assert "/sys/" in resp.url


def test_user_cannot_access_other_tenant(client, user_a_regular, tenant_b):
    client.login(username="alpha-user", password="pass")
    resp = client.get(f"/t/{tenant_b.slug}/dashboard/")
    assert resp.status_code == 403
