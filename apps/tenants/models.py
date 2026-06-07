"""Core tenancy models: Tenant, TenantSettings, Module, Plan, Subscription, TenantModule, TenantGroup."""
from __future__ import annotations

from django.contrib.auth.models import Group
from django.db import models
from django.utils import timezone


class Tenant(models.Model):
    """The tenancy root.

    There is no per-tenant scoping to apply on this table — every row IS a
    tenant — so `Tenant.objects` is a plain `Manager`. We do NOT expose an
    `unscoped` alias here (that pattern only makes sense for tenant-owned
    rows where `objects` is a tenant-filtered manager).
    """

    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()

    class Meta:
        permissions = (
            ("manage_tenant", "Can manage tenant (admin)"),
        )

    def __str__(self) -> str:
        return self.name

    def active_user_count(self) -> int:
        from apps.accounts.models import User

        return User.objects.filter(
            tenant=self,
            is_active=True,
            is_disabled=False,
            is_system_admin=False,
        ).count()

    def effective_seat_limit(self) -> int | None:
        now = timezone.now()
        sub = (
            self.subscriptions
            .filter(is_active=True, starts_at__lte=now)
            .filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=now))
            .select_related("plan")
            .order_by("-starts_at", "-id")
            .first()
        )
        if sub is None:
            return None
        if sub.seat_limit_override is not None:
            return sub.seat_limit_override
        if sub.plan_id:
            return sub.plan.seat_limit
        return None

    def has_seat_available(self) -> bool:
        limit = self.effective_seat_limit()
        if limit is None:
            return True
        return self.active_user_count() < limit

    def active_module_codes(self) -> set[str]:
        """Return the codes of modules currently active for this tenant.

        Memoized on the instance via `_active_module_codes_cache`. Because
        the Tenant instance is constructed fresh in middleware on every
        request, this naturally invalidates per-request and avoids a
        second query when both subscription middleware and the menu
        context processor read the same set.
        """
        cached = getattr(self, "_active_module_codes_cache", None)
        if cached is not None:
            return cached
        codes = set(
            TenantModule.objects.filter(tenant=self, disabled_at__isnull=True)
            .values_list("module__code", flat=True)
        )
        self._active_module_codes_cache = codes
        return codes


class TenantSettings(models.Model):
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="settings")
    display_name = models.CharField(max_length=200, blank=True)
    logo = models.ImageField(upload_to="tenants/logos/", blank=True, null=True)
    primary_color = models.CharField(max_length=16, default="#1f6feb")
    secondary_color = models.CharField(max_length=16, default="#0d1117")
    accent_color = models.CharField(max_length=16, default="#2ea043")
    decimal_places = models.PositiveSmallIntegerField(default=2)
    currency_code = models.CharField(max_length=3, default="USD")
    currency_symbol = models.CharField(max_length=8, default="$")
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=64, blank=True)
    address_line1 = models.CharField(max_length=200, blank=True)
    address_line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    country = models.CharField(max_length=100, blank=True)
    timezone = models.CharField(max_length=64, default="UTC")
    locale = models.CharField(max_length=10, default="en-us")

    def __str__(self) -> str:
        return f"Settings({self.tenant})"


class Module(models.Model):
    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_core = models.BooleanField(default=False)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Plan(models.Model):
    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    seat_limit = models.PositiveIntegerField(default=5)
    modules = models.ManyToManyField(Module, related_name="plans", blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class Subscription(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, blank=True, related_name="subscriptions")
    seat_limit_override = models.PositiveIntegerField(null=True, blank=True)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-starts_at",)

    def __str__(self) -> str:
        plan_name = self.plan.name if self.plan_id else "custom"
        return f"{self.tenant} / {plan_name}"


class TenantModule(models.Model):
    """Active-module link table.

    Like `Tenant`, this table doesn't need a tenant-scoped manager: every
    row already carries the tenant FK and callers always filter on it.
    `objects` is a plain `Manager` and there is no `unscoped` alias.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="tenant_modules")
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="tenant_modules")
    enabled_at = models.DateTimeField(default=timezone.now)
    disabled_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()

    class Meta:
        unique_together = (("tenant", "module"),)

    def __str__(self) -> str:
        return f"{self.tenant} / {self.module.code}"

    @property
    def is_active(self) -> bool:
        return self.disabled_at is None


class TenantGroup(models.Model):
    """Thin wrapper linking an `auth.Group` to a tenant."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="tenant_groups")
    group = models.OneToOneField(Group, on_delete=models.CASCADE, related_name="tenant_group")
    description = models.CharField(max_length=255, blank=True)
    is_system_managed = models.BooleanField(default=False)

    class Meta:
        ordering = ("group__name",)

    def __str__(self) -> str:
        return f"{self.tenant}:{self.group.name}"
