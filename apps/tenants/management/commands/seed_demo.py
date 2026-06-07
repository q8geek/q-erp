"""Seed demo data: multiple plans, tenants, users for manual exploration."""
from __future__ import annotations

import os

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import SystemAdminTenant, User
from apps.tenants.models import Module, Plan, Subscription, Tenant, TenantGroup, TenantModule


CORE_CODES = [
    "finance", "inventory", "procurement",
    "org", "tasks", "messaging", "automation", "statistics",
]
ADDON_CODES = [
    "hr", "crm", "manufacturing", "documents", "sales", "projects", "assets",
    "support_tickets",
]


class Command(BaseCommand):
    help = "Seed demo plans, tenants, and users."

    def handle(self, *args, **options):
        if not settings.DEBUG and os.environ.get("ALLOW_SEED_DEMO") != "1":
            raise CommandError(
                "seed_demo refuses to run with DEBUG=False unless ALLOW_SEED_DEMO=1"
            )
        with transaction.atomic():
            self._ensure_modules()
            plans = self._ensure_plans()
            global_admin = self._ensure_global_admin()
            tenant_a = self._ensure_tenant("acme", "Acme Industries", plans["starter"], global_admin)
            tenant_b = self._ensure_tenant("globex", "Globex Corporation", plans["growth"], global_admin)
            tenant_c = self._ensure_tenant("initech", "Initech Systems", plans["enterprise"], global_admin)

        self.stdout.write(self.style.SUCCESS("Seed complete."))
        self.stdout.write("")
        self.stdout.write("Accounts:")
        self.stdout.write("  System admin (global): admin / admin")
        self.stdout.write("  Acme admin:            acme-admin / pass")
        self.stdout.write("  Acme user:             acme-user / pass")
        self.stdout.write("  Globex admin:          globex-admin / pass")
        self.stdout.write("  Initech admin:         initech-admin / pass")
        self.stdout.write("")
        self.stdout.write("URLs:")
        self.stdout.write("  /sys/                  -> system admin")
        self.stdout.write("  /t/acme/dashboard/     -> Acme (core only)")
        self.stdout.write("  /t/globex/dashboard/   -> Globex (core + a few add-ons)")
        self.stdout.write("  /t/initech/dashboard/  -> Initech (all modules)")

    def _ensure_modules(self):
        # Make sure sync_modules has run; if codes are missing, raise.
        existing = set(Module.objects.values_list("code", flat=True))
        missing = (set(CORE_CODES) | set(ADDON_CODES)) - existing
        if missing:
            self.stdout.write(self.style.WARNING(f"Missing modules: {missing}. Run sync_modules first."))

    def _ensure_plans(self):
        starter, _ = Plan.objects.update_or_create(
            code="starter", defaults={"name": "Starter (core only)", "seat_limit": 5, "price": 0}
        )
        starter.modules.set(Module.objects.filter(code__in=CORE_CODES))

        growth, _ = Plan.objects.update_or_create(
            code="growth", defaults={"name": "Growth (core + some add-ons)", "seat_limit": 20, "price": 99}
        )
        growth.modules.set(Module.objects.filter(code__in=CORE_CODES + ["hr", "crm", "sales", "support_tickets"]))

        enterprise, _ = Plan.objects.update_or_create(
            code="enterprise", defaults={"name": "Enterprise (all modules)", "seat_limit": 100, "price": 499}
        )
        enterprise.modules.set(Module.objects.filter(code__in=CORE_CODES + ADDON_CODES))

        return {"starter": starter, "growth": growth, "enterprise": enterprise}

    def _ensure_global_admin(self) -> User:
        user, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@q-erp.local",
                "is_staff": True,
                "is_superuser": True,
                "is_system_admin": True,
                "is_global_admin": True,
            },
        )
        if created or not user.has_usable_password():
            user.set_password("admin")
            user.is_system_admin = True
            user.is_global_admin = True
            user.tenant = None
            user.save()
        return user

    def _ensure_tenant(self, slug: str, name: str, plan: Plan, global_admin: User) -> Tenant:
        tenant, _ = Tenant.objects.get_or_create(slug=slug, defaults={"name": name})
        # Create subscription (the signal already attached core modules + tenant admin group)
        sub, _ = Subscription.objects.get_or_create(
            tenant=tenant, plan=plan, defaults={"is_active": True}
        )
        sub.is_active = True
        sub.save()
        # Activate plan modules on tenant
        for module in plan.modules.all():
            TenantModule.objects.get_or_create(tenant=tenant, module=module)

        # Create tenant admin user
        admin_username = f"{slug}-admin"
        admin_user, created = User.objects.get_or_create(
            username=admin_username,
            defaults={
                "email": f"{admin_username}@{slug}.example",
                "tenant": tenant,
            },
        )
        if created:
            admin_user.tenant = tenant
            admin_user.set_password("pass")
            admin_user.save()
        # Add to Tenant Administrators group
        tgroup = TenantGroup.objects.filter(tenant=tenant, is_system_managed=True).first()
        if tgroup:
            admin_user.groups.add(tgroup.group)

        # Create one regular user
        regular_username = f"{slug}-user"
        regular_user, created = User.objects.get_or_create(
            username=regular_username,
            defaults={"email": f"{regular_username}@{slug}.example", "tenant": tenant},
        )
        if created:
            regular_user.tenant = tenant
            regular_user.set_password("pass")
            regular_user.save()
            # Create a "Module Users" group with view perms for active modules
            group_name = f"t{tenant.id}:Module Users"
            mu_group, _ = Group.objects.get_or_create(name=group_name)
            TenantGroup.objects.get_or_create(
                tenant=tenant, group=mu_group, defaults={"description": "Read access to active modules."}
            )
            active_codes = list(tenant.active_module_codes())
            view_perms = Permission.objects.filter(
                content_type__app_label__in=active_codes, codename__startswith="view_"
            )
            mu_group.permissions.set(view_perms)
            regular_user.groups.add(mu_group)

        # Grant the global admin scoped access (no-op for global admin but tests the link path)
        # We skip SystemAdminTenant for global admin since they see everything.
        return tenant
