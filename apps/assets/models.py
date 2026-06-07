from __future__ import annotations

from django.db import models

from apps.core.models import TenantOwnedModel


class AssetsArea(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_assets", "Can view assets"),
            ("manage_assets", "Can manage assets"),
        )


class AssetCategory(TenantOwnedModel):
    class DepreciationMethod(models.TextChoices):
        STRAIGHT_LINE = "STRAIGHT_LINE", "Straight line"
        REDUCING_BALANCE = "REDUCING_BALANCE", "Reducing balance"

    code = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    depreciation_method = models.CharField(
        max_length=20, choices=DepreciationMethod.choices, default=DepreciationMethod.STRAIGHT_LINE
    )
    useful_life_months = models.PositiveIntegerField(default=60)

    class Meta:
        unique_together = (("tenant", "code"),)
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class Asset(TenantOwnedModel):
    class Status(models.TextChoices):
        IN_USE = "IN_USE", "In use"
        IN_STORAGE = "IN_STORAGE", "In storage"
        DISPOSED = "DISPOSED", "Disposed"
        UNDER_REPAIR = "UNDER_REPAIR", "Under repair"

    asset_no = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    category = models.ForeignKey(AssetCategory, on_delete=models.PROTECT, related_name="assets")
    acquisition_date = models.DateField(null=True, blank=True)
    cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    location = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.IN_USE)

    class Meta:
        unique_together = (("tenant", "asset_no"),)
        ordering = ("asset_no",)

    def __str__(self) -> str:
        return f"{self.asset_no} {self.name}"
