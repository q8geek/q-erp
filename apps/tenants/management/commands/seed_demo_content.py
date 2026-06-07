"""Populate the three demo tenants with realistic per-module content.

Run AFTER `seed_demo`. Domain-data writes are idempotent (everything
uses `get_or_create` / `update_or_create`), so re-running won't duplicate
inventory items, accounts, customers, etc.

Two pieces are NOT idempotent and will accumulate on re-runs:
  * team users — only the User row is `get_or_create`'d, but every run
    adds them to the Module Users group (already in group; cheap no-op)
    and ensures their Membership row exists. Net effect on the DB is
    zero new rows after the first run.
  * ActivityLog rows — every run writes a fresh batch of ~10-15 rows
    per team user (logins + reads + writes), backdated across the past
    week. Pass ``--clear-activity`` to wipe the prior batch first.

Themes:
  * acme    — Acme Industries: light manufacturing co (active modules:
              core only). Fills finance, inventory, procurement, org,
              tasks, messaging, statistics.
  * globex  — Globex Corp: software/services with sales pipeline
              (active modules: core + HR, CRM, Sales, Support Tickets).
              Adds employees, customers, leads, sales orders, support
              tickets on top of Acme's coverage.
  * initech — Initech Systems: full enterprise (all 16 modules). Adds
              manufacturing BOMs/work orders, documents, projects,
              fixed assets, plus a working automation rule that fires
              a notification when items are saved.

Per-tenant content also includes:
  * 2-5 users per team and 1-2 users per department (all in the
    ``Module Users`` group seeded by ``seed_demo`` — view-only on every
    active module).
  * Backdated ActivityLog rows for each of those users across the past
    7 days: 1-3 logins, 3-8 module-read rows, 0-3 module-write rows.

Usage on PythonAnywhere:
    export ALLOW_SEED_DEMO=1
    python manage.py seed_demo_content
    # Subsequent runs to refresh content without doubling activity:
    python manage.py seed_demo_content --clear-activity
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core.scope import tenant_scope
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Populate the three demo tenants (acme/globex/initech) with per-module content."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            choices=["acme", "globex", "initech", "all"],
            default="all",
            help="Limit seeding to a single tenant (default: all three).",
        )
        parser.add_argument(
            "--clear-activity",
            action="store_true",
            help=(
                "Before seeding, delete any ActivityLog rows previously "
                "seeded by this command (rows whose user_agent is "
                "'seed_demo_content/1.0'). Use this to avoid duplicate "
                "activity buildup on re-runs."
            ),
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and os.environ.get("ALLOW_SEED_DEMO") != "1":
            raise CommandError(
                "seed_demo_content refuses to run with DEBUG=False unless ALLOW_SEED_DEMO=1"
            )

        targets = (
            ["acme", "globex", "initech"] if options["tenant"] == "all" else [options["tenant"]]
        )

        for slug in targets:
            try:
                tenant = Tenant.objects.get(slug=slug)
            except Tenant.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(
                        f"Tenant '{slug}' not found — run `python manage.py seed_demo` first."
                    )
                )
                continue
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== Seeding {tenant.name} ({slug}) ==="))
            if options.get("clear_activity"):
                from apps.activity.models import ActivityLog

                deleted, _ = ActivityLog.objects.filter(
                    tenant=tenant, user_agent="seed_demo_content/1.0",
                ).delete()
                self._log(tenant, "activity", f"cleared {deleted} previously-seeded rows")
            with transaction.atomic(), tenant_scope(tenant):
                self._seed_one(tenant)
        self.stdout.write(self.style.SUCCESS("\nContent seed complete."))
        self.stdout.write("Visit any tenant dashboard, e.g.:")
        self.stdout.write("  /t/acme/dashboard/")
        self.stdout.write("  /t/globex/dashboard/")
        self.stdout.write("  /t/initech/dashboard/")

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def _seed_one(self, tenant: Tenant) -> None:
        active = tenant.active_module_codes()
        admin = User.objects.filter(tenant=tenant, username=f"{tenant.slug}-admin").first()
        regular = User.objects.filter(tenant=tenant, username=f"{tenant.slug}-user").first()

        # Core modules (always present)
        self._seed_finance(tenant)
        self._seed_inventory(tenant)
        self._seed_procurement(tenant)
        self._seed_org(tenant, admin=admin, regular=regular)
        self._seed_tasks(tenant, admin=admin, regular=regular)
        self._seed_messaging(tenant, admin=admin, regular=regular)
        self._seed_statistics(tenant)

        # Add-on modules — only if active for this tenant.
        if "hr" in active:
            self._seed_hr(tenant)
        if "crm" in active:
            self._seed_crm(tenant, admin=admin)
        if "sales" in active:
            self._seed_sales(tenant)
        if "support_tickets" in active:
            self._seed_support_tickets(tenant, admin=admin, regular=regular)
        if "manufacturing" in active:
            self._seed_manufacturing(tenant)
        if "documents" in active:
            self._seed_documents(tenant)
        if "projects" in active:
            self._seed_projects(tenant, admin=admin, regular=regular)
        if "assets" in active:
            self._seed_assets(tenant)
        if "automation" in active:
            self._seed_automation(tenant, admin=admin)

        # Populate 2-5 users per team + 1-2 per department, then generate
        # backdated ActivityLog rows for them targeted at modules they have
        # access to.
        team_users = self._seed_team_users(tenant)
        self._seed_activity_for_users(tenant, team_users, active=active)

    # ------------------------------------------------------------------
    # Per-module seeders. All are idempotent.
    # ------------------------------------------------------------------

    def _seed_finance(self, tenant: Tenant) -> None:
        from apps.finance.models import Account

        chart = [
            ("1000", "Cash", Account.Type.ASSET),
            ("1100", "Accounts Receivable", Account.Type.ASSET),
            ("1200", "Inventory", Account.Type.ASSET),
            ("2000", "Accounts Payable", Account.Type.LIABILITY),
            ("3000", "Owner Equity", Account.Type.EQUITY),
            ("4000", "Sales Revenue", Account.Type.REVENUE),
            ("5000", "Cost of Goods Sold", Account.Type.EXPENSE),
            ("6000", "Operating Expenses", Account.Type.EXPENSE),
        ]
        for code, name, type_ in chart:
            Account.objects.update_or_create(
                tenant=tenant, code=code,
                defaults={"name": name, "type": type_, "is_active": True},
            )
        self._log(tenant, "finance", f"chart of accounts: {len(chart)} accounts")

    def _seed_inventory(self, tenant: Tenant) -> None:
        from apps.inventory.models import Item, Warehouse

        warehouses = [
            ("MAIN", "Main Warehouse"),
            ("EAST", "East Coast DC"),
        ]
        wh_by_code = {}
        for code, name in warehouses:
            wh, _ = Warehouse.objects.update_or_create(
                tenant=tenant, code=code,
                defaults={"name": name, "is_active": True},
            )
            wh_by_code[code] = wh

        # Items differ per tenant theme.
        if tenant.slug == "acme":
            items = [
                ("WIDGET-001", "Anvil, 50 lb", "EA"),
                ("WIDGET-002", "Anvil, 100 lb", "EA"),
                ("ROCKET-001", "Rocket Skates, Adult", "PR"),
                ("ROCKET-002", "Rocket Skates, Junior", "PR"),
                ("RAW-STEEL", "Cold-rolled steel sheet", "KG"),
                ("RAW-RUBBER", "Vulcanised rubber bar", "KG"),
            ]
        elif tenant.slug == "globex":
            items = [
                ("LIC-PRO", "Globex Pro License (annual)", "EA"),
                ("LIC-ENT", "Globex Enterprise License (annual)", "EA"),
                ("SUP-STD", "Standard Support (monthly)", "EA"),
                ("SUP-PRM", "Premium Support (monthly)", "EA"),
                ("HW-LAPTOP", "Branded Laptop", "EA"),
                ("HW-DOCK", "Docking Station", "EA"),
            ]
        else:  # initech
            items = [
                ("TPS-FORM", "TPS Report Cover Sheet", "EA"),
                ("TPS-BIND", "TPS Report Binder", "EA"),
                ("OFFICE-CHAIR", "Office Chair, Ergo", "EA"),
                ("OFFICE-DESK", "Standing Desk, Adj.", "EA"),
                ("SERVER-1U", "1U Rack Server", "EA"),
                ("SERVER-2U", "2U Rack Server", "EA"),
                ("SWITCH-48", "48-port managed switch", "EA"),
            ]
        for sku, name, uom in items:
            Item.objects.update_or_create(
                tenant=tenant, sku=sku,
                defaults={
                    "name": name,
                    "uom": uom,
                    "default_warehouse": wh_by_code["MAIN"],
                    "is_active": True,
                },
            )
        self._log(tenant, "inventory", f"{len(warehouses)} warehouses, {len(items)} items")

    def _seed_procurement(self, tenant: Tenant) -> None:
        from apps.procurement.models import PurchaseOrder, Supplier

        if tenant.slug == "acme":
            suppliers = [
                ("ACME-SUP-001", "Acme Steel Co", "sales@acmesteel.example"),
                ("ACME-SUP-002", "Rubber Wholesalers Inc", "orders@rubberwh.example"),
            ]
        elif tenant.slug == "globex":
            suppliers = [
                ("GLOBEX-SUP-001", "CloudHost Inc", "billing@cloudhost.example"),
                ("GLOBEX-SUP-002", "DevTools LLC", "ar@devtools.example"),
            ]
        else:  # initech
            suppliers = [
                ("INI-SUP-001", "Office Supply Depot", "orders@officedepot.example"),
                ("INI-SUP-002", "Server Hardware Co", "sales@serverhw.example"),
                ("INI-SUP-003", "Cleaning Services Co", "info@cleaning.example"),
            ]

        sup_by_code = {}
        for code, name, email in suppliers:
            sup, _ = Supplier.objects.update_or_create(
                tenant=tenant, code=code,
                defaults={
                    "name": name, "contact_email": email,
                    "contact_phone": "+1-555-0100", "is_active": True,
                },
            )
            sup_by_code[code] = sup

        # A handful of POs across statuses.
        first_sup = next(iter(sup_by_code.values()))
        po_specs = [
            (f"PO-{tenant.slug.upper()}-001", first_sup, PurchaseOrder.Status.DRAFT, "1250.00"),
            (f"PO-{tenant.slug.upper()}-002", first_sup, PurchaseOrder.Status.SUBMITTED, "3400.50"),
            (f"PO-{tenant.slug.upper()}-003", first_sup, PurchaseOrder.Status.APPROVED, "780.00"),
            (f"PO-{tenant.slug.upper()}-004", first_sup, PurchaseOrder.Status.RECEIVED, "9999.99"),
        ]
        for number, supplier, status, total in po_specs:
            PurchaseOrder.objects.update_or_create(
                tenant=tenant, number=number,
                defaults={"supplier": supplier, "status": status, "total": Decimal(total)},
            )
        self._log(
            tenant, "procurement",
            f"{len(suppliers)} suppliers, {len(po_specs)} purchase orders",
        )

    def _seed_org(self, tenant: Tenant, *, admin: User | None, regular: User | None) -> None:
        from apps.org.models import Department, Membership, Team

        if tenant.slug == "acme":
            dept_specs = [("ENG", "Engineering"), ("OPS", "Operations"), ("SALES", "Sales")]
        elif tenant.slug == "globex":
            dept_specs = [("ENG", "Engineering"), ("CS", "Customer Success"), ("FIN", "Finance")]
        else:
            dept_specs = [
                ("ENG", "Engineering"),
                ("HR", "Human Resources"),
                ("FIN", "Finance"),
                ("OPS", "Operations"),
            ]
        depts = {}
        for code, name in dept_specs:
            d, _ = Department.objects.update_or_create(
                tenant=tenant, code=code,
                defaults={"name": name, "is_active": True},
            )
            depts[code] = d

        # One team per department for the first two departments.
        team_specs = [
            ("ENG-A", "Engineering Team A", "ENG"),
            ("ENG-B", "Engineering Team B", "ENG"),
        ]
        teams = {}
        for code, name, dept_code in team_specs:
            if dept_code not in depts:
                continue
            t, _ = Team.objects.update_or_create(
                tenant=tenant, code=code,
                defaults={
                    "name": name, "department": depts[dept_code], "is_active": True,
                },
            )
            teams[code] = t

        # Memberships: admin = head of Engineering; regular = team-A member.
        if admin and "ENG" in depts:
            Membership.objects.update_or_create(
                tenant=tenant, user=admin, department=depts["ENG"], team=None,
                defaults={
                    "title": "Engineering Manager",
                    "is_head_of_department": True,
                    "is_head_of_team": False,
                },
            )
        if regular and "ENG" in depts and "ENG-A" in teams:
            Membership.objects.update_or_create(
                tenant=tenant, user=regular, department=depts["ENG"], team=teams["ENG-A"],
                defaults={
                    "title": "Software Engineer",
                    "is_head_of_department": False,
                    "is_head_of_team": True,  # head of team A
                },
            )
        self._log(
            tenant, "org",
            f"{len(depts)} departments, {len(teams)} teams, 2 memberships",
        )

    def _seed_tasks(self, tenant: Tenant, *, admin: User | None, regular: User | None) -> None:
        from apps.tasks.models import Task

        if tenant.slug == "acme":
            specs = [
                ("Set up 2026 cost centers", Task.Status.TODO, Task.Priority.NORMAL),
                ("Review quarterly inventory", Task.Status.IN_PROGRESS, Task.Priority.HIGH),
                ("Renew steel supplier contract", Task.Status.TODO, Task.Priority.HIGH),
                ("Q1 financial close", Task.Status.DONE, Task.Priority.URGENT),
            ]
        elif tenant.slug == "globex":
            specs = [
                ("Q2 product launch checklist", Task.Status.IN_PROGRESS, Task.Priority.URGENT),
                ("Customer NPS survey rollout", Task.Status.TODO, Task.Priority.NORMAL),
                ("Onboard new sales rep", Task.Status.IN_PROGRESS, Task.Priority.NORMAL),
                ("Year-end licensing audit", Task.Status.BLOCKED, Task.Priority.LOW),
            ]
        else:
            specs = [
                ("Replace office printer", Task.Status.TODO, Task.Priority.LOW),
                ("Migrate file server to new rack", Task.Status.IN_PROGRESS, Task.Priority.HIGH),
                ("Run TPS report process review", Task.Status.TODO, Task.Priority.NORMAL),
                ("Decommission legacy mainframe", Task.Status.BLOCKED, Task.Priority.NORMAL),
                ("Q1 board prep", Task.Status.DONE, Task.Priority.URGENT),
            ]
        today = timezone.now().date()
        for i, (title, status, priority) in enumerate(specs):
            assignee = admin if i % 2 == 0 else regular
            Task.objects.update_or_create(
                tenant=tenant, title=title,
                defaults={
                    "status": status,
                    "priority": priority,
                    "assignee": assignee,
                    "due_date": today + timedelta(days=7 + i),
                },
            )
        self._log(tenant, "tasks", f"{len(specs)} tasks")

    def _seed_messaging(self, tenant: Tenant, *, admin: User | None, regular: User | None) -> None:
        from apps.messaging.models import send_direct_message, send_notification

        if not admin or not regular:
            return
        # One DM thread (idempotent: helper reuses existing 1:1 thread).
        send_direct_message(
            tenant=tenant,
            sender=admin,
            recipient=regular,
            body=f"Welcome to {tenant.name}! Let me know if you need anything.",
            subject="Welcome",
        )
        # One system notification per user (helper reuses existing notification thread).
        send_notification(
            tenant=tenant,
            recipient=admin,
            body="Your tenant data is being initialised. Refresh the dashboard.",
            subject="System notification",
        )
        send_notification(
            tenant=tenant,
            recipient=regular,
            body="You've been assigned to a team — check the Org module.",
            subject="System notification",
        )
        self._log(tenant, "messaging", "1 DM, 2 notifications")

    def _seed_statistics(self, tenant: Tenant) -> None:
        from apps.statistics.models import DashboardWidget
        from apps.statistics.registry import all_widgets

        active = tenant.active_module_codes()
        eligible = [
            (code, w) for code, w in all_widgets().items()
            if w.module == "tenants" or w.module in active
        ]
        for sort_order, (code, w) in enumerate(eligible):
            DashboardWidget.objects.update_or_create(
                tenant=tenant, widget_code=code,
                defaults={
                    "is_active": True,
                    "sort_order": sort_order,
                    "label_override": "",
                },
            )
        self._log(tenant, "statistics", f"{len(eligible)} widgets enabled")

    def _seed_hr(self, tenant: Tenant) -> None:
        from apps.hr.models import Employee, LeaveRequest
        from apps.org.models import Department

        # Look up departments seeded earlier; tolerant of missing ones.
        depts = {d.code: d for d in Department.objects.filter(tenant=tenant)}
        if tenant.slug == "globex":
            emp_specs = [
                ("E-001", "Alice Engineer", "ENG", "Senior Engineer"),
                ("E-002", "Bob Customer-Success", "CS", "CS Lead"),
                ("E-003", "Carla Finance", "FIN", "Finance Analyst"),
            ]
        else:  # initech
            emp_specs = [
                ("E-001", "Peter Gibbons", "ENG", "Software Engineer"),
                ("E-002", "Michael Bolton", "ENG", "Software Engineer"),
                ("E-003", "Samir Nagheenanajar", "ENG", "Software Engineer"),
                ("E-004", "Joanna Waitstaff", "OPS", "Office Manager"),
                ("E-005", "Bill Lumbergh", "OPS", "Operations Director"),
            ]
        today = date.today()
        for no, name, dept_code, position in emp_specs:
            Employee.objects.update_or_create(
                tenant=tenant, employee_no=no,
                defaults={
                    "name": name,
                    "department": depts.get(dept_code),
                    "hire_date": today.replace(year=today.year - 2),
                    "position": position,
                },
            )

        # A couple of leave requests for variety.
        first_emp = Employee.objects.filter(tenant=tenant).first()
        if first_emp:
            LeaveRequest.objects.update_or_create(
                tenant=tenant, employee=first_emp,
                start_date=today + timedelta(days=30),
                end_date=today + timedelta(days=34),
                defaults={"type": "annual", "status": LeaveRequest.Status.SUBMITTED},
            )
        self._log(tenant, "hr", f"{len(emp_specs)} employees, 1 leave request")

    def _seed_crm(self, tenant: Tenant, *, admin: User | None) -> None:
        from apps.crm.models import Customer, Lead, Opportunity

        if tenant.slug == "globex":
            cust_specs = [
                ("C-001", "Initech Corp", "purchasing@initech.example"),
                ("C-002", "Hooli Inc", "ap@hooli.example"),
                ("C-003", "Pied Piper", "billing@piedpiper.example"),
                ("C-004", "Massive Dynamic", "vendors@massive.example"),
            ]
        else:  # initech
            cust_specs = [
                ("C-001", "Initech Internal — Marketing", "marketing@initech.local"),
                ("C-002", "Initech Internal — Sales Ops", "salesops@initech.local"),
            ]
        cust_by_code = {}
        for code, name, email in cust_specs:
            c, _ = Customer.objects.update_or_create(
                tenant=tenant, code=code,
                defaults={
                    "name": name, "contact_email": email,
                    "contact_phone": "+1-555-0200",
                },
            )
            cust_by_code[code] = c

        # Leads
        lead_specs = [
            ("Stark Industries", "trade show", Lead.Status.NEW),
            ("Wayne Enterprises", "referral", Lead.Status.QUALIFIED),
            ("Oscorp", "website form", Lead.Status.LOST),
        ]
        for name, source, status in lead_specs:
            Lead.objects.update_or_create(
                tenant=tenant, name=name,
                defaults={"source": source, "status": status, "owner": admin},
            )

        # Opportunities tied to existing customers
        if cust_by_code:
            first_cust = next(iter(cust_by_code.values()))
            today = date.today()
            for stage, amount, days_out in [
                (Opportunity.Stage.PROSPECT, "12000.00", 60),
                (Opportunity.Stage.PROPOSAL, "45000.00", 30),
                (Opportunity.Stage.NEGOTIATION, "78000.00", 14),
            ]:
                Opportunity.objects.update_or_create(
                    tenant=tenant, customer=first_cust, stage=stage,
                    defaults={
                        "amount": Decimal(amount),
                        "expected_close": today + timedelta(days=days_out),
                    },
                )
        self._log(
            tenant, "crm",
            f"{len(cust_specs)} customers, {len(lead_specs)} leads, 3 opportunities",
        )

    def _seed_sales(self, tenant: Tenant) -> None:
        from apps.crm.models import Customer
        from apps.inventory.models import Item
        from apps.sales.models import Quote, SalesOrder, SalesOrderLine

        customer = Customer.objects.filter(tenant=tenant).first()
        if not customer:
            return
        items = list(Item.objects.filter(tenant=tenant)[:3])
        if not items:
            return

        # Quotes
        for i, (status, total) in enumerate([
            (Quote.Status.SENT, "5000.00"),
            (Quote.Status.ACCEPTED, "12500.00"),
        ]):
            Quote.objects.update_or_create(
                tenant=tenant, number=f"Q-{tenant.slug.upper()}-{i+1:03d}",
                defaults={"customer": customer, "status": status, "total": Decimal(total)},
            )

        # Sales orders with lines
        for i, (status, qty, price) in enumerate([
            (SalesOrder.Status.DRAFT, 5, "100.00"),
            (SalesOrder.Status.CONFIRMED, 10, "250.00"),
            (SalesOrder.Status.SHIPPED, 2, "1500.00"),
        ]):
            so, _ = SalesOrder.objects.update_or_create(
                tenant=tenant, number=f"SO-{tenant.slug.upper()}-{i+1:03d}",
                defaults={
                    "customer": customer, "status": status,
                    "total": Decimal(qty) * Decimal(price),
                },
            )
            SalesOrderLine.objects.update_or_create(
                tenant=tenant, order=so, item=items[i % len(items)],
                defaults={"qty": Decimal(qty), "unit_price": Decimal(price)},
            )
        self._log(tenant, "sales", "2 quotes, 3 sales orders with lines")

    def _seed_support_tickets(
        self, tenant: Tenant, *, admin: User | None, regular: User | None
    ) -> None:
        from apps.crm.models import Customer
        from apps.support_tickets.models import Ticket, TicketCategory, TicketReply

        cat_specs = [
            ("BILL", "Billing", admin),
            ("TECH", "Technical Support", regular),
            ("GEN", "General Inquiry", admin),
        ]
        cats = {}
        for code, name, assignee in cat_specs:
            c, _ = TicketCategory.objects.update_or_create(
                tenant=tenant, code=code,
                defaults={"name": name, "default_assignee": assignee, "is_active": True},
            )
            cats[code] = c

        customer = Customer.objects.filter(tenant=tenant).first() if "crm" in tenant.active_module_codes() else None
        ticket_specs = [
            ("T-001", "Invoice line items not adding up",
             "Customer reports that the totals on invoice INV-2026-014 don't match the sum of the lines.",
             cats["BILL"], Ticket.Priority.HIGH, Ticket.Status.OPEN),
            ("T-002", "Cannot reset password",
             "Login screen says 'invalid token' when clicking the reset link.",
             cats["TECH"], Ticket.Priority.NORMAL, Ticket.Status.IN_PROGRESS),
            ("T-003", "How to export reports as PDF",
             "Need step-by-step instructions for the new export feature.",
             cats["GEN"], Ticket.Priority.LOW, Ticket.Status.RESOLVED),
            ("T-004", "Urgent: production system down",
             "All users report 502 errors since 09:00.",
             cats["TECH"], Ticket.Priority.URGENT, Ticket.Status.OPEN),
        ]
        for number, subject, desc, cat, priority, status in ticket_specs:
            t, _ = Ticket.objects.update_or_create(
                tenant=tenant, number=number,
                defaults={
                    "subject": subject,
                    "description": desc,
                    "category": cat,
                    "customer": customer,
                    "reporter": regular,
                    "priority": priority,
                    "status": status,
                },
            )
            # One reply per ticket for the resolved/in-progress ones
            if status in (Ticket.Status.IN_PROGRESS, Ticket.Status.RESOLVED):
                TicketReply.objects.update_or_create(
                    tenant=tenant, ticket=t, author=admin,
                    defaults={
                        "body": f"Looking into this, will update by end of day.",
                        "is_internal": False,
                    },
                )
        self._log(
            tenant, "support_tickets",
            f"{len(cat_specs)} categories, {len(ticket_specs)} tickets",
        )

    def _seed_manufacturing(self, tenant: Tenant) -> None:
        from apps.inventory.models import Item
        from apps.manufacturing.models import BillOfMaterials, BOMLine, WorkOrder

        items = list(Item.objects.filter(tenant=tenant))
        if len(items) < 2:
            return
        parent = items[0]
        components = items[1:3]
        bom, _ = BillOfMaterials.objects.update_or_create(
            tenant=tenant, item=parent, version="1",
            defaults={"is_active": True},
        )
        for comp in components:
            BOMLine.objects.update_or_create(
                tenant=tenant, bom=bom, component_item=comp,
                defaults={"qty": Decimal("2"), "uom": "EA"},
            )

        today = date.today()
        for i, (status, qty) in enumerate([
            (WorkOrder.Status.PLANNED, 10),
            (WorkOrder.Status.IN_PROGRESS, 5),
        ]):
            WorkOrder.objects.update_or_create(
                tenant=tenant, number=f"WO-{tenant.slug.upper()}-{i+1:03d}",
                defaults={
                    "item": parent,
                    "qty": Decimal(qty),
                    "status": status,
                    "due_date": today + timedelta(days=14 + i*7),
                },
            )
        self._log(
            tenant, "manufacturing",
            f"1 BOM ({len(components)} lines), 2 work orders",
        )

    def _seed_documents(self, tenant: Tenant) -> None:
        from apps.documents.models import Folder, Tag

        folder_specs = ["Policies", "Procedures", "Customer Contracts", "Templates"]
        folders = {}
        for name in folder_specs:
            f, _ = Folder.objects.update_or_create(
                tenant=tenant, parent=None, name=name,
            )
            folders[name] = f
        # Sub-folder example
        Folder.objects.update_or_create(
            tenant=tenant, parent=folders["Policies"], name="HR Policies",
        )

        tag_specs = ["public", "internal", "confidential", "draft"]
        for name in tag_specs:
            Tag.objects.update_or_create(tenant=tenant, name=name)
        self._log(
            tenant, "documents",
            f"{len(folder_specs) + 1} folders, {len(tag_specs)} tags (no files — upload via UI)",
        )

    def _seed_projects(
        self, tenant: Tenant, *, admin: User | None, regular: User | None
    ) -> None:
        from apps.crm.models import Customer
        from apps.projects.models import Project, Timesheet
        from apps.tasks.models import Task

        customer = Customer.objects.filter(tenant=tenant).first() if "crm" in tenant.active_module_codes() else None
        today = date.today()
        project_specs = [
            ("PRJ-001", "Office IT Refresh", Project.Status.ACTIVE,
             today - timedelta(days=30), today + timedelta(days=60)),
            ("PRJ-002", "Annual Security Audit", Project.Status.PLANNED,
             today + timedelta(days=14), today + timedelta(days=45)),
        ]
        projects = {}
        for code, name, status, start, end in project_specs:
            p, _ = Project.objects.update_or_create(
                tenant=tenant, code=code,
                defaults={
                    "name": name, "customer": customer, "status": status,
                    "start_date": start, "end_date": end,
                },
            )
            projects[code] = p

        # Link some existing tasks to PRJ-001
        active_project = projects["PRJ-001"]
        tasks = Task.objects.filter(tenant=tenant, project__isnull=True).order_by("-id")[:2]
        for t in tasks:
            t.project = active_project
            t.save(update_fields=["project", "updated_at"])

        # Timesheets
        if regular:
            Timesheet.objects.update_or_create(
                tenant=tenant, user=regular, date=today - timedelta(days=1),
                defaults={
                    "task": Task.objects.filter(tenant=tenant, project=active_project).first(),
                    "hours": Decimal("6.5"),
                    "notes": "Server rack reorganisation and cabling.",
                },
            )
        self._log(
            tenant, "projects",
            f"{len(project_specs)} projects, 1 timesheet, {tasks.count()} tasks linked",
        )

    def _seed_assets(self, tenant: Tenant) -> None:
        from apps.assets.models import Asset, AssetCategory

        cat_specs = [
            ("IT", "IT Equipment", AssetCategory.DepreciationMethod.STRAIGHT_LINE, 36),
            ("FURN", "Office Furniture", AssetCategory.DepreciationMethod.STRAIGHT_LINE, 84),
        ]
        cats = {}
        for code, name, method, life in cat_specs:
            c, _ = AssetCategory.objects.update_or_create(
                tenant=tenant, code=code,
                defaults={
                    "name": name,
                    "depreciation_method": method,
                    "useful_life_months": life,
                },
            )
            cats[code] = c

        today = date.today()
        asset_specs = [
            ("FA-001", "MacBook Pro 16-inch", "IT", "2500.00", Asset.Status.IN_USE),
            ("FA-002", "Dell OptiPlex Desktop", "IT", "1200.00", Asset.Status.IN_USE),
            ("FA-003", "Conference Table, Large", "FURN", "1800.00", Asset.Status.IN_USE),
            ("FA-004", "Office Chairs (x10)", "FURN", "3500.00", Asset.Status.IN_USE),
            ("FA-005", "Old Laser Printer", "IT", "450.00", Asset.Status.DISPOSED),
        ]
        for no, name, cat_code, cost, status in asset_specs:
            Asset.objects.update_or_create(
                tenant=tenant, asset_no=no,
                defaults={
                    "name": name,
                    "category": cats[cat_code],
                    "acquisition_date": today.replace(year=today.year - 1),
                    "cost": Decimal(cost),
                    "location": "HQ",
                    "status": status,
                },
            )
        self._log(
            tenant, "assets",
            f"{len(cat_specs)} categories, {len(asset_specs)} fixed assets",
        )

    def _seed_automation(self, tenant: Tenant, *, admin: User | None) -> None:
        from apps.automation.models import Rule

        if not admin:
            return
        # Demo rule: notify the tenant admin whenever an inventory item is created.
        Rule.objects.update_or_create(
            tenant=tenant, name="Notify admin on new inventory item",
            defaults={
                "event_type": "inventory.item.created",
                "condition": {},
                "action_type": "send_notification",
                "action_params": {
                    "recipient_user_id": admin.pk,
                    "subject": "New inventory item",
                    "body": "Item {sku} '{name}' was just created.",
                },
                "is_active": True,
            },
        )
        # Second rule: log to activity when a high-value PO is approved.
        Rule.objects.update_or_create(
            tenant=tenant, name="Log high-value PO approvals",
            defaults={
                "event_type": "procurement.purchaseorder.updated",
                "condition": {"status": {"==": "APPROVED"}, "total": {">=": 1000}},
                "action_type": "log_activity",
                "action_params": {
                    "action": "procurement.po.approved.highvalue",
                    "note": "High-value purchase order approved",
                },
                "is_active": True,
            },
        )
        self._log(tenant, "automation", "2 rules configured")

    # ------------------------------------------------------------------
    # Team users + per-user activity
    # ------------------------------------------------------------------

    def _seed_team_users(self, tenant: Tenant) -> list[User]:
        """Create 2-5 users per team and 1-2 users per department.

        All new users go into the per-tenant ``Module Users`` group
        (`seed_demo` creates it), which has view perms on every module
        the tenant has active. They have no manage perms — making them a
        good fixture for the UI-gating behaviour as well as for
        activity-log volume.

        Returns the list of newly-created (or already-existing) users so
        the caller can drive activity generation against them.
        """
        import random
        from apps.org.models import Department, Membership, Team

        # Deterministic seed per tenant so re-runs are stable.
        rng = random.Random(f"team-users-{tenant.slug}")

        first_names = [
            "Alex", "Riley", "Jamie", "Casey", "Morgan", "Avery", "Quinn",
            "Sage", "Robin", "Drew", "Sam", "Jordan", "Taylor", "Kai", "Reese",
            "Parker", "Hayden", "Rowan", "Skyler", "Emerson",
        ]
        last_names = [
            "Smith", "Patel", "Garcia", "Lee", "Kim", "Brown", "Davis",
            "Wilson", "Lopez", "Martin", "Khan", "Singh", "Chen", "Nguyen",
            "Rossi", "Hassan", "Costa", "Yamamoto", "Andersen", "Bauer",
        ]

        # Locate the per-tenant Module Users group (created by seed_demo).
        mu_group_name = f"t{tenant.id}:Module Users"
        try:
            mu_group = Group.objects.get(name=mu_group_name)
        except Group.DoesNotExist:
            mu_group = None  # safe degradation; users still get created

        created_users: list[User] = []

        departments = list(Department.objects.filter(tenant=tenant))
        teams = list(Team.objects.filter(tenant=tenant))

        # 2-5 users per team
        for team in teams:
            n = rng.randint(2, 5)
            for i in range(n):
                username, first, last = self._pick_team_user(
                    tenant, team.code, i, rng, first_names, last_names,
                )
                user = self._ensure_team_user(tenant, username, first, last, mu_group)
                Membership.objects.update_or_create(
                    tenant=tenant, user=user, department=team.department, team=team,
                    defaults={"title": "Team Member", "is_head_of_department": False, "is_head_of_team": False},
                )
                created_users.append(user)

        # 1-2 users per department (no team — works for departments that
        # don't have a team yet, like Operations/Finance/etc.)
        for dept in departments:
            n = rng.randint(1, 2)
            for i in range(n):
                username, first, last = self._pick_team_user(
                    tenant, f"dept-{dept.code}", i, rng, first_names, last_names,
                )
                user = self._ensure_team_user(tenant, username, first, last, mu_group)
                Membership.objects.update_or_create(
                    tenant=tenant, user=user, department=dept, team=None,
                    defaults={"title": "Staff", "is_head_of_department": False, "is_head_of_team": False},
                )
                created_users.append(user)

        # Dedupe (a user can be created twice if their username happened
        # to be identical across teams/departments — extremely unlikely
        # given the RNG, but defensively dedupe by id).
        seen: dict[int, User] = {}
        for u in created_users:
            seen.setdefault(u.pk, u)
        created_users = list(seen.values())

        self._log(
            tenant, "team_users",
            f"{len(created_users)} team/dept users (Module Users group)",
        )
        return created_users

    def _pick_team_user(
        self, tenant: Tenant, scope: str, index: int,
        rng, first_names: list[str], last_names: list[str],
    ) -> tuple[str, str, str]:
        """Deterministically pick a (username, first_name, last_name) triple.

        The username is a slug-safe, tenant-unique identifier; the
        first/last names are stored on the User row so ``User.__str__``
        renders cleanly as "First Last" in dropdowns, activity logs,
        org membership tables, etc.
        """
        first = rng.choice(first_names)  # Capitalised already
        last = rng.choice(last_names)
        scope_slug = scope.lower().replace("-", "").replace("_", "")
        username = (
            f"{tenant.slug}-{scope_slug}-{first.lower()}-{last.lower()}-{index}"
        )[:150]
        return username, first, last

    def _ensure_team_user(
        self,
        tenant: Tenant,
        username: str,
        first_name: str,
        last_name: str,
        mu_group: Group | None,
    ) -> User:
        """Idempotent: get-or-create the user, ensure password+group set."""
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": f"{username}@{tenant.slug}.example",
                "tenant": tenant,
                "first_name": first_name,
                "last_name": last_name,
            },
        )
        if created:
            user.tenant = tenant
            user.set_password("pass")
            user.save()
        else:
            # Repair display names on existing rows so re-running fixes
            # users created by an earlier version of this command (which
            # parsed names out of the username slug awkwardly).
            updates = []
            if user.first_name != first_name:
                user.first_name = first_name
                updates.append("first_name")
            if user.last_name != last_name:
                user.last_name = last_name
                updates.append("last_name")
            if updates:
                user.save(update_fields=updates)
        if mu_group is not None and not user.groups.filter(pk=mu_group.pk).exists():
            user.groups.add(mu_group)
        return user

    # ------------------------------------------------------------------

    def _seed_activity_for_users(
        self, tenant: Tenant, users: list[User], *, active: set[str]
    ) -> None:
        """Backdate a realistic spread of ActivityLog rows for ``users``.

        Each user gets:
          * one or two AUTH login events,
          * 3-8 MODULE_READ rows targeting modules they can view, and
          * 0-3 MODULE_WRITE rows for modules where writes make sense.

        Rows are scattered over the last 7 days so the activity viewer
        (paginated, ordered by -timestamp) shows realistic content.
        """
        import random
        from apps.activity.models import ActivityLog

        if not users:
            return

        rng = random.Random(f"activity-{tenant.slug}")
        now = timezone.now()
        total = 0

        # Per-module "this is what users do here" template. Each entry
        # is (action_suffix, http_method, http_path_template).
        read_actions = {
            "finance": [("account.list", "GET", "/finance/account/")],
            "inventory": [
                ("item.list", "GET", "/inventory/item/"),
                ("warehouse.list", "GET", "/inventory/warehouse/"),
            ],
            "procurement": [
                ("supplier.list", "GET", "/procurement/supplier/"),
                ("purchaseorder.list", "GET", "/procurement/purchaseorder/"),
            ],
            "tasks": [
                ("task.list", "GET", "/tasks/task/"),
                ("my_tasks", "GET", "/tasks/my/"),
            ],
            "org": [
                ("department.list", "GET", "/org/department/"),
                ("team.list", "GET", "/org/team/"),
            ],
            "messaging": [("inbox", "GET", "/messaging/")],
            "statistics": [("dashboard", "GET", "/statistics/")],
            "hr": [("employee.list", "GET", "/hr/employee/")],
            "crm": [
                ("customer.list", "GET", "/crm/customer/"),
                ("lead.list", "GET", "/crm/lead/"),
            ],
            "sales": [
                ("salesorder.list", "GET", "/sales/salesorder/"),
                ("quote.list", "GET", "/sales/quote/"),
            ],
            "support_tickets": [
                ("ticket.list", "GET", "/support_tickets/ticket/"),
            ],
            "manufacturing": [
                ("billofmaterials.list", "GET", "/manufacturing/billofmaterials/"),
                ("workorder.list", "GET", "/manufacturing/workorder/"),
            ],
            "documents": [
                ("folder.list", "GET", "/documents/folder/"),
                ("document.list", "GET", "/documents/document/"),
            ],
            "projects": [
                ("project.list", "GET", "/projects/project/"),
                ("timesheet.list", "GET", "/projects/timesheet/"),
            ],
            "assets": [
                ("asset.list", "GET", "/assets/asset/"),
            ],
            "automation": [
                ("rule.list", "GET", "/automation/"),
            ],
        }

        # Write activities — only sensible for users who actually have
        # manage perms. Since team users only get view perms, we use these
        # to flavour the activity feed for the admin / regular users.
        # Restrict the write set to actions a typical tenant user might
        # perform (status updates on their assigned items).
        write_actions = {
            "tasks": [("task.update", "POST", "/tasks/task/{pk}/edit/")],
        }

        for user in users:
            # 1. Auth events: 1-3 logins per user backdated across the
            # last week.
            for offset_days in self._random_offsets(rng, 1, 3, 7):
                row = ActivityLog.objects.create(
                    tenant=tenant, actor=user,
                    actor_username_snapshot=user.username,
                    category=ActivityLog.Category.AUTH,
                    action="user.login",
                    request_method="POST",
                    request_path="/accounts/login/",
                    status_code=200,
                    ip_address="127.0.0.1",
                    user_agent="seed_demo_content/1.0",
                )
                # auto_now_add prevents passing timestamp on create;
                # backdate post-hoc via update().
                ActivityLog.objects.filter(pk=row.pk).update(
                    timestamp=now - timedelta(
                        days=offset_days,
                        hours=rng.randint(0, 23),
                        minutes=rng.randint(0, 59),
                    ),
                )
                total += 1

            # 2. Module reads — sample 3-8 per user across modules they
            # can view (= every active module on this tenant).
            user_modules = [m for m in active if m in read_actions]
            num_reads = rng.randint(3, 8)
            for _ in range(num_reads):
                if not user_modules:
                    break
                module = rng.choice(user_modules)
                action_suffix, method, path = rng.choice(read_actions[module])
                row = ActivityLog.objects.create(
                    tenant=tenant, actor=user,
                    actor_username_snapshot=user.username,
                    category=ActivityLog.Category.MODULE_READ,
                    action=f"{module}:{action_suffix}",
                    request_method=method,
                    request_path=f"/t/{tenant.slug}{path}",
                    status_code=200,
                    ip_address="127.0.0.1",
                    user_agent="seed_demo_content/1.0",
                )
                ActivityLog.objects.filter(pk=row.pk).update(
                    timestamp=now - timedelta(
                        days=rng.randint(0, 6),
                        hours=rng.randint(0, 23),
                        minutes=rng.randint(0, 59),
                    ),
                )
                total += 1

            # 3. Module writes — only sampled where it makes sense.
            num_writes = rng.randint(0, 3)
            for _ in range(num_writes):
                module = rng.choice(list(write_actions.keys()))
                if module not in active:
                    continue
                action_suffix, method, path = rng.choice(write_actions[module])
                fake_pk = rng.randint(1, 50)
                row = ActivityLog.objects.create(
                    tenant=tenant, actor=user,
                    actor_username_snapshot=user.username,
                    category=ActivityLog.Category.MODULE_WRITE,
                    action=f"{module}:{action_suffix}",
                    object_type=f"{module}.task",
                    object_id=str(fake_pk),
                    object_repr=f"Task #{fake_pk}",
                    request_method=method,
                    request_path=f"/t/{tenant.slug}{path.format(pk=fake_pk)}",
                    status_code=302,
                    ip_address="127.0.0.1",
                    user_agent="seed_demo_content/1.0",
                )
                ActivityLog.objects.filter(pk=row.pk).update(
                    timestamp=now - timedelta(
                        days=rng.randint(0, 6),
                        hours=rng.randint(0, 23),
                        minutes=rng.randint(0, 59),
                    ),
                )
                total += 1

        self._log(
            tenant, "activity",
            f"{total} backdated activity rows across {len(users)} team users",
        )

    def _random_offsets(self, rng, lo: int, hi: int, span_days: int) -> list[int]:
        """Return a small list of distinct day offsets in [0, span_days]."""
        n = rng.randint(lo, hi)
        return [rng.randint(0, span_days) for _ in range(n)]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, tenant: Tenant, module: str, msg: str) -> None:
        self.stdout.write(f"  {tenant.slug}.{module}: {msg}")
