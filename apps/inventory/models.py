from __future__ import annotations

from django.db import models

from apps.core.models import TenantOwnedModel


class InventoryArea(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_inventory", "Can view inventory"),
            ("manage_inventory", "Can manage inventory"),
        )


class Warehouse(TenantOwnedModel):
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = (("tenant", "code"),)
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class Item(TenantOwnedModel):
    sku = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    uom = models.CharField(max_length=16, default="EA")
    default_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.SET_NULL, null=True, blank=True, related_name="items"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = (("tenant", "sku"),)
        ordering = ("sku",)

    def __str__(self) -> str:
        return f"{self.sku} {self.name}"
