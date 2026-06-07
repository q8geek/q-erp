"""Reusable base class for chunked-delete prune management commands.

This module deliberately lives directly under ``apps/core/management/`` (not
under ``apps/core/management/commands/``) so Django's management command
auto-discovery does NOT pick it up as a runnable command. Subclasses placed
under each app's ``management/commands/`` directory provide the per-model
configuration.

Contract (subclasses must set / may override the class-level attributes):

- ``model``: the Django model class to prune. Required.
- ``manager_name``: name of the manager attribute used for queries and deletes
  ("objects" by default; pass "unscoped" for tenant-aware models when the
  prune is intentionally global).
- ``timestamp_field``: the timestamp column compared against ``--older-than``
  (default ``"created_at"``).
- ``filter_arg_name``: optional CLI flag base name (without the leading ``--``).
  When set, the command exposes ``--<filter_arg_name>`` and filters the queryset
  on ``filter_field_attr`` when the user passes a value.
- ``filter_field_choices``: optional list of ``(value, label)`` tuples used both
  to constrain the CLI ``choices`` and to document accepted values.
- ``filter_field_attr``: the actual model field name to filter on (often the
  same as ``filter_arg_name``).
- ``object_noun``: human-friendly noun used in stdout messages (default
  ``"rows"``).

CLI contract (identical across every subclass):

- ``--older-than N`` (integer, ``>= 1``; default 90). Rejects ``< 1``.
- ``--batch-size N`` (integer; default 5000; minimum 100).
- ``--dry-run`` (counts candidates, exits without deleting).
- ``--yes`` (required when not ``--dry-run``).
- ``--<filter_arg_name>`` (optional, only when ``filter_arg_name`` is set).

Iteration strategy:
    Each batch advances a ``pk > last_seen_pk`` cursor instead of re-scanning
    the filtered queryset from offset 0. The database can then satisfy the
    per-batch SELECT using the pk index, even when the timestamp/filter
    predicate is unindexed. Total scan cost is O(N) instead of O(N^2 / batch).

    Operators pruning *very* large tables should still ensure an index on
    the configured ``timestamp_field`` (e.g. ``timestamp`` / ``created_at``)
    to make the initial ``count()`` and the candidate-set walk efficient.

    Deletion order is by ascending pk, which usually matches insertion
    order.
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class ChunkedPruneCommand(BaseCommand):
    """Base for chunked-delete prune commands. See module docstring."""

    # Configuration knobs — override per subclass.
    model = None
    manager_name: str = "objects"
    timestamp_field: str = "created_at"
    filter_arg_name: str | None = None
    filter_field_choices: list = []
    filter_field_attr: str | None = None
    object_noun: str = "rows"

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than",
            type=int,
            default=90,
            help="Days to retain (default 90). Must be >= 1.",
        )
        parser.add_argument("--batch-size", type=int, default=5000)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Required when not --dry-run.",
        )
        if self.filter_arg_name:
            choices = (
                [v for v, _ in self.filter_field_choices]
                if self.filter_field_choices
                else None
            )
            parser.add_argument(
                f"--{self.filter_arg_name}",
                choices=choices,
                help=f"Only prune rows whose {self.filter_field_attr} matches this value.",
            )

    def get_manager(self):
        if self.model is None:
            raise CommandError(
                f"{type(self).__name__} did not set `model`; cannot prune."
            )
        return getattr(self.model, self.manager_name)

    def handle(self, *args, **options):
        days = options["older_than"]
        if days < 1:
            raise CommandError("--older-than must be >= 1")
        cutoff = timezone.now() - timedelta(days=days)
        manager = self.get_manager()
        qs = manager.filter(**{f"{self.timestamp_field}__lt": cutoff})
        if self.filter_arg_name:
            # argparse normalises `--foo-bar` to `foo_bar` in options.
            opt_key = self.filter_arg_name.replace("-", "_")
            val = options.get(opt_key)
            if val and self.filter_field_attr:
                qs = qs.filter(**{self.filter_field_attr: val})
        total = qs.count()
        self.stdout.write(
            f"Candidate {self.object_noun}: {total} older than {cutoff.isoformat()}"
        )
        if options["dry_run"]:
            return
        if not options["yes"]:
            raise CommandError(
                f"Refusing to delete {self.object_noun} without --yes (or use --dry-run)."
            )
        batch = max(100, options["batch_size"])
        deleted_total = 0
        last_pk = None
        while True:
            chunk_qs = qs
            if last_pk is not None:
                chunk_qs = chunk_qs.filter(pk__gt=last_pk)
            # Order by pk so the gt filter consistently shrinks the
            # candidate window each iteration. Each batch SELECT is
            # bounded by the pk index even if the filter column is not
            # indexed.
            ids = list(chunk_qs.order_by("pk").values_list("pk", flat=True)[:batch])
            if not ids:
                break
            last_pk = ids[-1]
            deleted, _ = manager.filter(pk__in=ids).delete()
            deleted_total += deleted
            self.stdout.write(f"  deleted {deleted_total}/{total}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Deleted {deleted_total} {self.object_noun}."
            )
        )
