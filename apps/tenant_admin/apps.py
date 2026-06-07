from django.apps import AppConfig


class TenantAdminConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenant_admin"
    label = "tenant_admin"
