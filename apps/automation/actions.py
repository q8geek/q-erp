"""Built-in action handlers.

Each handler receives keyword args `(tenant, payload, rule, params)`.
- `tenant`: the Tenant instance.
- `payload`: the event payload dict (e.g. {"item_id": 5, "qty_on_hand": 3, ...}).
- `rule`: the Rule that matched (gives access to `rule.action_params`).
- `params`: convenience alias for `rule.action_params`.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.utils import timezone

from .registry import register_action

log = logging.getLogger(__name__)


@register_action(
    "send_notification",
    "Send a notification to a user",
    description="Posts a message into the recipient's notification inbox.",
    params={
        "recipient_user_id": "Tenant user id to notify",
        "body": "Notification body (supports {payload.path} placeholders)",
        "subject": "Optional notification subject",
    },
)
def action_send_notification(*, tenant, payload, rule, params):
    # Lazy imports keep the automation app loadable even if messaging is
    # removed from INSTALLED_APPS for some reason.
    from apps.accounts.models import User
    from apps.messaging.models import send_notification

    recipient_id = params.get("recipient_user_id")
    if not recipient_id:
        return
    try:
        recipient = User.objects.get(pk=recipient_id, tenant=tenant)
    except User.DoesNotExist:
        log.warning("send_notification: recipient %s not in tenant %s", recipient_id, tenant)
        return
    body = _render(params.get("body", ""), payload)
    subject = _render(params.get("subject", "Automation notification"), payload)
    send_notification(tenant=tenant, recipient=recipient, body=body, subject=subject)


@register_action(
    "create_task",
    "Create a task",
    description="Creates a Task assigned to a user.",
    params={
        "title": "Task title (supports {payload.path} placeholders)",
        "assignee_user_id": "Tenant user id to assign",
        "priority": "LOW|NORMAL|HIGH|URGENT",
    },
)
def action_create_task(*, tenant, payload, rule, params):
    from apps.accounts.models import User
    from apps.tasks.models import Task

    title = _render(params.get("title", "Automation task"), payload)
    priority = params.get("priority", Task.Priority.NORMAL)
    assignee = None
    aid = params.get("assignee_user_id")
    if aid:
        try:
            assignee = User.objects.get(pk=aid, tenant=tenant)
        except User.DoesNotExist:
            assignee = None
    Task.unscoped.create(
        tenant=tenant,
        title=title[:200],
        assignee=assignee,
        priority=priority,
        status=Task.Status.TODO,
    )


@register_action(
    "create_purchase_request",
    "Create a draft purchase order",
    description="Creates a draft Purchase Order for a supplier with a generated number. "
                "Useful as the action for an 'item below threshold' rule.",
    params={
        "supplier_id": "Supplier to attach the PO to",
        "total": "Estimated total amount (optional)",
        "number_prefix": "Number prefix (default 'AUTO-')",
    },
)
def action_create_purchase_request(*, tenant, payload, rule, params):
    from apps.procurement.models import PurchaseOrder, Supplier

    supplier_id = params.get("supplier_id")
    if not supplier_id:
        log.warning("create_purchase_request: no supplier_id in params")
        return
    try:
        supplier = Supplier.unscoped.get(pk=supplier_id, tenant=tenant)
    except Supplier.DoesNotExist:
        log.warning("create_purchase_request: supplier %s not in tenant", supplier_id)
        return
    prefix = params.get("number_prefix", "AUTO-")
    number = f"{prefix}{timezone.now():%Y%m%d%H%M%S}-{rule.pk}"
    total = params.get("total", 0) or 0
    try:
        total = Decimal(str(total))
    except Exception:
        total = Decimal("0")
    PurchaseOrder.unscoped.create(
        tenant=tenant,
        number=number[:32],
        supplier=supplier,
        status=PurchaseOrder.Status.DRAFT,
        total=total,
    )


# Per-emit_event memoization for head-of lookups.
#
# The cache lives on a ContextVar bound by ``apps.automation.engine.emit_event``
# (see ``engine.get_head_of_cache``). Properties of the new design:
#
# * Memoized for the duration of the enclosing ``emit_event`` call. The dict
#   is shared across every rule + action handler invoked within that call.
# * Benefits multi-rule events targeting the same (scope_kind, pk): the
#   second and subsequent lookups hit the cache. Single-rule events get no
#   benefit (single insert, single read).
# * Thread-safe under any worker model (sync, threaded WSGI,
#   asgiref-wrapped async) because ContextVar provides per-call isolation.
# * Outside ``emit_event`` (e.g. direct unit-test calls into the action
#   handler) the cache degrades to a throwaway dict — lookups still work,
#   they just are not memoized.
#
# Keys are ``(tenant_id, scope_kind, pk)`` where ``scope_kind`` is
# ``"department"`` or ``"team"``.


def _resolve_scope_and_head(*, tenant, scope_kind: str, pk):
    """Resolve (scope_obj, recipient) for the given scope_kind/pk under `tenant`.

    Returns (scope_obj, recipient) or (None, None) if the scope is missing or
    cross-tenant. `recipient` may be None when no head is set.

    Memoized for the duration of the enclosing ``emit_event`` call via a
    ContextVar (see :func:`apps.automation.engine.get_head_of_cache`). The
    memoization is safe under threaded workers because each ``emit_event``
    call binds its own dict.
    """
    from apps.automation.engine import get_head_of_cache
    from apps.org.models import Department, Team, head_of

    cache = get_head_of_cache()
    cache_key = (tenant.id, scope_kind, pk)
    if cache_key in cache:
        return cache[cache_key]

    model = Department if scope_kind == "department" else Team
    try:
        scope = model.unscoped.get(pk=pk, tenant=tenant)
    except model.DoesNotExist:
        log.warning("notify_head_of_%s: %s %s not in tenant", scope_kind, scope_kind, pk)
        result = (None, None)
        cache[cache_key] = result
        return result
    recipient = head_of(tenant=tenant, **{scope_kind: scope})
    result = (scope, recipient)
    cache[cache_key] = result
    return result


def _notify_head_of_scope(*, tenant, payload, rule, params, scope_kind: str):
    """Shared body for notify_head_of_department / notify_head_of_team.

    `scope_kind` is "department" or "team".
    """
    from apps.messaging.models import send_notification

    pk_key = f"{scope_kind}_id"
    pk = params.get(pk_key)
    if not pk:
        return
    scope, recipient = _resolve_scope_and_head(tenant=tenant, scope_kind=scope_kind, pk=pk)
    if scope is None:
        return
    if recipient is None:
        log.info("notify_head_of_%s: %s %s has no head set", scope_kind, scope_kind, pk)
        return
    if recipient.tenant_id != tenant.id:
        log.warning(
            "notify_head_of_%s: head of %s %s belongs to tenant %s, not %s",
            scope_kind,
            scope_kind,
            pk,
            recipient.tenant_id,
            tenant.id,
        )
        return
    body = _render(params.get("body", ""), payload)
    subject = _render(
        params.get("subject", f"Head-of-{scope_kind} notification"), payload
    )
    send_notification(tenant=tenant, recipient=recipient, body=body, subject=subject)


@register_action(
    "notify_head_of_department",
    "Notify the head of a department",
    description=(
        "Looks up the User flagged is_head_of_department=True on the given "
        "department and sends them a notification. No-op if the department "
        "has no head set."
    ),
    params={
        "department_id": "Tenant department id whose head to notify",
        "body": "Notification body (supports {payload.path} placeholders)",
        "subject": "Optional notification subject",
    },
)
def action_notify_head_of_department(*, tenant, payload, rule, params):
    _notify_head_of_scope(
        tenant=tenant, payload=payload, rule=rule, params=params, scope_kind="department"
    )


@register_action(
    "notify_head_of_team",
    "Notify the head of a team",
    description=(
        "Looks up the User flagged is_head_of_team=True on the given team "
        "and sends them a notification. No-op if the team has no head set."
    ),
    params={
        "team_id": "Tenant team id whose head to notify",
        "body": "Notification body (supports {payload.path} placeholders)",
        "subject": "Optional notification subject",
    },
)
def action_notify_head_of_team(*, tenant, payload, rule, params):
    _notify_head_of_scope(
        tenant=tenant, payload=payload, rule=rule, params=params, scope_kind="team"
    )


@register_action(
    "log_activity",
    "Write to activity log",
    description="Emits a custom ActivityLog row with category=OTHER.",
    params={
        "action": "Action string (e.g. 'automation.custom')",
        "note": "Free-form note",
    },
)
def action_log_activity(*, tenant, payload, rule, params):
    from apps.activity.models import ActivityLog

    ActivityLog.objects.create(
        tenant=tenant,
        category=ActivityLog.Category.OTHER,
        action=str(params.get("action", "automation.custom"))[:120],
        object_repr=str(params.get("note", ""))[:255],
        extra={"payload": payload, "rule_id": rule.pk},
    )


def _render(template: str, payload: dict) -> str:
    """Tiny placeholder renderer: {payload.path.to.value} -> resolved value."""
    if not template:
        return ""
    out = template
    # Find {...} groups
    import re

    def _sub(m):
        path = m.group(1).strip()
        if path.startswith("payload."):
            path = path[len("payload.") :]
        cur = payload
        for part in path.split("."):
            if isinstance(cur, dict):
                cur = cur.get(part)
            else:
                cur = getattr(cur, part, None)
            if cur is None:
                return ""
        return str(cur)

    return re.sub(r"\{([^}]+)\}", _sub, out)
