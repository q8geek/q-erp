from __future__ import annotations

from django.db import models

from apps.core.models import TenantOwnedModel


class ManufacturingArea(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_manufacturing", "Can view manufacturing"),
            ("manage_manufacturing", "Can manage manufacturing"),
        )


class BillOfMaterials(TenantOwnedModel):
    item = models.ForeignKey("inventory.Item", on_delete=models.PROTECT, related_name="boms")
    version = models.CharField(max_length=16, default="1")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = (("tenant", "item", "version"),)
        ordering = ("-pk",)

    def __str__(self) -> str:
        return f"BOM {self.item} v{self.version}"


class BOMLine(TenantOwnedModel):
    bom = models.ForeignKey(BillOfMaterials, on_delete=models.CASCADE, related_name="lines")
    component_item = models.ForeignKey("inventory.Item", on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(max_digits=14, decimal_places=4, default=1)
    uom = models.CharField(max_length=16, default="EA")

    class Meta:
        ordering = ("pk",)
        indexes = [
            models.Index(fields=["tenant", "-id"]),
        ]

    def __str__(self) -> str:
        return f"{self.bom} · {self.component_item}"


class WorkOrder(TenantOwnedModel):
    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    number = models.CharField(max_length=32)
    item = models.ForeignKey("inventory.Item", on_delete=models.PROTECT, related_name="work_orders")
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=1)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    due_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = (("tenant", "number"),)
        ordering = ("-pk",)

    def __str__(self) -> str:
        return self.number
