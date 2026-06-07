from __future__ import annotations

from django.db import models

from apps.core.models import TenantOwnedModel


class ProcurementArea(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_procurement", "Can view procurement"),
            ("manage_procurement", "Can manage procurement"),
        )


class Supplier(TenantOwnedModel):
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = (("tenant", "code"),)
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class PurchaseOrder(TenantOwnedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"

    number = models.CharField(max_length=32)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        unique_together = (("tenant", "number"),)
        ordering = ("-pk",)

    def __str__(self) -> str:
        return self.number
