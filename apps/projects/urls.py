from apps.core.crud import ModuleCRUDConfig, build_module_urls

from .models import Project, Timesheet


class ProjectConfig(ModuleCRUDConfig):
    model = Project
    fields = ["code", "name", "customer", "status", "start_date", "end_date"]
    list_display = ["code", "name", "customer", "status", "start_date", "end_date"]
    list_select_related = ["customer"]
    url_namespace = "projects"
    module_code = "projects"


class TimesheetConfig(ModuleCRUDConfig):
    model = Timesheet
    fields = ["user", "date", "task", "hours", "notes"]
    list_display = ["user", "date", "task", "hours"]
    list_select_related = ["user", "task"]
    url_namespace = "projects"
    module_code = "projects"


urlpatterns = build_module_urls(ProjectConfig) + build_module_urls(TimesheetConfig)
