"""Template helpers."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


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
