"""Tasks-specific views (beyond the generic CRUD)."""
from __future__ import annotations

from django.views.generic import ListView

from apps.core.mixins import TenantPermissionRequiredMixin

from .models import Task


class MyTasksView(TenantPermissionRequiredMixin, ListView):
    template_name = "tasks/my_tasks.html"
    context_object_name = "tasks"
    paginate_by = 50
    required_permission = "tasks.view_tasks"

    def get_queryset(self):
        return (
            Task.objects.filter(assignee=self.request.user)
            .exclude(status=Task.Status.DONE)
            .exclude(status=Task.Status.CANCELLED)
            .order_by("due_date", "-pk")
        )
