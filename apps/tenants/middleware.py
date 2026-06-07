"""Tenancy middleware: resolution, access, subscription enforcement."""
from __future__ import annotations

import re

from django.core.exceptions import PermissionDenied
from django.http import Http404

from apps.core.scope import clear_current_tenant, set_current_tenant

from .models import Tenant


TENANT_URL_RE = re.compile(r"^/t/(?P<slug>[^/]+)/")

_MISSING = object()


def _resolve_tenant(request) -> Tenant | None:
    """Resolve `request.path_info` -> Tenant, memoized per-request.

    Both this middleware and the menu context processor need the tenant;
    we cache the lookup on the request so they share a single DB hit.
    `select_related("settings")` pre-loads the OneToOne the branding
    context processor will read.
    """
    cached = getattr(request, "_qerp_resolved_tenant", _MISSING)
    if cached is not _MISSING:
        return cached
    m = TENANT_URL_RE.match(request.path_info)
    if not m:
        request._qerp_resolved_tenant = None
        return None
    slug = m.group("slug")
    try:
        tenant = (
            Tenant.objects
            .select_related("settings")
            .get(slug=slug, is_active=True)
        )
    except Tenant.DoesNotExist:
        # Preserve the previous behaviour of returning a 404 to the caller.
        raise Http404("Tenant not found.")
    request._qerp_resolved_tenant = tenant
    return tenant


class TenantResolutionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = _resolve_tenant(request)
        request.tenant = tenant
        if tenant is not None:
            set_current_tenant(tenant)
        try:
            response = self.get_response(request)
        finally:
            clear_current_tenant()
        return response


class TenantAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return self.get_response(request)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return self.get_response(request)
        if user.is_system_admin:
            if not user.is_global_admin:
                from apps.accounts.models import SystemAdminTenant

                if not SystemAdminTenant.objects.filter(user=user, tenant=tenant).exists():
                    raise PermissionDenied("System admin lacks access to this tenant.")
            return self.get_response(request)
        if user.tenant_id != tenant.id:
            raise PermissionDenied("You do not belong to this tenant.")
        if user.is_disabled or not user.is_active:
            raise PermissionDenied("Your account is disabled.")
        return self.get_response(request)


# Tenant URL prefixes that are NOT module-scoped (e.g. dashboard, admin pages).
NON_MODULE_TENANT_PREFIXES = ("dashboard", "admin", "")


class SubscriptionEnforcementMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return self.get_response(request)
        # Determine the second URL segment after /t/<slug>/
        path = request.path_info
        m = TENANT_URL_RE.match(path)
        if not m:
            return self.get_response(request)
        remainder = path[m.end():]
        first_segment = remainder.split("/", 1)[0] if remainder else ""
        if first_segment in NON_MODULE_TENANT_PREFIXES:
            return self.get_response(request)
        # The first segment must correspond to an active module code.
        active_codes = tenant.active_module_codes()
        if first_segment and first_segment not in active_codes:
            raise PermissionDenied(
                f"Module '{first_segment}' is not active for tenant '{tenant.slug}'."
            )
        return self.get_response(request)
