"""Thread-local tenant scope used by TenantManager."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Optional

_storage = threading.local()


def set_current_tenant(tenant) -> None:
    _storage.tenant = tenant


def get_current_tenant():
    return getattr(_storage, "tenant", None)


def clear_current_tenant() -> None:
    if hasattr(_storage, "tenant"):
        delattr(_storage, "tenant")


@contextmanager
def tenant_scope(tenant):
    """Temporarily set the current tenant (used in management commands/tests)."""
    previous = get_current_tenant()
    set_current_tenant(tenant)
    try:
        yield
    finally:
        set_current_tenant(previous)
