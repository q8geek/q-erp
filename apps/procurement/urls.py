from apps.core.crud import ModuleCRUDConfig, build_module_urls

from .models import PurchaseOrder, Supplier


class SupplierConfig(ModuleCRUDConfig):
    model = Supplier
    fields = ["code", "name", "contact_email", "contact_phone", "is_active"]
    list_display = ["code", "name", "contact_email", "is_active"]
    url_namespace = "procurement"
    module_code = "procurement"


class PurchaseOrderConfig(ModuleCRUDConfig):
    model = PurchaseOrder
    fields = ["number", "supplier", "status", "total"]
    list_display = ["number", "supplier", "status", "total"]
    list_select_related = ["supplier"]
    url_namespace = "procurement"
    module_code = "procurement"


urlpatterns = build_module_urls(SupplierConfig) + build_module_urls(PurchaseOrderConfig)
