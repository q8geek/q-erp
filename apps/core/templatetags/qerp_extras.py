"""Template helpers."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter(name="can_manage_module")
def can_manage_module(user, module_code: str) -> bool:
    """Return True if ``user`` can manage records in the named module.

    Mirrors the server-side ``apps.core.access.enforce_tenant_manage``
    contract so that hiding a button in the template can't drift from
    the permission the view actually requires:

      * system admins can always manage;
      * users with ``tenants.manage_tenant`` can manage anything;
      * everyone else needs ``<module_code>.manage_<module_code>``.

    Used by ``templates/module/list.html`` / ``detail.html`` and
    module-specific list templates to hide the +New / edit / delete
    buttons from view-only users.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_system_admin", False):
        return True
    if user.has_perm("tenants.manage_tenant"):
        return True
    if not module_code:
        return False
    return user.has_perm(f"{module_code}.manage_{module_code}")


@register.filter(name="tenant_money")
def tenant_money(value, tenant_settings=None):
    """Format a number using tenant currency/decimal settings.

    Usage: {{ value|tenant_money:tenant_settings }}
    """
    if value is None or value == "":
        return ""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return value
    if tenant_settings is None:
        return f"{d:,.2f}"
    places = max(0, int(getattr(tenant_settings, "decimal_places", 2) or 2))
    symbol = getattr(tenant_settings, "currency_symbol", "") or ""
    formatted = f"{d:,.{places}f}"
    return f"{symbol}{formatted}" if symbol else formatted


@register.filter
def get_item(d, key):
    if isinstance(d, dict):
        return d.get(key)
    return None


@register.filter(name="get_attr")
def get_attr(obj, name):
    """Resolve attribute (or dict key) by name; used in generic list rendering."""
    if obj is None:
        return ""
    try:
        value = getattr(obj, name)
    except AttributeError:
        if isinstance(obj, dict):
            return obj.get(name, "")
        return ""
    if callable(value):
        try:
            value = value()
        except Exception:
            return ""
    return value
