from apps.core.crud import ModuleCRUDConfig, build_module_urls

from .models import Quote, SalesOrder, SalesOrderLine


class QuoteConfig(ModuleCRUDConfig):
    model = Quote
    fields = ["number", "customer", "status", "total"]
    list_display = ["number", "customer", "status", "total"]
    list_select_related = ["customer"]
    url_namespace = "sales"
    module_code = "sales"


class SalesOrderConfig(ModuleCRUDConfig):
    model = SalesOrder
    fields = ["number", "customer", "status", "total"]
    list_display = ["number", "customer", "status", "total"]
    list_select_related = ["customer"]
    url_namespace = "sales"
    module_code = "sales"


class SalesOrderLineConfig(ModuleCRUDConfig):
    model = SalesOrderLine
    fields = ["order", "item", "qty", "unit_price"]
    list_display = ["order", "item", "qty", "unit_price"]
    list_select_related = ["order", "item"]
    url_namespace = "sales"
    module_code = "sales"


urlpatterns = (
    build_module_urls(QuoteConfig)
    + build_module_urls(SalesOrderConfig)
    + build_module_urls(SalesOrderLineConfig)
)
