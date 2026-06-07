from __future__ import annotations

from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.views.generic import TemplateView

from apps.activity.helpers import log_change
from apps.core.access import enforce_tenant_manage
from apps.core.mixins import TenantPermissionRequiredMixin

from .models import DashboardWidget
from .registry import Widget, all_widgets, get_widget


WIDGET_CACHE_TTL_SECONDS = 30


class DashboardView(TenantPermissionRequiredMixin, TemplateView):
    template_name = "statistics/dashboard.html"
    required_permission = "statistics.view_statistics"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tenant = self.request.tenant
        active_codes = tenant.active_module_codes()
        configured = list(DashboardWidget.objects.filter(is_active=True).order_by("sort_order", "pk"))
        configured_codes = {cfg.widget_code for cfg in configured}
        # If no widgets configured yet, show all eligible widgets (initial UX)
        widgets_to_show = []
        if configured:
            for cfg in configured:
                w = get_widget(cfg.widget_code)
                if w is None:
                    continue
                if w.module != "tenants" and w.module not in active_codes:
                    continue
                widgets_to_show.append((cfg.label_override or w.label, w))
        else:
            for code, w in all_widgets().items():
                if w.module != "tenants" and w.module not in active_codes:
                    continue
                widgets_to_show.append((w.label, w))

        results = []
        for label, w in widgets_to_show:
            try:
                data = _compute_widget(tenant, self.request, w)
            except Exception as exc:  # noqa: BLE001
                data = {"value": "?", "hint": f"error: {exc}", "unit": ""}
            results.append({"label": label, "code": w.code, **data})
        ctx["widgets"] = results
        ctx["has_custom_config"] = bool(configured)
        return ctx


def _compute_widget(tenant, request, w: Widget) -> dict:
    """Compute a widget value, using a short tenant-wide cache for non-per-user widgets."""
    if w.per_user:
        # Per-user values (my tasks, unread messages) can't be tenant-cached.
        return w.compute(tenant, request)
    cache_key = f"stats:widget:{tenant.id}:{w.code}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    data = w.compute(tenant, request)
    cache.set(cache_key, data, WIDGET_CACHE_TTL_SECONDS)
    return data


def configure_view(request, tenant_slug):
    enforce_tenant_manage(request, "statistics.manage_statistics")
    tenant = request.tenant
    active_codes = tenant.active_module_codes()
    if request.method == "POST":
        # Submitted: each row may have widget_code, enabled, sort_order, label_override
        existing = {dw.widget_code: dw for dw in DashboardWidget.objects.all()}
        for code, w in all_widgets().items():
            if w.module != "tenants" and w.module not in active_codes:
                continue
            enabled = request.POST.get(f"{code}__enabled") == "on"
            sort_order = int(request.POST.get(f"{code}__sort", 0) or 0)
            label_override = (request.POST.get(f"{code}__label") or "").strip()
            cfg = existing.get(code)
            if enabled:
                if cfg is None:
                    cfg = DashboardWidget(tenant=tenant, widget_code=code)
                cfg.is_active = True
                cfg.sort_order = sort_order
                cfg.label_override = label_override
                cfg.save()
            elif cfg is not None:
                cfg.delete()
        log_change(request, action="statistics.dashboard.configure")
        messages.success(request, "Dashboard configuration saved.")
        return redirect("statistics:dashboard", tenant_slug=tenant_slug)
    rows = []
    existing = {dw.widget_code: dw for dw in DashboardWidget.objects.all()}
    for code, w in all_widgets().items():
        if w.module != "tenants" and w.module not in active_codes:
            continue
        cfg = existing.get(code)
        rows.append(
            {
                "code": code,
                "label": w.label,
                "description": w.description,
                "module": w.module,
                "enabled": cfg is not None and cfg.is_active,
                "sort_order": cfg.sort_order if cfg else 0,
                "label_override": cfg.label_override if cfg else "",
            }
        )
    return render(request, "statistics/configure.html", {"rows": rows})
