from __future__ import annotations

from django.conf import settings
from django.db import models


class ActivityLog(models.Model):
    class Category(models.TextChoices):
        AUTH = "AUTH", "Auth"
        TENANT_ADMIN = "TENANT_ADMIN", "Tenant admin"
        SYSTEM_ADMIN = "SYSTEM_ADMIN", "System admin"
        MODULE_READ = "MODULE_READ", "Module read"
        MODULE_WRITE = "MODULE_WRITE", "Module write"
        OTHER = "OTHER", "Other"

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.SET_NULL, null=True, blank=True, related_name="activity_logs"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="activity_logs"
    )
    actor_username_snapshot = models.CharField(max_length=150, blank=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    action = models.CharField(max_length=120)
    object_type = models.CharField(max_length=120, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    ip_address = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    request_method = models.CharField(max_length=10, blank=True)
    request_path = models.CharField(max_length=512, blank=True)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    extra = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "-timestamp"]),
            models.Index(fields=["tenant", "category", "-timestamp"]),
            models.Index(fields=["actor", "-timestamp"]),
        ]
        ordering = ("-timestamp",)

    def __str__(self) -> str:
        who = self.actor_username_snapshot or "anon"
        return f"[{self.timestamp:%Y-%m-%d %H:%M:%S}] {who} {self.action}"
