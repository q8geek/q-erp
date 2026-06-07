from __future__ import annotations

from django.views.generic import TemplateView

from apps.core.mixins import TenantRequiredMixin


class HomeView(TenantRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tenant = self.request.tenant
        ctx["tenant"] = tenant
        ctx["active_modules"] = sorted(tenant.active_module_codes())
        ctx["seats_used"] = tenant.active_user_count()
        ctx["seats_limit"] = tenant.effective_seat_limit()
        return ctx
