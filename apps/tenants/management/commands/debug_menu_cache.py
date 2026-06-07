"""Diagnostic: dump the menu cache + reorder state for a tenant.

Used to debug 'reorder doesn't reflect on the sidebar' bugs in deployed
environments (where the test client isn't available). Prints:

  * DB-side TenantModule order (what the next cache miss WILL produce).
  * Current menu_ver counter (the version-namespace integer).
  * Cached menu structure for each known user of the tenant, if present.
  * The exact cache key each of those users would look up next.

Run on PythonAnywhere:
    cd ~/q-erp
    workon qerp
    export DJANGO_SETTINGS_MODULE=qerp.settings.pythonanywhere
    export DJANGO_SECRET_KEY=...   # whatever you used in the WSGI file
    export DJANGO_ALLOWED_HOSTS=q8geek.pythonanywhere.com
    python manage.py debug_menu_cache --tenant acme
"""
from __future__ import annotations

from django.core.cache import cache
from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.core.context_processors import _menu_ver_key, menu_cache_key
from apps.tenants.models import Tenant, TenantModule


class Command(BaseCommand):
    help = "Inspect TenantModule order + the Django cache state used by the sidebar."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant", required=True, help="Tenant slug to inspect (e.g. acme)."
        )
        parser.add_argument(
            "--invalidate",
            action="store_true",
            help="After dumping, call invalidate_menu_for_tenant() and dump again.",
        )

    def handle(self, *args, **options):
        try:
            tenant = Tenant.objects.get(slug=options["tenant"])
        except Tenant.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"No tenant with slug {options['tenant']!r}"))
            return

        self._dump(tenant)

        if options["invalidate"]:
            from apps.core.context_processors import invalidate_menu_for_tenant

            self.stdout.write("\n--- invalidate_menu_for_tenant() ---\n")
            invalidate_menu_for_tenant(tenant.id)
            self._dump(tenant)

    def _dump(self, tenant: Tenant) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== Tenant: {tenant.slug} ==="))

        # Cache backend identity (which backend is actually configured?).
        from django.conf import settings as dj_settings
        backend = dj_settings.CACHES["default"]["BACKEND"]
        location = dj_settings.CACHES["default"].get("LOCATION", "")
        self.stdout.write(f"Cache backend: {backend}  location={location!r}")

        # Menu version counter — the key that gets bumped on invalidation.
        ver_key = _menu_ver_key(tenant.id)
        ver = cache.get(ver_key)
        self.stdout.write(f"Menu version key: {ver_key!r} = {ver!r}")

        # DB-side TenantModule order: what the next cache miss will use.
        self.stdout.write("\nDB order (what a fresh menu build would render):")
        rows = (
            TenantModule.objects
            .filter(tenant=tenant, disabled_at__isnull=True)
            .select_related("module")
            .order_by("sort_order", "module__name")
        )
        for tm in rows:
            self.stdout.write(
                f"  sort_order={tm.sort_order:>4}  pk={tm.pk:<4}  "
                f"is_core={tm.module.is_core}  {tm.module.code}  ({tm.module.name})"
            )

        # Per-user cached menu state.
        users = list(User.objects.filter(tenant=tenant).order_by("username"))
        self.stdout.write(f"\nKnown tenant users: {len(users)}")
        for user in users:
            key = menu_cache_key(tenant.id, user.id)
            cached = cache.get(key)
            if cached is None:
                self.stdout.write(f"  {user.username}: NO CACHE (cold)  key={key!r}")
            else:
                codes = [item.get("code") for item in cached]
                self.stdout.write(
                    f"  {user.username}: CACHED {len(cached)} items: {codes}  key={key!r}"
                )
