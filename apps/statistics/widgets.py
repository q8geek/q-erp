"""Built-in widgets. Each is module-scoped: it only appears when the
required module is active for the tenant.
"""
from __future__ import annotations

from .registry import register_widget


@register_widget("seats_used", "Seats used", module="tenants", description="Active tenant users vs. seat limit.")
def w_seats(tenant, request):
    limit = tenant.effective_seat_limit()
    used = tenant.active_user_count()
    hint = f"of {limit}" if limit else "no limit"
    return {"value": used, "hint": hint, "unit": "users"}


@register_widget("active_modules", "Active modules", module="tenants", description="Number of modules enabled.")
def w_modules(tenant, request):
    n = len(tenant.active_module_codes())
    return {"value": n, "hint": "incl. core", "unit": "modules"}


@register_widget("inventory_items", "Inventory items", module="inventory", description="Total active items.")
def w_inventory_items(tenant, request):
    from apps.inventory.models import Item

    n = Item.unscoped.filter(tenant=tenant, is_active=True).count()
    return {"value": n, "hint": "active", "unit": "items"}


@register_widget("open_pos", "Open purchase orders", module="procurement", description="POs in DRAFT/SUBMITTED/APPROVED.")
def w_open_pos(tenant, request):
    from apps.procurement.models import PurchaseOrder

    n = PurchaseOrder.unscoped.filter(
        tenant=tenant, status__in=[
            PurchaseOrder.Status.DRAFT,
            PurchaseOrder.Status.SUBMITTED,
            PurchaseOrder.Status.APPROVED,
        ]
    ).count()
    return {"value": n, "hint": "draft/submitted/approved", "unit": "POs"}


@register_widget("open_tickets", "Open support tickets", module="support_tickets", description="Tickets not yet resolved.")
def w_open_tickets(tenant, request):
    from apps.support_tickets.models import Ticket

    n = Ticket.unscoped.filter(
        tenant=tenant,
    ).exclude(status__in=[Ticket.Status.RESOLVED, Ticket.Status.CLOSED]).count()
    return {"value": n, "hint": "not resolved", "unit": "tickets"}


@register_widget("my_open_tasks", "My open tasks", module="tasks", description="Open tasks assigned to current user.", per_user=True)
def w_my_tasks(tenant, request):
    from apps.tasks.models import Task

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"value": 0, "hint": "", "unit": "tasks"}
    n = Task.unscoped.filter(tenant=tenant, assignee=user).exclude(
        status__in=[Task.Status.DONE, Task.Status.CANCELLED]
    ).count()
    return {"value": n, "hint": "assigned to me", "unit": "tasks"}


@register_widget("unread_messages", "Unread messages", module="messaging", description="Messages in user's threads not yet read.", per_user=True)
def w_unread(tenant, request):
    from apps.messaging.views import unread_count

    n = unread_count(request)
    return {"value": n, "hint": "across threads", "unit": "messages"}


@register_widget("rule_runs_today", "Rule runs today", module="automation", description="RuleRun rows for today.")
def w_rule_runs(tenant, request):
    from django.utils import timezone

    from apps.automation.models import RuleRun

    # Use a half-open range so the (tenant, -created_at) index is sargable.
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    n = RuleRun.unscoped.filter(
        tenant=tenant, created_at__gte=today_start
    ).count()
    return {"value": n, "hint": "since midnight", "unit": "runs"}


@register_widget("sales_orders_open", "Open sales orders", module="sales", description="Sales orders in DRAFT/CONFIRMED.")
def w_sales_open(tenant, request):
    from apps.sales.models import SalesOrder

    n = SalesOrder.unscoped.filter(
        tenant=tenant, status__in=[SalesOrder.Status.DRAFT, SalesOrder.Status.CONFIRMED]
    ).count()
    return {"value": n, "hint": "draft/confirmed", "unit": "orders"}


@register_widget("leads_active", "Active leads", module="crm", description="Leads in NEW/QUALIFIED.")
def w_leads(tenant, request):
    from apps.crm.models import Lead

    n = Lead.unscoped.filter(
        tenant=tenant, status__in=[Lead.Status.NEW, Lead.Status.QUALIFIED]
    ).count()
    return {"value": n, "hint": "new/qualified", "unit": "leads"}
