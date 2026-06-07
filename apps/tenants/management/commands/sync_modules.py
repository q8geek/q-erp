"""Idempotently sync module_meta.py declarations into Module and auth_permission rows.

Also back-fills `is_core=True` modules onto every existing tenant, so that
promoting a module to core (or adding a new core module to the catalog)
attaches it to tenants created before the change.
"""
from __future__ import annotations

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.tenants.models import Module, Tenant, TenantModule
from apps.tenants.registry import iter_module_metas


class Command(BaseCommand):
    help = "Sync module catalog (Module rows + Permission rows) from each app's module_meta.py."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-backfill",
            action="store_true",
            help="Do not back-fill core modules onto existing tenants.",
        )
        parser.add_argument(
            "--prune",
            action="store_true",
            help=(
                "Delete Module rows whose `code` is no longer declared by "
                "any installed app's module_meta.py."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what --prune would delete without committing.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Required to actually delete rows when --prune is used (must be combined with --prune; ignored otherwise).",
        )

    def handle(self, *args, **options):
        if options["prune"] and not options["dry_run"] and not options["yes"]:
            raise CommandError(
                "Refusing to prune without --yes (or use --dry-run)."
            )
        created_modules = 0
        updated_modules = 0
        created_perms = 0
        declared_codes: set[str] = set()
        with transaction.atomic():
            for meta in iter_module_metas():
                declared_codes.add(meta["code"])
                code = meta["code"]
                name = meta["name"]
                description = meta.get("description", "")
                is_core = bool(meta.get("is_core", False))
                module, was_created = Module.objects.update_or_create(
                    code=code,
                    defaults={"name": name, "description": description, "is_core": is_core},
                )
                if was_created:
                    created_modules += 1
                else:
                    updated_modules += 1
                # Permissions
                app_label = meta.get("app_label", code)
                content_type = self._get_module_content_type(app_label, code)
                for codename, label in meta.get("permissions", []):
                    perm, p_created = Permission.objects.get_or_create(
                        codename=codename,
                        content_type=content_type,
                        defaults={"name": label},
                    )
                    if p_created:
                        created_perms += 1
                    elif perm.name != label:
                        perm.name = label
                        perm.save(update_fields=["name"])

            attached = 0
            if not options["skip_backfill"]:
                attached = self._backfill_core_modules()

            pruned = 0
            if options["prune"]:
                # Compute what WOULD have been pruned without the core guard
                # so we can warn the operator about protected codes.
                all_stale = Module.objects.exclude(code__in=declared_codes)
                protected_codes = list(
                    all_stale.filter(is_core=True).values_list("code", flat=True)
                )
                if protected_codes:
                    self.stdout.write(
                        self.style.WARNING(
                            "Protected core modules skipped by --prune: "
                            + ", ".join(protected_codes)
                        )
                    )
                stale_qs = all_stale.exclude(is_core=True)
                stale_codes = list(stale_qs.values_list("code", flat=True))
                if options["dry_run"]:
                    if stale_codes:
                        self.stdout.write(
                            "Would prune (dry-run): " + ", ".join(stale_codes)
                        )
                    else:
                        self.stdout.write("Would prune (dry-run): <nothing>")
                else:
                    pruned, _ = stale_qs.delete()
                    if stale_codes:
                        self.stdout.write(
                            f"Pruned {pruned} stale modules: " + ", ".join(stale_codes)
                        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Modules created={created_modules} updated={updated_modules}; "
                f"new permissions={created_perms}; "
                f"core back-fill attachments={attached}; "
                f"pruned={pruned if options['prune'] and not options['dry_run'] else 0}"
            )
        )

    def _backfill_core_modules(self) -> int:
        """Ensure every existing tenant has a TenantModule row for every
        `is_core=True` module. Returns the number of new attachments.
        """
        core_modules = list(Module.objects.filter(is_core=True))
        if not core_modules:
            return 0
        attached = 0
        for tenant in Tenant.objects.all():
            for module in core_modules:
                _, created = TenantModule.objects.get_or_create(tenant=tenant, module=module)
                if created:
                    attached += 1
        return attached

    def _get_module_content_type(self, app_label: str, module_code: str) -> ContentType:
        from django.apps import apps as django_apps

        # Look for the marker model named <Code>Area (e.g. FinanceArea).
        target_model_name = f"{module_code}area"
        try:
            app_config = django_apps.get_app_config(app_label)
        except LookupError:
            app_config = None
        if app_config:
            for model in app_config.get_models(include_auto_created=False):
                if model._meta.model_name == target_model_name:
                    return ContentType.objects.get_for_model(model)
        # Fallback: attach to Module
        return ContentType.objects.get_for_model(Module)
