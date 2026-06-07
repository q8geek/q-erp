"""Synchronous, in-process rule engine.

`emit_event(request, event_type, payload)` is called from module write
views (e.g. inventory item save). It:

1. Looks up active Rule rows for `request.tenant` matching `event_type`.
2. Evaluates each rule's condition against `payload`.
3. For matches, dispatches to the registered action handler.
4. Records a RuleRun audit row for MATCHED / ERROR (but not SKIPPED — see
   `_run_rule` below) and updates the Rule's `last_run_*` fields.

Action handlers are expected to be cheap and safe; the engine guards
against handler exceptions so a misconfigured rule never breaks the
caller's request.

Payload normalization: callers pass raw Python values (model field
values, Decimals, dates, FK references, etc.). The engine's
`coerce_for_event(...)` reduces the payload to JSON-friendly primitives
exactly once at the engine boundary, BEFORE conditions are evaluated.
This guarantees a single, well-defined contract for rule authors
regardless of which emit site produced the event.
"""
from __future__ import annotations

import logging
import traceback
from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from django.db import models as dj_models
from django.utils import timezone

from .conditions import evaluate
from .models import Rule, RuleRun
from .registry import get_action

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-emit_event memoization scaffolding
# ---------------------------------------------------------------------------
# Action handlers (notify_head_of_*, ...) memoize a few lookups for the
# duration of one ``emit_event`` call. We expose this via a ContextVar
# rather than a module global so each emit_event call gets its own isolated
# dict regardless of worker model (sync, threaded, async-via-asgiref).
#
# ``get_head_of_cache()`` returns the active dict when called inside
# ``emit_event`` and a throwaway empty dict when called outside. The
# throwaway means lookups still work outside emit_event (e.g. when an
# action handler is unit-tested directly) — they just don't get memoized.
_head_of_cache_var: ContextVar[dict | None] = ContextVar(
    "qerp_automation_head_of_cache", default=None
)


def get_head_of_cache() -> dict:
    """Return the active per-``emit_event`` memoization dict.

    Inside an ``emit_event`` call this is the dict bound for that call
    (shared across every rule + action handler in the dispatch). Outside
    one, returns a fresh empty dict so direct-call callers degrade
    gracefully (no memoization, but lookups still succeed).
    """
    current = _head_of_cache_var.get()
    if current is None:
        return {}
    return current


# ---------------------------------------------------------------------------
# Payload normalization (single source of truth at the engine boundary)
# ---------------------------------------------------------------------------

def coerce_for_event(value: Any) -> Any:
    """Recursively coerce a Python value to a JSON-friendly form.

    Rules:
    - None / bool / int / float / str: returned as-is.
    - Decimal: stringified (preserves precision for comparison rules).
    - date / datetime: ISO 8601 string.
    - dict: each value is coerced recursively.
    - list / tuple / set: each element coerced; result is a list.
    - Django Model instance: replaced with its pk.
    - Anything else: `str(value)` as a last resort (e.g. UUID, Path).
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: coerce_for_event(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [coerce_for_event(v) for v in value]
    if isinstance(value, dj_models.Model):
        return value.pk
    return str(value)


def _normalize_payload(payload: Mapping[str, Any] | None) -> dict:
    if not payload:
        return {}
    return {k: coerce_for_event(v) for k, v in payload.items()}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def emit_event(request, event_type: str, payload: Mapping[str, Any] | None = None) -> list[RuleRun]:
    """Fire all active rules for the current tenant matching `event_type`.

    Returns the list of RuleRun audit rows created (MATCHED + ERROR only).
    Never raises.
    """
    tenant = getattr(request, "tenant", None) if request is not None else None
    if tenant is None:
        return []
    user = getattr(request, "user", None) if request is not None else None
    # Bind a fresh per-emit memoization dict on the ContextVar. Action
    # handlers (see apps.automation.actions) read from it via
    # ``get_head_of_cache()``. The dict is isolated per emit_event call;
    # under threaded WSGI workers two concurrent emit_event calls each
    # see their own dict and never clobber each other.
    token = _head_of_cache_var.set({})
    try:
        runs: list[RuleRun] = []
        rules = (
            Rule.unscoped.filter(tenant=tenant, event_type=event_type, is_active=True)
            .order_by("pk")
        )
        if not rules.exists():
            return []
        safe_payload = _normalize_payload(payload)
        for rule in rules:
            run = _run_rule(rule, safe_payload, user)
            if run is not None:
                runs.append(run)
        return runs
    finally:
        _head_of_cache_var.reset(token)


def _run_rule(rule: Rule, payload: Mapping[str, Any], user) -> RuleRun | None:
    """Evaluate one rule and dispatch its action.

    Returns the RuleRun row that was written (MATCHED or ERROR), or None for
    SKIPPED (we no longer write audit rows for non-matching evaluations).
    """
    try:
        matches = evaluate(rule.condition, payload)
    except Exception as exc:
        return _record_and_update(
            rule, payload, user, RuleRun.Status.ERROR, error=f"condition: {exc}"
        )
    if not matches:
        # SKIPPED: don't record an audit row, don't UPDATE the rule.
        # (See the deferred-write design note in the engine docstring.)
        return None
    action = get_action(rule.action_type)
    if action is None or action.handler is None:
        return _record_and_update(
            rule, payload, user, RuleRun.Status.ERROR,
            error=f"unknown action: {rule.action_type}",
        )
    try:
        action.handler(tenant=rule.tenant, payload=payload, rule=rule, params=rule.action_params or {})
    except Exception as exc:
        log.exception("automation action %s failed", rule.action_type)
        return _record_and_update(
            rule, payload, user, RuleRun.Status.ERROR,
            error=f"{exc}\n{traceback.format_exc(limit=4)}",
        )
    return _record_and_update(rule, payload, user, RuleRun.Status.MATCHED)


def _record_and_update(
    rule: Rule,
    payload: Mapping[str, Any],
    user,
    status: str,
    *,
    error: str = "",
) -> RuleRun:
    now = timezone.now()
    rule.last_run_at = now
    rule.last_run_status = status
    rule.last_run_error = error or ""
    rule.save(update_fields=["last_run_at", "last_run_status", "last_run_error", "updated_at"])
    return RuleRun.unscoped.create(
        tenant=rule.tenant,
        rule=rule,
        event_type=rule.event_type,
        payload=payload,
        status=status,
        error=error,
        triggered_by=user if getattr(user, "is_authenticated", False) else None,
    )
