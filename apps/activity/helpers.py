"""Helpers callable from views to enrich the activity log row."""
from __future__ import annotations

from typing import Any


def log_change(request, *, action: str, obj=None, extra: dict[str, Any] | None = None) -> None:
    """Stash details about a write that the middleware will pick up at response time."""
    payload = getattr(request, "_qerp_activity_extra", None)
    if payload is None:
        payload = {}
        request._qerp_activity_extra = payload
    payload["action"] = action
    if obj is not None:
        payload["object_type"] = f"{obj._meta.app_label}.{obj._meta.model_name}"
        payload["object_id"] = str(getattr(obj, "pk", ""))
        try:
            payload["object_repr"] = str(obj)[:255]
        except Exception:
            payload["object_repr"] = ""
    if extra:
        payload.setdefault("extra", {}).update(extra)
