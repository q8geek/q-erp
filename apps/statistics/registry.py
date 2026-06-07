"""Widget registry.

A widget is a small computation that returns a (label, value, hint) tuple
for a given tenant + request. Registered by code; tenant-admins select
which widgets appear on the statistics page via the dashboard config.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional


@dataclass
class Widget:
    code: str
    label: str
    description: str
    module: str  # required module code; widget is only available when module is active
    compute: Callable[..., dict]  # (tenant, request) -> {"value": ..., "hint": ..., "unit": ...}
    per_user: bool = False  # True when result depends on request.user (skips tenant-wide cache)


_WIDGETS: dict[str, Widget] = {}


def register_widget(code: str, label: str, module: str, description: str = "", *, per_user: bool = False):
    def _wrap(fn: Callable[..., dict]) -> Callable[..., dict]:
        _WIDGETS[code] = Widget(
            code=code,
            label=label,
            description=description,
            module=module,
            compute=fn,
            per_user=per_user,
        )
        return fn

    return _wrap


def get_widget(code: str) -> Optional[Widget]:
    return _WIDGETS.get(code)


def all_widgets() -> dict[str, Widget]:
    return dict(_WIDGETS)


def widget_choices() -> list[tuple[str, str]]:
    return sorted(((code, w.label) for code, w in _WIDGETS.items()), key=lambda x: x[1])
