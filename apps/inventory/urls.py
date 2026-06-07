from apps.core.crud import ModuleCRUDConfig, build_module_urls

from .models import Item, Warehouse


class WarehouseConfig(ModuleCRUDConfig):
    model = Warehouse
    fields = ["code", "name", "is_active"]
    list_display = ["code", "name", "is_active"]
    url_namespace = "inventory"
    module_code = "inventory"


class ItemConfig(ModuleCRUDConfig):
    model = Item
    fields = ["sku", "name", "uom", "default_warehouse", "is_active"]
    list_display = ["sku", "name", "uom", "is_active"]
    list_select_related = ["default_warehouse"]
    url_namespace = "inventory"
    module_code = "inventory"


urlpatterns = build_module_urls(WarehouseConfig) + build_module_urls(ItemConfig)
