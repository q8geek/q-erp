"""Custom detail views for Department and Team.

The generic CRUD scaffold renders the model's fields and nothing else.
For org, the value-add is showing the *contents* of a department or team
(its teams and members), so we subclass the generic detail view and
inject extra context that the templates render alongside the standard
field table.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404

from apps.core.crud import ModuleCRUDConfig, TenantScopedDetailView

from .models import Department, Membership, Team


class DepartmentConfig(ModuleCRUDConfig):
    model = Department
    fields = ["code", "name", "parent", "is_active"]
    list_display = ["code", "name", "parent", "is_active"]
    list_select_related = ["parent"]
    url_namespace = "org"
    module_code = "org"


class TeamConfig(ModuleCRUDConfig):
    model = Team
    fields = ["code", "name", "department", "is_active"]
    list_display = ["code", "name", "department", "is_active"]
    list_select_related = ["department"]
    url_namespace = "org"
    module_code = "org"


class MembershipConfig(ModuleCRUDConfig):
    model = Membership
    fields = ["user", "department", "team", "title", "is_head_of_department", "is_head_of_team"]
    list_display = ["user", "department", "team", "title", "is_head_of_department", "is_head_of_team"]
    list_display_labels = {
        "is_head_of_department": "Head of dept.",
        "is_head_of_team": "Head of team",
    }
    list_select_related = ["user", "department", "team"]
    url_namespace = "org"
    module_code = "org"


class DepartmentDetailView(TenantScopedDetailView):
    """Department detail page with teams + members cards."""

    template_name = "org/department_detail.html"
    config = DepartmentConfig

    def get_object(self, queryset=None):
        return get_object_or_404(Department.objects.all(), pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        dept = self.object
        # Teams nested under this department.
        ctx["dept_teams"] = list(
            Team.objects.filter(department=dept).order_by("code")
        )
        # All memberships in the department (both team and non-team).
        ctx["dept_memberships"] = list(
            Membership.objects.filter(department=dept)
            .select_related("user", "team")
            .order_by("team__code", "user__first_name", "user__last_name", "user__username")
        )
        return ctx


class TeamDetailView(TenantScopedDetailView):
    """Team detail page with members card."""

    template_name = "org/team_detail.html"
    config = TeamConfig

    def get_object(self, queryset=None):
        return get_object_or_404(Team.objects.all(), pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        team = self.object
        ctx["team_memberships"] = list(
            Membership.objects.filter(team=team)
            .select_related("user")
            .order_by("user__first_name", "user__last_name", "user__username")
        )
        return ctx
