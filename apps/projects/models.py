from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import TenantOwnedModel


class ProjectsArea(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_projects", "Can view projects"),
            ("manage_projects", "Can manage projects"),
        )


class Project(TenantOwnedModel):
    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        ACTIVE = "ACTIVE", "Active"
        ON_HOLD = "ON_HOLD", "On hold"
        DONE = "DONE", "Done"

    code = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    customer = models.ForeignKey("crm.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="projects")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = (("tenant", "code"),)
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class Timesheet(TenantOwnedModel):
    """Time entry; can be linked to a Task (which itself may belong to a Project)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    date = models.DateField()
    task = models.ForeignKey(
        "tasks.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="timesheets",
    )
    hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-date", "-pk")
        indexes = [
            models.Index(fields=["tenant", "-id"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} {self.date} {self.hours}h"
