"""Tenant-configurable organisational structure.

`Department` is a hierarchical org unit (e.g. Engineering > Backend).
`Team` is a flat grouping of users that lives under a department.
`Membership` is the user <-> department/team link and carries the
`is_head` flag that lets triggers target heads-of-X.

Heads-of-X are pure metadata in this prototype: they have no automatic
permission-scope consequences (per the explicit decision in the plan
discussion). Triggers may use them as action recipients.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import TenantOwnedModel


class OrgArea(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_org", "Can view organisation"),
            ("manage_org", "Can manage organisation"),
        )


class Department(TenantOwnedModel):
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = (("tenant", "code"),)
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class Team(TenantOwnedModel):
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="teams"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = (("tenant", "code"),)
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class Membership(TenantOwnedModel):
    """A user's membership of a department and optionally a team.

    A user can have multiple memberships (e.g. one per team they sit in).
    `is_head_of_department` / `is_head_of_team` flag this row as the
    head for that scope; uniqueness is enforced per scope (one head per
    department, one head per team).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memberships",
    )
    title = models.CharField(max_length=120, blank=True)
    is_head_of_department = models.BooleanField(default=False)
    is_head_of_team = models.BooleanField(default=False)

    class Meta:
        ordering = ("department__code", "team__code", "user__username")
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "user", "department", "team"),
                name="org_membership_unique_scope",
            ),
            models.UniqueConstraint(
                fields=("tenant", "department"),
                condition=models.Q(is_head_of_department=True),
                name="org_membership_one_head_per_department",
            ),
            models.UniqueConstraint(
                fields=("tenant", "team"),
                condition=models.Q(is_head_of_team=True, team__isnull=False),
                name="org_membership_one_head_per_team",
            ),
        ]

    def __str__(self) -> str:
        if self.team_id:
            return f"{self.user} @ {self.team} ({self.department})"
        return f"{self.user} @ {self.department}"


def head_of(*, tenant, department: Department | None = None, team: Team | None = None):
    """Return the User who is head of the given department or team within `tenant`.

    Exactly one of `department` / `team` must be provided. `tenant` is required to
    prevent cross-tenant lookups. Returns None when no head is set.
    """
    if (department is None) == (team is None):
        raise ValueError("Exactly one of department/team must be provided.")
    qs = Membership.objects.filter(tenant=tenant)
    if department is not None:
        qs = qs.filter(department=department, is_head_of_department=True)
    else:
        qs = qs.filter(team=team, is_head_of_team=True)
    m = qs.select_related("user").first()
    return m.user if m else None


def head_of_department(department: Department, *, tenant):
    """Back-compat thin wrapper around :func:`head_of`.

    `tenant` is required to prevent cross-tenant lookups.
    """
    return head_of(tenant=tenant, department=department)


def head_of_team(team: Team, *, tenant):
    """Back-compat thin wrapper around :func:`head_of`.

    `tenant` is required to prevent cross-tenant lookups.
    """
    return head_of(tenant=tenant, team=team)
