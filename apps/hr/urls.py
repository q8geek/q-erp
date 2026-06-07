from apps.core.crud import ModuleCRUDConfig, build_module_urls

from .models import Employee, LeaveRequest


class EmployeeConfig(ModuleCRUDConfig):
    model = Employee
    fields = ["employee_no", "name", "department", "hire_date", "position"]
    list_display = ["employee_no", "name", "department", "position"]
    list_select_related = ["department"]
    url_namespace = "hr"
    module_code = "hr"


class LeaveRequestConfig(ModuleCRUDConfig):
    model = LeaveRequest
    fields = ["employee", "type", "start_date", "end_date", "status"]
    list_display = ["employee", "type", "start_date", "end_date", "status"]
    list_select_related = ["employee"]
    url_namespace = "hr"
    module_code = "hr"


urlpatterns = (
    build_module_urls(EmployeeConfig)
    + build_module_urls(LeaveRequestConfig)
)
