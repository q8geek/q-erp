"""Generic tenant-scoped CRUD view bases.

Modules subclass these to get a uniform list / detail / create / edit / delete
flow with permission gating, tenant scoping, activity logging, and automation
event emission.
"""
from __future__ import annotations

from django.contrib import messages
from django.forms import modelform_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView

from apps.activity.helpers import log_change

from .access import enforce_tenant_manage
from .mixins import TenantPermissionRequiredMixin


# ---------------------------------------------------------------------------
# Automation engine emit hook
# ---------------------------------------------------------------------------

def _has_active_rules_cache(request, event_code: str) -> bool:
    """Cheaply ask: are there any active automation rules for this tenant/event?

    Cached on the request so save+log+emit in the same view do not requery.
    Returns False (no work) when the answer is unknown, the automation app is
    missing, or the engine raises.
    """
    try:
        from apps.automation.models import Rule
    except Exception:
        return False
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return False
    cache = getattr(request, "_qerp_active_rule_cache", None)
    if cache is None:
        cache = {}
        request._qerp_active_rule_cache = cache
    if event_code in cache:
        return cache[event_code]
    try:
        result = Rule.unscoped.filter(
            tenant=tenant, event_type=event_code, is_active=True
        ).exists()
    except Exception:
        result = False
    cache[event_code] = result
    return result


def _emit_lifecycle_event(request, obj, *, action_kind: str, payload_snapshot: dict | None = None):
    """Best-effort: emit `<app>.<model>.<action_kind>` through the automation engine.

    `action_kind` is one of "saved", "created", "updated", "deleted".

    For deletes the caller must supply `payload_snapshot` taken BEFORE the row
    is deleted; otherwise the snapshot is built from the still-live instance.

    Never raises; never blocks the request.
    """
    try:
        from apps.automation.engine import emit_event
        from apps.automation.registry import get_event
    except Exception:
        return
    try:
        module_code = obj._meta.app_label
        model_name = obj._meta.model_name
        event_code = f"{module_code}.{model_name}.{action_kind}"
        if get_event(event_code) is None:
            # Fall back to the generic `.saved` event when emitting a more
            # specific kind that's not registered.
            if action_kind in ("created", "updated"):
                fallback = f"{module_code}.{model_name}.saved"
                if get_event(fallback) is None:
                    return
                event_code = fallback
            else:
                return
        if not _has_active_rules_cache(request, event_code):
            return
        if payload_snapshot is None:
            payload_snapshot = _snapshot_payload(obj)
        emit_event(request, event_code, payload_snapshot)
    except Exception:
        # Never propagate
        return


def _snapshot_payload(obj) -> dict:
    """Build a JSON-friendly payload from a model instance.

    The actual JSON-coercion happens inside the engine (see
    `apps.automation.engine.coerce_for_event`); here we only extract raw
    field values + the pk so the engine sees a single, consistent shape.
    """
    payload = {f.name: getattr(obj, f.name, None) for f in obj._meta.fields if f.name != "tenant"}
    payload["object_id"] = obj.pk
    return payload


# ---------------------------------------------------------------------------
# CRUD config / view bases
# ---------------------------------------------------------------------------

class ModuleCRUDConfig:
    """Holds module CRUD metadata; subclasses set attributes."""

    model = None
    fields: list[str] = []
    list_display: list[str] = []
    # FKs to follow with select_related() on the list view to avoid N+1.
    list_select_related: list[str] = []
    # Reverse / M2M relations to prefetch on the list view.
    list_prefetch_related: list[str] = []
    # Optional per-field header label overrides. Field names not listed
    # here fall through to ``humanize_field_label`` (which uses the
    # model's verbose_name, then strips a leading "is_" prefix so
    # ``is_active`` renders as ``active``).
    list_display_labels: dict[str, str] = {}
    url_namespace: str = ""
    module_code: str = ""

    @classmethod
    def view_perm(cls):
        return f"{cls.module_code}.view_{cls.module_code}"

    @classmethod
    def manage_perm(cls):
        return f"{cls.module_code}.manage_{cls.module_code}"


