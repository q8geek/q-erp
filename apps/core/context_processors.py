"""Template context processors for tenant branding and menu."""
from __future__ import annotations

from django.core.cache import cache
from django.urls import reverse, NoReverseMatch


# Per-(tenant, user) menu cache TTL. TTL is the safety net; active
# invalidation goes through ``invalidate_menu_for_user`` /
# ``invalidate_menu_for_tenant`` below so that role/permission/module
# changes are reflected on the very next request.
MENU_CACHE_TTL = 60

# Long TTL for the per-tenant menu version namespace. The version key
# bumps monotonically; we just need it to stick around. 30 days is plenty;
# even if it falls out of the cache the only side effect is one extra
# rebuild per (tenant, user) pair after the next bump.
_MENU_VER_TTL = 60 * 60 * 24 * 30


def _menu_ver_key(tenant_id: int) -> str:
    return f"menu_ver:{tenant_id}"


def _get_menu_ver(tenant_id: int) -> int:
    key = _menu_ver_key(tenant_id)
    # Atomic no-op-if-exists; only the first caller seeds 0. Avoids the
    # get-then-set race where a concurrent ``invalidate_menu_for_tenant``
    # could clobber a freshly-bumped version back to 0.
    cache.add(key, 0, _MENU_VER_TTL)
    return int(cache.get(key, 0))


def _get_menu_ver_for_request(request, tenant_id: int) -> int:
    """Per-request memoized variant of :func:`_get_menu_ver`.

    The ``menu`` context processor may run several times in a single
    request (multiple templates / includes); without this, each run does
    an extra cache.get + add. We stash a tiny dict on the request object
    so subsequent reads in the same request are free.
    """
    cache_attr = "_qerp_menu_ver"
    per_request = getattr(request, cache_attr, None)
    if per_request is None:
        per_request = {}
        try:
            setattr(request, cache_attr, per_request)
        except (AttributeError, TypeError):
            # Frozen / mock request — fall back to the un-memoized path.
            return _get_menu_ver(tenant_id)
    if tenant_id not in per_request:
        per_request[tenant_id] = _get_menu_ver(tenant_id)
    return per_request[tenant_id]


def menu_cache_key(tenant_id: int, user_id: int, *, request=None) -> str:
    """Return the per-(tenant, user) menu cache key for the CURRENT tenant version.

    The tenant version is embedded so that ``invalidate_menu_for_tenant``
    can bump it and effectively invalidate every per-user entry without
    needing pattern delete (which LocMemCache does not support).

    Pass ``request=request`` from request-scoped callers (i.e. the ``menu``
    context processor) to enable the per-request version memoization.
    Invalidation callers do not pass it — they only call once per save.
    """
    ver = (
        _get_menu_ver_for_request(request, tenant_id)
        if request is not None
        else _get_menu_ver(tenant_id)
    )
    return f"menu:{tenant_id}:{user_id}:v{ver}"


def invalidate_menu_for_user(tenant_id: int, user_id: int) -> None:
    """Drop the cached menu for one user under one tenant."""
    cache.delete(menu_cache_key(tenant_id, user_id))


def invalidate_menu_for_tenant(tenant_id: int) -> None:
    """Invalidate every cached menu under ``tenant_id``.

    Implementation: bumps the per-tenant ``menu_ver`` integer so that all
    existing ``menu:{tenant_id}:*:v{old}`` entries become unreachable.

    Race-safety: uses ``cache.add`` to atomically seed the key (no-op if
    it already exists), then ``cache.incr`` to bump unconditionally. Two
    concurrent invalidations on a cold key both observe the seeded 0 and
    increment to 1 and 2 respectively — no events are lost.
    """
    key = _menu_ver_key(tenant_id)
    # Ensure the key exists atomically (no-op if already present), then
    # increment unconditionally.
    cache.add(key, 0, _MENU_VER_TTL)
    try:
        cache.incr(key)
    except ValueError:
        # Extremely tight race: another caller deleted/expired the key
        # between the add and the incr. Re-seed at 1 so the bump is still
        # observed; on persistent failure the next render's natural TTL
        # rebuild treats the menu as invalidated anyway.
        cache.set(key, 1, _MENU_VER_TTL)


def tenant_branding(request):
    tenant = getattr(request, "tenant", None)
    settings_obj = getattr(tenant, "settings", None) if tenant else None
    if settings_obj is None:
        return {
            "tenant": tenant,
            "tenant_settings": None,
            "primary_color": "#1f6feb",
            "secondary_color": "#0d1117",
            "accent_color": "#2ea043",
        }
    return {
        "tenant": tenant,
        "tenant_settings": settings_obj,
        "primary_color": settings_obj.primary_color or "#1f6feb",
        "secondary_color": settings_obj.secondary_color or "#0d1117",
        "accent_color": settings_obj.accent_color or "#2ea043",
    }


def menu(request):
    """Build the tenant sidebar menu from active modules and user perms.

    The rendered menu structure is cached per (tenant_id, user_id) in
    Django's cache backend for `MENU_CACHE_TTL` seconds. Cache is keyed
    by user because per-module view perms gate visibility.
    """
    tenant = getattr(request, "tenant", None)
    user = getattr(request, "user", None)
    if tenant is None or user is None or not user.is_authenticated:
        return {"tenant_menu": []}

    cache_key = menu_cache_key(tenant.id, user.id, request=request)
    cached = cache.get(cache_key)
    if cached is not None:
        return {"tenant_menu": cached}

    # Avoid circular imports
    from apps.tenants.models import TenantModule
    from apps.tenants.registry import get_module_meta

    items = []
    active = TenantModule.objects.filter(tenant=tenant, disabled_at__isnull=True).select_related("module")
    for tm in active:
        meta = get_module_meta(tm.module.code)
        if not meta:
            continue
        view_perm = f"{tm.module.code}.view_{tm.module.code}"
        if not user.has_perm(view_perm) and not user.is_system_admin:
            # Tenant admins also bypass per-module perms via 'tenants.manage_tenant'
            if not user.has_perm("tenants.manage_tenant"):
                continue
        entries = []
        for entry in meta.get("menu", []):
            try:
                url = reverse(entry["url_name"], kwargs={"tenant_slug": tenant.slug})
            except NoReverseMatch:
                continue
            entries.append({"label": entry["label"], "url": url})
        items.append(
            {
                "code": tm.module.code,
                "name": tm.module.name,
                "is_core": tm.module.is_core,
                "entries": entries,
            }
        )
    cache.set(cache_key, items, MENU_CACHE_TTL)
    return {"tenant_menu": items}
