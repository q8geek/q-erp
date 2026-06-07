from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import TenantOwnedModel


class CrmArea(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_crm", "Can view CRM"),
            ("manage_crm", "Can manage CRM"),
        )


class Lead(TenantOwnedModel):
    class Status(models.TextChoices):
        NEW = "NEW", "New"
        QUALIFIED = "QUALIFIED", "Qualified"
        CONVERTED = "CONVERTED", "Converted"
        LOST = "LOST", "Lost"

    name = models.CharField(max_length=200)
    source = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ("-pk",)
        indexes = [
            models.Index(fields=["tenant", "-id"]),
        ]

    def __str__(self) -> str:
        return self.name


class Customer(TenantOwnedModel):
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=64, blank=True)

    class Meta:
        unique_together = (("tenant", "code"),)
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class Opportunity(TenantOwnedModel):
    class Stage(models.TextChoices):
        PROSPECT = "PROSPECT", "Prospect"
        PROPOSAL = "PROPOSAL", "Proposal"
        NEGOTIATION = "NEGOTIATION", "Negotiation"
        WON = "WON", "Won"
        LOST = "LOST", "Lost"

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="opportunities")
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.PROSPECT)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    expected_close = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("-pk",)
        indexes = [
            models.Index(fields=["tenant", "-id"]),
        ]

    def __str__(self) -> str:
        return f"Opp {self.pk}: {self.customer}"
