from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import SystemAdminTenant, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "tenant", "is_system_admin", "is_global_admin", "is_active", "is_disabled")
    list_filter = ("is_system_admin", "is_global_admin", "is_active", "is_disabled", "tenant")
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "Tenancy",
            {"fields": ("tenant", "is_system_admin", "is_global_admin", "is_disabled", "phone", "last_seen_at")},
        ),
    )


@admin.register(SystemAdminTenant)
class SystemAdminTenantAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "granted_at", "granted_by")
    list_filter = ("tenant",)
