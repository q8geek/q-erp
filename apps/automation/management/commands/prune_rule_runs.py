"""Delete old RuleRun rows in chunks.

Thin subclass of :class:`apps.core.management.chunked_prune.ChunkedPruneCommand`.
CLI surface is preserved verbatim: ``--older-than``, ``--batch-size``,
``--dry-run``, ``--yes``, ``--status``.
"""
from __future__ import annotations

from apps.automation.models import RuleRun
from apps.core.management.chunked_prune import ChunkedPruneCommand


class Command(ChunkedPruneCommand):
    help = "Delete RuleRun rows older than --older-than days (chunked, idempotent)."

    model = RuleRun
    manager_name = "unscoped"
    timestamp_field = "created_at"
    filter_arg_name = "status"
    filter_field_choices = list(RuleRun.Status.choices)
    filter_field_attr = "status"
    object_noun = "rule run rows"
