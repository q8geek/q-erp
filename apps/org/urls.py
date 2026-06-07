from django.urls import path

from apps.core.crud import build_module_urls

from .views import (
    DepartmentConfig,
    DepartmentDetailView,
    MembershipConfig,
    TeamConfig,
    TeamDetailView,
)


# Custom detail patterns are registered BEFORE `build_module_urls` so they
# take precedence over the generic detail view (Django URL resolution is
# first-match-wins).
_custom_overrides = [
    path(
        "department/<int:pk>/",
        DepartmentDetailView.as_view(),
        name="department_detail",
    ),
    path(
        "team/<int:pk>/",
        TeamDetailView.as_view(),
        name="team_detail",
    ),
]

urlpatterns = (
    _custom_overrides
    + build_module_urls(DepartmentConfig)
    + build_module_urls(TeamConfig)
    + build_module_urls(MembershipConfig)
)