def humanize_field_label(model, field_name: str, override: str | None = None) -> str:
    """Pick a user-facing header label for ``field_name`` on ``model``.

    Order of precedence:
      1. Explicit ``override`` from ``ModuleCRUDConfig.list_display_labels``.
      2. The Django field's ``verbose_name`` (already humanised by Django
         to e.g. ``"is active"`` for an ``is_active`` BooleanField).
      3. Strip a leading ``is_`` prefix and replace underscores with
         spaces (``is_active`` -> ``active``).

    The ``is_`` prefix strip is the small extra step that turns Django's
    default ``"is active"`` header into the cleaner ``"active"`` UX you
    expect on a list view.
    """
    if override:
        return override
    try:
        field = model._meta.get_field(field_name)
    except Exception:  # pragma: no cover - defensive
        field = None
    if field is not None:
        label = str(field.verbose_name or field_name)
    else:
        label = field_name
    # Strip leading "is " so BooleanFields render naturally.
    if label.lower().startswith("is "):
        label = label[3:]
    return label.capitalize() if label else label


def make_form(model_class, fields):
    return modelform_factory(model_class, fields=fields)


class TenantScopedListView(TenantPermissionRequiredMixin, ListView):
    """Generic list view; subclasses set `model`, `template_name`, etc."""

    paginate_by = 50
    template_name = "module/list.html"
    config: type[ModuleCRUDConfig] = None
    context_object_name = "objects"

    def get_required_permission(self):
        return self.config.view_perm()

    def get_queryset(self):
        qs = self.config.model.objects.all()
        if self.config.list_select_related:
            qs = qs.select_related(*self.config.list_select_related)
        if self.config.list_prefetch_related:
            qs = qs.prefetch_related(*self.config.list_prefetch_related)
        # Sort newest-first; on a tenant-scoped queryset this is effectively
        # `(tenant_id, -id)` since `objects` is already tenant-filtered for
        # TenantOwnedModel subclasses.
        return qs.order_by("-id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["config"] = self.config
        fields = self.config.list_display or [
            f.name for f in self.config.model._meta.fields if f.name != "tenant"
        ]
        labels = self.config.list_display_labels or {}
        # Pair each field name with its rendered header label so the
        # template can iterate once.
        ctx["list_columns"] = [
            (name, humanize_field_label(self.config.model, name, labels.get(name)))
            for name in fields
        ]
        # Kept for back-compat with templates that still iterate list_display.
        ctx["list_display"] = fields
        ctx["module_code"] = self.config.module_code
        ctx["model_name"] = self.config.model._meta.model_name
        ctx["verbose_name"] = self.config.model._meta.verbose_name
        ctx["verbose_name_plural"] = self.config.model._meta.verbose_name_plural
        return ctx


class TenantScopedDetailView(TenantPermissionRequiredMixin, DetailView):
    template_name = "module/detail.html"
    config: type[ModuleCRUDConfig] = None
    context_object_name = "object"

    def get_required_permission(self):
        return self.config.view_perm()

    def get_queryset(self):
        return self.config.model.objects.all()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["config"] = self.config
        ctx["module_code"] = self.config.module_code
        ctx["model_name"] = self.config.model._meta.model_name
        ctx["verbose_name"] = self.config.model._meta.verbose_name
        ctx["verbose_name_plural"] = self.config.model._meta.verbose_name_plural
        labels = self.config.list_display_labels or {}
        ctx["object_fields"] = [
            (
                humanize_field_label(self.config.model, f.name, labels.get(f.name)),
                f.name,
            )
            for f in self.config.model._meta.fields
            if f.name != "tenant"
        ]
        return ctx


def tenant_scoped_create_or_edit(
    request, tenant_slug, *, config: type[ModuleCRUDConfig], pk=None
):
    enforce_tenant_manage(request, config.manage_perm())
    user = request.user
    instance = None
    is_create = pk is None
    if pk is not None:
        instance = get_object_or_404(config.model.objects.all(), pk=pk)
    form_class = make_form(config.model, config.fields)
    if request.method == "POST":
        form = form_class(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            if is_create and hasattr(obj, "created_by_id"):
                obj.created_by = user
            if hasattr(obj, "updated_by_id"):
                obj.updated_by = user
            obj.save()
            form.save_m2m()
            log_change(
                request,
                action=f"{config.module_code}.{config.model._meta.model_name}."
                + ("create" if is_create else "update"),
                obj=obj,
            )
            # Emit the specific lifecycle event first (falls back to `.saved`
            # if not registered).
            _emit_lifecycle_event(
                request, obj, action_kind="created" if is_create else "updated"
            )
            # Always also try the generic `.saved` event for rules subscribed
            # to either change kind.
            _emit_lifecycle_event(request, obj, action_kind="saved")
            messages.success(request, "Saved.")
            return redirect(
                reverse(
                    f"{config.url_namespace}:{config.model._meta.model_name}_list",
                    kwargs={"tenant_slug": tenant_slug},
                )
            )
    else:
        form = form_class(instance=instance)
    return render(
        request,
        "module/form.html",
        {
            "form": form,
            "instance": instance,
            "config": config,
            "module_code": config.module_code,
            "model_name": config.model._meta.model_name,
            "verbose_name": config.model._meta.verbose_name,
            "verbose_name_plural": config.model._meta.verbose_name_plural,
        },
    )


def tenant_scoped_delete(request, tenant_slug, *, config: type[ModuleCRUDConfig], pk):
    enforce_tenant_manage(request, config.manage_perm())
    instance = get_object_or_404(config.model.objects.all(), pk=pk)
    if request.method == "POST":
        log_change(
            request,
            action=f"{config.module_code}.{config.model._meta.model_name}.delete",
            obj=instance,
        )
        # Snapshot the payload BEFORE delete (pk + FK ids still valid).
        snapshot = _snapshot_payload(instance)
        instance.delete()
        _emit_lifecycle_event(
            request, instance, action_kind="deleted", payload_snapshot=snapshot
        )
        messages.success(request, "Deleted.")
        return redirect(
            reverse(
                f"{config.url_namespace}:{config.model._meta.model_name}_list",
                kwargs={"tenant_slug": tenant_slug},
            )
        )
    return render(
        request,
        "module/confirm_delete.html",
        {
            "object": instance,
            "config": config,
            "module_code": config.module_code,
            "model_name": config.model._meta.model_name,
            "verbose_name": config.model._meta.verbose_name,
        },
    )


def _validate_list_display_select_related(config: type[ModuleCRUDConfig]) -> None:
    """Ensure every FK in `list_display` is covered by `list_select_related`.

    Raises ImproperlyConfigured for any FK on the list view that would
    otherwise trigger an N+1 query when rendered. Unknown field names
    (e.g. property accessors, callables) are silently skipped.
    """
    from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured

    select_related = set(config.list_select_related or [])
    for name in config.list_display or []:
        try:
            field = config.model._meta.get_field(name)
        except FieldDoesNotExist:
            continue
        if getattr(field, "is_relation", False) and getattr(field, "many_to_one", False):
            if name not in select_related:
                raise ImproperlyConfigured(
                    f"{config.__name__}.list_display includes FK '{name}' "
                    f"but list_select_related does not — would cause N+1."
                )


def build_module_urls(config: type[ModuleCRUDConfig]):
    """Generate a list of url patterns for the standard list/detail/create/edit/delete flow."""
    from django.urls import path

    _validate_list_display_select_related(config)

    model_name = config.model._meta.model_name

    list_view = type(
        f"{model_name}_ListView",
        (TenantScopedListView,),
        {"config": config, "model": config.model},
    )
    detail_view = type(
        f"{model_name}_DetailView",
        (TenantScopedDetailView,),
        {"config": config, "model": config.model},
    )

    def _create(request, tenant_slug):
        return tenant_scoped_create_or_edit(request, tenant_slug, config=config)

    def _edit(request, tenant_slug, pk):
        return tenant_scoped_create_or_edit(request, tenant_slug, config=config, pk=pk)

    def _delete(request, tenant_slug, pk):
        return tenant_scoped_delete(request, tenant_slug, config=config, pk=pk)

    return [
        path(f"{model_name}/", list_view.as_view(), name=f"{model_name}_list"),
        path(f"{model_name}/new/", _create, name=f"{model_name}_create"),
        path(f"{model_name}/<int:pk>/", detail_view.as_view(), name=f"{model_name}_detail"),
        path(f"{model_name}/<int:pk>/edit/", _edit, name=f"{model_name}_edit"),
        path(f"{model_name}/<int:pk>/delete/", _delete, name=f"{model_name}_delete"),
    ]
