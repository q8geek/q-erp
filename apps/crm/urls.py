from apps.core.crud import ModuleCRUDConfig, build_module_urls

from .models import Customer, Lead, Opportunity


class LeadConfig(ModuleCRUDConfig):
    model = Lead
    fields = ["name", "source", "status", "owner"]
    list_display = ["name", "source", "status"]
    url_namespace = "crm"
    module_code = "crm"


class CustomerConfig(ModuleCRUDConfig):
    model = Customer
    fields = ["code", "name", "contact_email", "contact_phone"]
    list_display = ["code", "name", "contact_email"]
    url_namespace = "crm"
    module_code = "crm"


class OpportunityConfig(ModuleCRUDConfig):
    model = Opportunity
    fields = ["customer", "stage", "amount", "expected_close"]
    list_display = ["customer", "stage", "amount", "expected_close"]
    list_select_related = ["customer"]
    url_namespace = "crm"
    module_code = "crm"


urlpatterns = (
    build_module_urls(LeadConfig)
    + build_module_urls(CustomerConfig)
    + build_module_urls(OpportunityConfig)
)
