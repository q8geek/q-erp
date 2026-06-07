"""User model and system admin assignment."""
from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


# Q expressions describing the *valid* User rows under each generation of the
# tenant/system-admin XOR rule. Exposed at module scope so that the
# corresponding migrations can run a pre-flight check against existing rows
# instead of letting the CheckConstraint blow up with a bare IntegrityError.
#
# USER_XOR_VALID_Q_V1: the original 0003 rule.
# USER_XOR_VALID_Q_V2: the extended 0004 rule (adds the is_global_admin clauses).
# USER_XOR_VIOLATOR_Q_V{1,2}: the negation, i.e. the rows the check would reject.
USER_XOR_VALID_Q_V1 = (
    models.Q(is_system_admin=True, tenant__isnull=True)
    | models.Q(is_system_admin=False, tenant__isnull=False)
    | models.Q(is_superuser=True, is_system_admin=False, tenant__isnull=True)
)
USER_XOR_VIOLATOR_Q_V1 = ~USER_XOR_VALID_Q_V1

USER_XOR_VALID_Q_V2 = (
    models.Q(is_system_admin=True, tenant__isnull=True)
    | models.Q(
        is_global_admin=False, is_system_admin=False, tenant__isnull=False
    )
    | models.Q(
        is_global_admin=False,
        is_superuser=True,
        is_system_admin=False,
        tenant__isnull=True,
    )
)
USER_XOR_VIOLATOR_Q_V2 = ~USER_XOR_VALID_Q_V2


class User(AbstractUser):
    """Custom user attached to at most one tenant.

    A system admin has `tenant=NULL` and `is_system_admin=True`. Tenant users
    have a non-null `tenant` and `is_system_admin=False`. The two are mutually
    exclusive (enforced in `clean()`).
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="users",
    )
    is_system_admin = models.BooleanField(default=False)
    is_global_admin = models.BooleanField(
        default=False,
        help_text="If true, the system admin sees all tenants (no SystemAdminTenant rows needed).",
    )
    is_disabled = models.BooleanField(
        default=False,
        help_text="Tenant-side disable flag (distinct from is_active which is system-level).",
    )
    phone = models.CharField(max_length=64, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        constraints = [
            # Source of truth: ``USER_XOR_VALID_Q_V2`` at module scope.
            # Migrations 0003/0004 and tooling read the same Q so the
            # constraint condition and the pre-flight check cannot drift.
            models.CheckConstraint(
                name="user_tenant_xor_system_admin",
                condition=USER_XOR_VALID_Q_V2,
            ),
        ]

    def __str__(self) -> str:
        # Display priority: "First Last" > "First" > "Last" > username > email.
        # The previous implementation defaulted to email which exposed the
        # internal `<user>@<tenant>.example` format on demo deployments.
        first = (self.first_name or "").strip()
        last = (self.last_name or "").strip()
        if first and last:
            return f"{first} {last}"
        if first:
            return first
        if last:
            return last
        if self.username:
            return self.username
        if self.email:
            return self.email
        return f"user#{self.pk}"

    def clean(self):
        super().clean()
        if self.is_system_admin and self.tenant_id:
            raise ValidationError("System admins must not be attached to a tenant.")
        if not self.is_system_admin and not self.tenant_id and not self.is_superuser:
            # Allow superuser without tenant for bootstrap, but require either system_admin or tenant
            raise ValidationError("A user must either be a system admin or belong to a tenant.")
        if self.is_global_admin and not self.is_system_admin:
            raise ValidationError("is_global_admin requires is_system_admin.")

    def save(self, *args, _skip_clean: bool = False, **kwargs):
        """Defense in depth: enforce `clean()` invariants on every save.

        Pass `_skip_clean=True` from bootstrap/management paths that build a
        User in stages and need to defer validation (e.g. createsuperuser
        leaving fields unset until the prompts complete).
        """
        if not _skip_clean:
            self.full_clean(exclude=["password"])
        super().save(*args, **kwargs)

    def accessible_tenants(self):
        """Return queryset of tenants the user can act on (system admins only)."""
        from apps.tenants.models import Tenant

        if not self.is_system_admin:
            return Tenant.objects.none()
        if self.is_global_admin:
            return Tenant.objects.all()
        return Tenant.objects.filter(system_admin_links__user=self)


class SystemAdminTenant(models.Model):
    """Grants a non-global system admin access to a specific tenant."""

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="system_admin_links",
        limit_choices_to={"is_system_admin": True, "is_global_admin": False},
    )
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="system_admin_links",
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    granted_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_system_admin_links",
    )

    class Meta:
        unique_together = (("user", "tenant"),)
        verbose_name = "System admin tenant assignment"
        verbose_name_plural = "System admin tenant assignments"

    def __str__(self) -> str:
        return f"{self.user} -> {self.tenant}"
