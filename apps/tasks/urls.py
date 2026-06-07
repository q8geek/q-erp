from django.urls import path

from apps.core.crud import ModuleCRUDConfig, build_module_urls

from .models import Task
from .views import MyTasksView


class TaskConfig(ModuleCRUDConfig):
    model = Task
    fields = ["title", "description", "project", "assignee", "status", "priority", "due_date"]
    list_display = ["title", "project", "assignee", "status", "priority", "due_date"]
    list_select_related = ["project", "assignee"]
    url_namespace = "tasks"
    module_code = "tasks"


urlpatterns = [
    path("my/", MyTasksView.as_view(), name="my_tasks"),
] + build_module_urls(TaskConfig)
