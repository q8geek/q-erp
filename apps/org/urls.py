from apps.core.crud import ModuleCRUDConfig, build_module_urls

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
    list_select_related = ["user", "department", "team"]
    url_namespace = "org"
    module_code = "org"


urlpatterns = (
    build_module_urls(DepartmentConfig)
    + build_module_urls(TeamConfig)
    + build_module_urls(MembershipConfig)
)
