"""Event and action registries.

Both are in-process: each module that emits events imports this module
and calls `register_event(...)`. Action handlers do the same with
`register_action(...)`. No DB rows back the registry, because event
types and action types are CODE-LEVEL definitions (changing them is a
deploy, not a tenant-admin task).

What tenant admins *do* configure (via DB) is `Rule` rows that wire a
known event_type to a known action_type with a tenant-scoped condition
and parameters.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class EventType:
    code: str
    label: str
    description: str = ""
    # Documented payload shape — used by the UI to render the condition builder.
    # Each key is a dotted path that may appear in `payload`; value is a human
    # description.
    payload_fields: dict[str, str] = field(default_factory=dict)


@dataclass
class ActionType:
    code: str
    label: str
    description: str = ""
    # Documented parameter shape: {param_name: help text}
    params: dict[str, str] = field(default_factory=dict)
    handler: Optional[Callable[..., Any]] = None


_EVENTS: dict[str, EventType] = {}
_ACTIONS: dict[str, ActionType] = {}


def register_event(code: str, label: str, *, description: str = "", payload_fields: Optional[dict[str, str]] = None) -> EventType:
    et = EventType(code=code, label=label, description=description, payload_fields=payload_fields or {})
    _EVENTS[code] = et
    return et


def register_action(code: str, label: str, *, description: str = "", params: Optional[dict[str, str]] = None) -> Callable:
    """Decorator: registers an action handler.

    The wrapped callable receives (tenant, payload, rule, params) and may
    return anything (for logging). It MUST NOT raise to avoid breaking
    the request — handlers should swallow their own errors and log.
    """
    def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        _ACTIONS[code] = ActionType(
            code=code, label=label, description=description, params=params or {}, handler=fn
        )
        return fn

    return _wrap


def get_event(code: str) -> Optional[EventType]:
    return _EVENTS.get(code)


def get_action(code: str) -> Optional[ActionType]:
    return _ACTIONS.get(code)


def event_choices() -> list[tuple[str, str]]:
    return sorted(((code, et.label) for code, et in _EVENTS.items()), key=lambda x: x[1])


def action_choices() -> list[tuple[str, str]]:
    return sorted(((code, at.label) for code, at in _ACTIONS.items()), key=lambda x: x[1])


def all_events() -> dict[str, EventType]:
    return dict(_EVENTS)


def all_actions() -> dict[str, ActionType]:
    return dict(_ACTIONS)
