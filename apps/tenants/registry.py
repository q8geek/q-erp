"""Module registry: walks INSTALLED_APPS for module_meta modules."""
from __future__ import annotations

from importlib import import_module
from typing import Optional

from django.apps import apps


def iter_module_metas():
    for app_config in apps.get_app_configs():
        if not app_config.name.startswith("apps."):
            continue
        try:
            module = import_module(f"{app_config.name}.module_meta")
        except ModuleNotFoundError:
            continue
        meta = getattr(module, "MODULE", None)
        if isinstance(meta, dict) and "code" in meta:
            yield meta


def get_module_meta(code: str) -> Optional[dict]:
    for meta in iter_module_metas():
        if meta["code"] == code:
            return meta
    return None
