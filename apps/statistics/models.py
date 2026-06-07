from __future__ import annotations

from django.db import models

from apps.core.models import TenantOwnedModel


class StatisticsArea(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_statistics", "Can view statistics"),
            ("manage_statistics", "Can configure statistics"),
        )


class DashboardWidget(TenantOwnedModel):
    """A widget configured to appear on this tenant's statistics page."""

    widget_code = models.CharField(max_length=64)
    label_override = models.CharField(max_length=120, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = (("tenant", "widget_code"),)
        ordering = ("sort_order", "pk")

    def __str__(self) -> str:
        return self.label_override or self.widget_code
