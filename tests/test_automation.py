"""Automation engine: condition eval + rule firing."""
from __future__ import annotations

import pytest

from apps.automation.conditions import evaluate
from apps.automation.engine import emit_event
from apps.automation.models import Rule, RuleRun
from apps.messaging.models import Message, Thread


pytestmark = pytest.mark.django_db


def test_empty_condition_matches():
    assert evaluate({}, {"qty": 5}) is True
    assert evaluate(None, {"qty": 5}) is True


def test_simple_comparisons():
    assert evaluate({"qty": {"<": 10}}, {"qty": 5}) is True
    assert evaluate({"qty": {"<": 10}}, {"qty": 15}) is False
    assert evaluate({"name": {"==": "X"}}, {"name": "X"}) is True
    assert evaluate({"name": {"!=": "X"}}, {"name": "Y"}) is True


def test_combinators():
    cond = {"$any": [{"a": {"==": 1}}, {"b": {"==": 2}}]}
    assert evaluate(cond, {"a": 1, "b": 9}) is True
    assert evaluate(cond, {"a": 9, "b": 2}) is True
    assert evaluate(cond, {"a": 0, "b": 0}) is False


def test_dotted_path():
    payload = {"item": {"sku": "ABC", "qty": 3}}
    assert evaluate({"item.qty": {"<=": 3}}, payload) is True


def test_emit_event_no_rules_no_runs(rf, tenant_a, user_a_admin):
    request = rf.get("/")
    request.tenant = tenant_a
    request.user = user_a_admin
    runs = emit_event(request, "inventory.item.saved", {"sku": "X", "name": "Y"})
    assert runs == []


def test_emit_event_fires_send_notification(rf, tenant_a, user_a_admin, user_a_regular):
    Rule.unscoped.create(
        tenant=tenant_a,
        name="notify on item save",
        event_type="inventory.item.saved",
        condition={},
        action_type="send_notification",
        action_params={"recipient_user_id": user_a_regular.pk, "body": "item {sku} saved"},
    )
    request = rf.get("/")
    request.tenant = tenant_a
    request.user = user_a_admin
    runs = emit_event(request, "inventory.item.saved", {"sku": "ABC", "name": "Widget"})
    assert len(runs) == 1
    assert runs[0].status == RuleRun.Status.MATCHED
    # Notification thread created with message body containing the SKU
    msg = Message.unscoped.filter(tenant=tenant_a).order_by("-pk").first()
    assert msg is not None
    assert "ABC" in msg.body
    assert msg.thread.kind == Thread.Kind.NOTIFICATION


def test_emit_event_condition_skips(rf, tenant_a, user_a_admin, user_a_regular):
    """A non-matching condition must NOT create a RuleRun row (engine v2
    suppresses SKIPPED audit rows to bound table growth) and must NOT fire
    the action."""
    Rule.unscoped.create(
        tenant=tenant_a,
        name="only urgent",
        event_type="inventory.item.saved",
        condition={"qty": {"<": 10}},
        action_type="send_notification",
        action_params={"recipient_user_id": user_a_regular.pk, "body": "hi"},
    )
    request = rf.get("/")
    request.tenant = tenant_a
    request.user = user_a_admin
    runs = emit_event(request, "inventory.item.saved", {"qty": 100})
    assert runs == []  # SKIPPED runs are not persisted
    assert RuleRun.unscoped.filter(tenant=tenant_a).count() == 0
    assert Message.unscoped.filter(tenant=tenant_a).count() == 0


def test_emit_event_handler_error_recorded(rf, tenant_a, user_a_admin):
    Rule.unscoped.create(
        tenant=tenant_a,
        name="missing supplier",
        event_type="inventory.item.saved",
        condition={},
        action_type="create_purchase_request",
        action_params={"supplier_id": 9999999},  # nonexistent
    )
    request = rf.get("/")
    request.tenant = tenant_a
    request.user = user_a_admin
    runs = emit_event(request, "inventory.item.saved", {"sku": "X"})
    assert len(runs) == 1
    # The handler logs a warning and returns; not raising. So status is MATCHED but no PO created.
    # We verify no exception and that a run row exists.
    from apps.procurement.models import PurchaseOrder
    assert PurchaseOrder.unscoped.filter(tenant=tenant_a).count() == 0


@pytest.fixture
def rf():
    from django.test import RequestFactory
    return RequestFactory()
