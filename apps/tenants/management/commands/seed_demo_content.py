"""Populate the three demo tenants with realistic per-module content.

Run AFTER `seed_demo`. Idempotent: every row is created via `get_or_create`
or `update_or_create`, so re-running won't duplicate data.

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

Usage on PythonAnywhere:
    export ALLOW_SEED_DEMO=1
    python manage.py seed_demo_content
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
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
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, tenant: Tenant, module: str, msg: str) -> None:
        self.stdout.write(f"  {tenant.slug}.{module}: {msg}")
