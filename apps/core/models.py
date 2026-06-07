"""Abstract base models and managers for tenant-owned data."""
from __future__ import annotations

from django.conf import settings
from django.db import models

from .scope import get_current_tenant


class TenantQuerySet(models.QuerySet):
    pass


class TenantManager(models.Manager):
    """Default manager that scopes querysets to the current tenant."""

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_current_tenant()
        if tenant is None:
            # No tenant in scope -> return empty (prevents accidental leakage).
            # Code paths that need cross-tenant access must use `.unscoped`.
            return qs.none()
        return qs.filter(tenant=tenant)


class UnscopedManager(models.Manager):
    """Explicit cross-tenant access; for system admin code only."""

    def get_queryset(self):
        return super().get_queryset()


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantOwnedModel(TimestampedModel):
    """Abstract base for any tenant-owned domain row."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="+",
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        abstract = True
