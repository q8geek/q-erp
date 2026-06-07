from __future__ import annotations

from django.db import models

from apps.core.models import TenantOwnedModel


class HrArea(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_hr", "Can view HR"),
            ("manage_hr", "Can manage HR"),
        )


class Employee(TenantOwnedModel):
    employee_no = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    department = models.ForeignKey(
        "org.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )
    hire_date = models.DateField(null=True, blank=True)
    position = models.CharField(max_length=120, blank=True)

    class Meta:
        unique_together = (("tenant", "employee_no"),)
        ordering = ("employee_no",)

    def __str__(self) -> str:
        return f"{self.employee_no} {self.name}"


class LeaveRequest(TenantOwnedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_requests")
    type = models.CharField(max_length=40, default="annual")
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        ordering = ("-start_date",)
        indexes = [
            models.Index(fields=["tenant", "-id"]),
        ]

    def __str__(self) -> str:
        return f"{self.employee} {self.type} {self.start_date}"
