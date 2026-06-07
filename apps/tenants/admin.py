from django.contrib import admin

from .models import Module, Plan, Subscription, Tenant, TenantGroup, TenantModule, TenantSettings


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "is_active", "created_at")
    search_fields = ("slug", "name")
    list_filter = ("is_active",)


@admin.register(TenantSettings)
class TenantSettingsAdmin(admin.ModelAdmin):
    list_display = ("tenant", "currency_code", "timezone")


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_core")
    list_filter = ("is_core",)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "seat_limit", "is_active", "price")
    filter_horizontal = ("modules",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("tenant", "plan", "seat_limit_override", "is_active", "starts_at", "ends_at")


@admin.register(TenantModule)
class TenantModuleAdmin(admin.ModelAdmin):
    list_display = ("tenant", "module", "enabled_at", "disabled_at")
    list_filter = ("module",)


@admin.register(TenantGroup)
class TenantGroupAdmin(admin.ModelAdmin):
    list_display = ("tenant", "group", "is_system_managed")
