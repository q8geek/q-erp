"""Shared tenant-access gate.

Single source of truth for the rule "may this user perform an action on
this tenant?" — used by both the class-based `TenantPermissionRequiredMixin`
and by the function-based write views in `apps/core/crud.py`,
`apps/tenant_admin/views.py`, `apps/automation/views.py`, and
`apps/statistics/views.py`.

The previous design re-implemented the check inline at each site; the
mixin enforced `is_disabled` and `tenant_id == request.tenant.id`, the
function views did not. This helper closes that gap.
"""
from __future__ import annotations

from django.core.exceptions import PermissionDenied


def assert_tenant_access(request) -> None:
    """Verify the request user can act within `request.tenant`.

    Raises PermissionDenied on any failure. Returns silently on success.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        raise PermissionDenied("Tenant context required.")
    if user.is_disabled or not user.is_active:
        raise PermissionDenied("Your account is disabled.")
    if user.is_system_admin:
        # TenantAccessMiddleware already validated the system admin's
        # SystemAdminTenant link (or global-admin status). Nothing more to do.
        return
    if user.tenant_id != tenant.id:
        raise PermissionDenied("You do not belong to this tenant.")


def enforce_tenant_manage(request, perm: str | None = None) -> None:
    """Verify access + permission for a mutating action.

    `perm` is the per-module manage permission (e.g. "tasks.manage_tasks").
    Bypassed for system admins and for users with `tenants.manage_tenant`.
    """
    assert_tenant_access(request)
    user = request.user
    if user.is_system_admin:
        return
    if user.has_perm("tenants.manage_tenant"):
        return
    if perm and user.has_perm(perm):
        return
    raise PermissionDenied("Missing required permission.")


def has_tenant_view(request, perm: str | None = None) -> bool:
    """Same as enforce_tenant_manage but boolean and for *view* permissions.

    Used by context processors / template tags that need to gate visibility
    without raising. Not currently used but provided for symmetry.
    """
    try:
        assert_tenant_access(request)
    except PermissionDenied:
        return False
    user = request.user
    if user.is_system_admin:
        return True
    if user.has_perm("tenants.manage_tenant"):
        return True
    return bool(perm) and user.has_perm(perm)
