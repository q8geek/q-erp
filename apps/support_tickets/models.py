from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import TenantOwnedModel


class SupportTicketsArea(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_support_tickets", "Can view support tickets"),
            ("manage_support_tickets", "Can manage support tickets"),
        )


class TicketCategory(TenantOwnedModel):
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    default_assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = (("tenant", "code"),)
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class Ticket(TenantOwnedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        WAITING = "WAITING", "Waiting on customer"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    number = models.CharField(max_length=32)
    subject = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        TicketCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets"
    )
    customer = models.ForeignKey(
        "crm.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets"
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reported_tickets"
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tickets"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.NORMAL)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = (("tenant", "number"),)
        ordering = ("-pk",)
        indexes = [
            models.Index(fields=["tenant", "status", "-id"]),
            models.Index(fields=["tenant", "assignee", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.number} {self.subject}"

    def save(self, *args, **kwargs):
        # If the ticket has no assignee yet but its category specifies a
        # `default_assignee`, copy it across on create. This makes
        # `TicketCategory.default_assignee` functional through the generic
        # CRUD scaffold without needing a per-view override.
        if self.assignee_id is None and self.category_id is not None:
            default = getattr(self.category, "default_assignee_id", None)
            if default:
                self.assignee_id = default
        super().save(*args, **kwargs)


class TicketReply(TenantOwnedModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    body = models.TextField()
    is_internal = models.BooleanField(
        default=False, help_text="Internal notes are not visible to the customer."
    )

    class Meta:
        ordering = ("pk",)
        indexes = [
            models.Index(fields=["tenant", "-id"]),
        ]

    def __str__(self) -> str:
        return f"reply on {self.ticket}"
