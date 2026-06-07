from apps.core.crud import ModuleCRUDConfig, build_module_urls

from .models import BillOfMaterials, BOMLine, WorkOrder


class BOMConfig(ModuleCRUDConfig):
    model = BillOfMaterials
    fields = ["item", "version", "is_active"]
    list_display = ["item", "version", "is_active"]
    list_select_related = ["item"]
    url_namespace = "manufacturing"
    module_code = "manufacturing"


class BOMLineConfig(ModuleCRUDConfig):
    model = BOMLine
    fields = ["bom", "component_item", "qty", "uom"]
    list_display = ["bom", "component_item", "qty", "uom"]
    list_select_related = ["bom", "component_item"]
    url_namespace = "manufacturing"
    module_code = "manufacturing"


class WorkOrderConfig(ModuleCRUDConfig):
    model = WorkOrder
    fields = ["number", "item", "qty", "status", "due_date"]
    list_display = ["number", "item", "qty", "status", "due_date"]
    list_select_related = ["item"]
    url_namespace = "manufacturing"
    module_code = "manufacturing"


urlpatterns = (
    build_module_urls(BOMConfig)
    + build_module_urls(BOMLineConfig)
    + build_module_urls(WorkOrderConfig)
)
