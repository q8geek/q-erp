from __future__ import annotations

from django.db import models

from apps.core.models import TenantOwnedModel


class FinanceArea(models.Model):
    """Marker model — provides a content type for finance custom permissions."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_finance", "Can view finance"),
            ("manage_finance", "Can manage finance"),
        )


class Account(TenantOwnedModel):
    class Type(models.TextChoices):
        ASSET = "ASSET", "Asset"
        LIABILITY = "LIABILITY", "Liability"
        EQUITY = "EQUITY", "Equity"
        REVENUE = "REVENUE", "Revenue"
        EXPENSE = "EXPENSE", "Expense"

    code = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.ASSET)
    parent = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = (("tenant", "code"),)
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} {self.name}"
