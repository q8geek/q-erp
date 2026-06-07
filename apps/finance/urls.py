from apps.core.crud import ModuleCRUDConfig, build_module_urls

from .models import Account


class AccountConfig(ModuleCRUDConfig):
    model = Account
    fields = ["code", "name", "type", "parent", "is_active"]
    list_display = ["code", "name", "type", "is_active"]
    url_namespace = "finance"
    module_code = "finance"


urlpatterns = build_module_urls(AccountConfig)
