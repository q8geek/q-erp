"""Reusable view mixins.

The tenant-access rule lives in `apps.core.access`; these mixins compose
it for class-based views.
"""
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from .access import assert_tenant_access, enforce_tenant_manage


class TenantRequiredMixin(LoginRequiredMixin):
    """Require an authenticated user attached to the resolved tenant."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        # Use the shared helper so the rule cannot drift relative to
        # middleware / function-based views.
        assert_tenant_access(request)
        return super().dispatch(request, *args, **kwargs)


class TenantPermissionRequiredMixin(TenantRequiredMixin):
    """Require a specific permission within the tenant context."""

    required_permission: str | None = None

    def get_required_permission(self) -> str | None:
        return self.required_permission

    def has_required_permission(self, request) -> bool:
        user = request.user
        if user.is_system_admin:
            return True
        if user.has_perm("tenants.manage_tenant"):
            return True
        perm = self.get_required_permission()
        return bool(perm) and user.has_perm(perm)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        # `assert_tenant_access` is run by TenantRequiredMixin via the
        # super().dispatch chain. The permission check happens here.
        assert_tenant_access(request)
        if not self.has_required_permission(request):
            raise PermissionDenied("Missing required permission.")
        return super(TenantRequiredMixin, self).dispatch(request, *args, **kwargs)


class SystemAdminRequiredMixin(LoginRequiredMixin):
    """Require an active system admin user."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if not request.user.is_system_admin:
            raise PermissionDenied("System admin required.")
        return super().dispatch(request, *args, **kwargs)
