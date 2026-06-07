"""Canonical task model.

Tasks can be:
- Project-linked (Task.project is set) — used by apps/projects.
- Personal/standalone (Task.project is NULL).

Other modules (support_tickets actions, automation rules, etc.)
target Task as a first-class object.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import TenantOwnedModel


class TasksArea(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_tasks", "Can view tasks"),
            ("manage_tasks", "Can manage tasks"),
        )


class Task(TenantOwnedModel):
    class Status(models.TextChoices):
        TODO = "TODO", "To do"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        BLOCKED = "BLOCKED", "Blocked"
        DONE = "DONE", "Done"
        CANCELLED = "CANCELLED", "Cancelled"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
        help_text="Optional project link; NULL means a personal/standalone task.",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TODO)
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.NORMAL)
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-pk",)
        indexes = [
            models.Index(fields=["tenant", "assignee", "status"]),
            models.Index(fields=["tenant", "project", "status"]),
            models.Index(fields=["tenant", "-id"]),
        ]

    def __str__(self) -> str:
        return self.title
