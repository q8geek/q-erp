"""Tiny safe condition evaluator.

Condition format (JSON dict):
    {
      "field.path": {"op": value, ...},
      "another.field": {"<=": 10},
      "$all": [ {...}, {...} ],          # AND across siblings (default already)
      "$any": [ {...}, {...} ],          # OR across siblings
    }

Supported ops: ==, !=, <, <=, >, >=, in, not_in, contains, startswith, endswith

The evaluator NEVER imports or evaluates raw expressions. It walks the
condition dict, resolves each field path against the payload, and
applies the typed comparison.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

_OPS = {
    "==": lambda a, b: a == b,
    "eq": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "ne": lambda a, b: a != b,
    "<": lambda a, b: _cmp(a, b) < 0,
    "<=": lambda a, b: _cmp(a, b) <= 0,
    ">": lambda a, b: _cmp(a, b) > 0,
    ">=": lambda a, b: _cmp(a, b) >= 0,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
    "contains": lambda a, b: b in (a or ""),
    "startswith": lambda a, b: (a or "").startswith(b),
    "endswith": lambda a, b: (a or "").endswith(b),
}


def _cmp(a, b):
    """Compare with Decimal-friendly coercion."""
    if isinstance(a, (int, float, Decimal)) or isinstance(b, (int, float, Decimal)):
        try:
            return (Decimal(str(a)) - Decimal(str(b)))
        except Exception:
            return 0
    if a == b:
        return 0
    return -1 if (a or "") < (b or "") else 1


def _resolve(payload: Mapping[str, Any], path: str):
    """Walk `path` ('a.b.c') against `payload`.

    Defense in depth: refuse to descend into non-Mapping values. The engine
    already normalises payloads to JSON primitives via `coerce_for_event`,
    but if a hand-crafted payload reaches us with arbitrary Python objects,
    we MUST NOT call getattr on them — that would let conditions probe
    attribute names on models / requests / settings.
    """
    cur: Any = payload
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, Mapping):
            cur = cur.get(part)
        else:
            return None
    return cur


def evaluate(condition: Mapping[str, Any] | None, payload: Mapping[str, Any]) -> bool:
    """Return True if `payload` satisfies `condition`.

    An empty/None condition matches everything.
    """
    if not condition:
        return True
    if not isinstance(condition, Mapping):
        return False
    # Combinators
    if "$any" in condition:
        clauses = condition["$any"] or []
        return any(evaluate(c, payload) for c in clauses)
    if "$all" in condition:
        clauses = condition["$all"] or []
        return all(evaluate(c, payload) for c in clauses)
    # Default: AND across all field clauses
    for path, ops in condition.items():
        if not isinstance(ops, Mapping):
            return False
        actual = _resolve(payload, path)
        for op, expected in ops.items():
            fn = _OPS.get(op)
            if fn is None:
                return False
            try:
                ok = bool(fn(actual, expected))
            except Exception:
                return False
            if not ok:
                return False
    return True
