"""Prune old ActivityLog rows (chunked, idempotent).

Thin subclass of :class:`apps.core.management.chunked_prune.ChunkedPruneCommand`.
CLI surface is preserved verbatim: ``--older-than``, ``--batch-size``,
``--dry-run``, ``--yes``, ``--category``.
"""
from __future__ import annotations

from apps.activity.models import ActivityLog
from apps.core.management.chunked_prune import ChunkedPruneCommand


class Command(ChunkedPruneCommand):
    help = "Delete ActivityLog rows older than --older-than days (chunked, idempotent)."

    model = ActivityLog
    manager_name = "objects"
    timestamp_field = "timestamp"
    filter_arg_name = "category"
    filter_field_choices = list(ActivityLog.Category.choices)
    filter_field_attr = "category"
    object_noun = "activity log rows"
