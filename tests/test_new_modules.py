"""Smoke tests for the newly added modules."""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.django_db


def test_messaging_direct_helper_creates_thread(tenant_a, user_a_admin, user_a_regular):
    from apps.messaging.models import Message, Thread, send_direct_message

    from apps.messaging.models import Participant

    msg = send_direct_message(
        tenant=tenant_a, sender=user_a_admin, recipient=user_a_regular, body="hello"
    )
    assert msg.thread.kind == Thread.Kind.DIRECT
    assert Participant.unscoped.filter(thread=msg.thread).count() == 2
    # Second DM reuses the same thread
    msg2 = send_direct_message(
        tenant=tenant_a, sender=user_a_admin, recipient=user_a_regular, body="again"
    )
    assert msg.thread_id == msg2.thread_id
    assert Message.unscoped.filter(thread=msg.thread).count() == 2


def test_messaging_notification_helper_reuses_thread(tenant_a, user_a_regular):
    from apps.messaging.models import Thread, send_notification

    send_notification(tenant=tenant_a, recipient=user_a_regular, body="one")
    send_notification(tenant=tenant_a, recipient=user_a_regular, body="two")
    notifications = Thread.unscoped.filter(
        tenant=tenant_a, kind=Thread.Kind.NOTIFICATION, participants__user=user_a_regular
    ).distinct()
    assert notifications.count() == 1


def test_tasks_module_creates_task(client, user_a_admin, tenant_a):
    client.login(username="alpha-admin", password="pass")
    resp = client.post(
        f"/t/{tenant_a.slug}/tasks/task/new/",
        {
            "title": "do it",
            "description": "stuff",
            "status": "TODO",
            "priority": "NORMAL",
        },
    )
    assert resp.status_code == 302
    from apps.tasks.models import Task

    assert Task.unscoped.filter(tenant=tenant_a, title="do it").exists()


def test_support_tickets_list_accessible(client, user_a_admin, tenant_a):
    from apps.tenants.models import Module, TenantModule

    # Activate support_tickets for tenant_a
    m = Module.objects.get(code="support_tickets")
    TenantModule.objects.get_or_create(tenant=tenant_a, module=m)
    client.login(username="alpha-admin", password="pass")
    resp = client.get(f"/t/{tenant_a.slug}/support_tickets/ticket/")
    assert resp.status_code == 200


def test_org_membership_one_head_per_department(tenant_a, user_a_admin, user_a_regular):
    from django.db import IntegrityError, transaction
    from apps.org.models import Department, Membership

    dept = Department.unscoped.create(tenant=tenant_a, code="ENG", name="Engineering")
    Membership.unscoped.create(
        tenant=tenant_a, user=user_a_admin, department=dept, is_head_of_department=True
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Membership.unscoped.create(
                tenant=tenant_a,
                user=user_a_regular,
                department=dept,
                is_head_of_department=True,
            )


def test_statistics_dashboard_renders(client, user_a_admin, tenant_a):
    client.login(username="alpha-admin", password="pass")
    resp = client.get(f"/t/{tenant_a.slug}/statistics/")
    assert resp.status_code == 200
    # Should include at least the seats widget
    assert b"Seats" in resp.content or b"seats" in resp.content


def test_automation_rule_list_accessible(client, user_a_admin, tenant_a):
    client.login(username="alpha-admin", password="pass")
    resp = client.get(f"/t/{tenant_a.slug}/automation/")
    assert resp.status_code == 200
