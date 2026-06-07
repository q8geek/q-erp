"""Register the events that built-in modules can emit.

The generic CRUD scaffold (`apps/core/crud.py`) emits, for every successful
write via `tenant_scoped_create_or_edit` / `tenant_scoped_delete`:

  <app_label>.<model_name>.created     (new object)
  <app_label>.<model_name>.updated     (existing object edited)
  <app_label>.<model_name>.saved       (always, in addition to created/updated)
  <app_label>.<model_name>.deleted     (after the row is removed)

Modules opt in to surface these events in the Rule UI by registering them
below. ONLY register events that the engine actually fires — registering a
phantom event creates a Rule-dropdown entry that silently never matches.

Events that require additional, non-CRUD emit sites (e.g. status-change
detection, threshold computation) are NOT registered here until those
emit sites exist. Adding them prematurely is worse than not surfacing the
feature: rule authors will configure rules that look like they should
fire but never will.
"""
from __future__ import annotations

from .registry import register_event


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------
register_event(
    "inventory.item.created",
    "Inventory: item created",
    payload_fields={
        "object_id": "Item primary key",
        "sku": "Item SKU",
        "name": "Item name",
    },
)
register_event(
    "inventory.item.updated",
    "Inventory: item updated",
    payload_fields={
        "object_id": "Item primary key",
        "sku": "Item SKU",
        "is_active": "Active flag",
    },
)
register_event(
    "inventory.item.saved",
    "Inventory: item saved (created or updated)",
    description="Fires for both creation and update of an Item.",
    payload_fields={
        "object_id": "Item primary key",
        "sku": "Item SKU",
        "name": "Item name",
        "is_active": "Active flag",
    },
)
register_event(
    "inventory.item.deleted",
    "Inventory: item deleted",
    payload_fields={
        "object_id": "Item primary key (pre-delete snapshot)",
        "sku": "Item SKU",
    },
)
register_event(
    "inventory.warehouse.saved",
    "Inventory: warehouse saved",
    payload_fields={"object_id": "Warehouse pk", "code": "Warehouse code"},
)


# ---------------------------------------------------------------------------
# Procurement
# ---------------------------------------------------------------------------
register_event(
    "procurement.purchaseorder.created",
    "Procurement: purchase order created",
    payload_fields={
        "object_id": "PO pk",
        "number": "PO number",
        "supplier": "Supplier pk",
        "status": "PO status",
        "total": "Total amount (string-encoded Decimal)",
    },
)
register_event(
    "procurement.purchaseorder.updated",
    "Procurement: purchase order updated",
    payload_fields={
        "object_id": "PO pk",
        "number": "PO number",
        "status": "PO status",
    },
)
register_event(
    "procurement.purchaseorder.saved",
    "Procurement: purchase order saved",
    payload_fields={"object_id": "PO pk", "status": "PO status"},
)


# ---------------------------------------------------------------------------
# Support tickets
# ---------------------------------------------------------------------------
register_event(
    "support_tickets.ticket.created",
    "Support: ticket created",
    payload_fields={
        "object_id": "Ticket pk",
        "number": "Ticket number",
        "subject": "Ticket subject",
        "priority": "Ticket priority",
        "category": "Category pk",
        "assignee": "Assignee user pk",
    },
)
register_event(
    "support_tickets.ticket.updated",
    "Support: ticket updated",
    payload_fields={
        "object_id": "Ticket pk",
        "status": "New status (use a condition on this field for status-change rules)",
        "priority": "Priority",
    },
)
register_event(
    "support_tickets.ticket.saved",
    "Support: ticket saved (created or updated)",
    payload_fields={"object_id": "Ticket pk", "status": "Ticket status"},
)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
register_event(
    "tasks.task.created",
    "Tasks: task created",
    payload_fields={
        "object_id": "Task pk",
        "title": "Task title",
        "assignee": "Assignee user pk",
        "priority": "Priority",
        "project": "Project pk (or null)",
    },
)
register_event(
    "tasks.task.updated",
    "Tasks: task updated",
    payload_fields={
        "object_id": "Task pk",
        "status": "Status",
        "assignee": "Assignee user pk",
    },
)
register_event(
    "tasks.task.saved",
    "Tasks: task saved",
    payload_fields={"object_id": "Task pk"},
)


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------
register_event(
    "sales.salesorder.created",
    "Sales: sales order created",
    payload_fields={
        "object_id": "Sales order pk",
        "number": "Order number",
        "customer": "Customer pk",
        "status": "Status",
        "total": "Total amount (string-encoded Decimal)",
    },
)
register_event(
    "sales.salesorder.updated",
    "Sales: sales order updated",
    payload_fields={"object_id": "Sales order pk", "status": "Status"},
)
register_event(
    "sales.salesorder.saved",
    "Sales: sales order saved",
    payload_fields={"object_id": "Sales order pk"},
)


# ---------------------------------------------------------------------------
# Messaging (emitted by messaging views, not the generic CRUD)
# ---------------------------------------------------------------------------
# These are registered for completeness but emit sites currently live only
# in the helper functions, which do NOT call the engine — adding emission
# would change messaging semantics. Intentionally left unregistered for now.
