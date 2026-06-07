from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import TenantOwnedModel


class AutomationArea(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_automation", "Can view automation rules"),
            ("manage_automation", "Can manage automation rules"),
        )


class Rule(TenantOwnedModel):
    """A tenant-configured rule: when `event_type` fires, evaluate `condition`,
    and if it matches run `action_type` with `action_params`.
    """

    name = models.CharField(max_length=200)
    event_type = models.CharField(
        max_length=80,
        help_text="Event code (e.g. 'inventory.item.below_threshold').",
    )
    # Condition is a simple JSON object describing field comparisons against
    # the event payload. See apps/automation/conditions.py for the grammar.
    condition = models.JSONField(default=dict, blank=True)
    action_type = models.CharField(
        max_length=80,
        help_text="Action code (e.g. 'create_purchase_request').",
    )
    action_params = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run_status = models.CharField(max_length=20, blank=True)
    last_run_error = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)
        indexes = [
            models.Index(fields=["tenant", "event_type", "is_active"]),
        ]

    def __str__(self) -> str:
        return self.name


class RuleRun(TenantOwnedModel):
    """Audit record of a single rule firing."""

    class Status(models.TextChoices):
        MATCHED = "MATCHED", "Matched (action ran)"
        SKIPPED = "SKIPPED", "Condition not met"
        ERROR = "ERROR", "Action raised"

    rule = models.ForeignKey(Rule, on_delete=models.CASCADE, related_name="runs")
    event_type = models.CharField(max_length=80)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=Status.choices)
    error = models.TextField(blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ("-pk",)
        indexes = [
            models.Index(fields=["tenant", "rule", "-id"]),
            models.Index(fields=["tenant", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.rule} -> {self.status}"
