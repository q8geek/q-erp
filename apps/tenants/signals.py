"""Tenant signals: auto-attach core modules and create reserved groups."""
from __future__ import annotations

from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Module, Tenant, TenantGroup, TenantModule, TenantSettings


RESERVED_TENANT_ADMIN_GROUP = "Tenant Administrators"


@receiver(post_save, sender=Tenant)
def on_tenant_created(sender, instance: Tenant, created: bool, **kwargs):
    if not created:
        return
    # 1. Create TenantSettings
    TenantSettings.objects.get_or_create(tenant=instance, defaults={"display_name": instance.name})

    # 2. Auto-attach all core modules
    for module in Module.objects.filter(is_core=True):
        TenantModule.objects.get_or_create(tenant=instance, module=module)

    # 3. Create reserved "Tenant Administrators" group
    group_name = f"t{instance.id}:{RESERVED_TENANT_ADMIN_GROUP}"
    group, _ = Group.objects.get_or_create(name=group_name)
    # Grant tenants.manage_tenant
    try:
        perm = Permission.objects.get(codename="manage_tenant", content_type__app_label="tenants")
        group.permissions.add(perm)
    except Permission.DoesNotExist:
        pass
    TenantGroup.objects.get_or_create(
        tenant=instance,
        group=group,
        defaults={
            "is_system_managed": True,
            "description": "Built-in tenant administrators group (auto-created).",
        },
    )
