from __future__ import annotations

from django.db import models

from apps.core.models import TenantOwnedModel


class SalesArea(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_sales", "Can view sales"),
            ("manage_sales", "Can manage sales"),
        )


class Quote(TenantOwnedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SENT = "SENT", "Sent"
        ACCEPTED = "ACCEPTED", "Accepted"
        REJECTED = "REJECTED", "Rejected"

    number = models.CharField(max_length=32)
    customer = models.ForeignKey("crm.Customer", on_delete=models.PROTECT, related_name="quotes")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        unique_together = (("tenant", "number"),)
        ordering = ("-pk",)

    def __str__(self) -> str:
        return self.number


class SalesOrder(TenantOwnedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CONFIRMED = "CONFIRMED", "Confirmed"
        SHIPPED = "SHIPPED", "Shipped"
        CANCELLED = "CANCELLED", "Cancelled"

    number = models.CharField(max_length=32)
    customer = models.ForeignKey("crm.Customer", on_delete=models.PROTECT, related_name="sales_orders")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        unique_together = (("tenant", "number"),)
        ordering = ("-pk",)

    def __str__(self) -> str:
        return self.number


class SalesOrderLine(TenantOwnedModel):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey("inventory.Item", on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ("pk",)
        indexes = [
            models.Index(fields=["tenant", "-id"]),
        ]

    def __str__(self) -> str:
        return f"{self.order} · {self.item}"
