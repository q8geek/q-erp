from apps.core.crud import ModuleCRUDConfig, build_module_urls

from .models import Ticket, TicketCategory, TicketReply


class TicketCategoryConfig(ModuleCRUDConfig):
    model = TicketCategory
    fields = ["code", "name", "default_assignee", "is_active"]
    list_display = ["code", "name", "default_assignee", "is_active"]
    list_select_related = ["default_assignee"]
    url_namespace = "support_tickets"
    module_code = "support_tickets"


class TicketConfig(ModuleCRUDConfig):
    model = Ticket
    fields = ["number", "subject", "description", "category", "customer", "reporter", "assignee", "status", "priority"]
    list_display = ["number", "subject", "status", "priority", "assignee", "category"]
    list_select_related = ["category", "assignee"]
    url_namespace = "support_tickets"
    module_code = "support_tickets"


class TicketReplyConfig(ModuleCRUDConfig):
    model = TicketReply
    fields = ["ticket", "author", "body", "is_internal"]
    list_display = ["ticket", "author", "is_internal"]
    list_select_related = ["ticket", "author"]
    url_namespace = "support_tickets"
    module_code = "support_tickets"


urlpatterns = (
    build_module_urls(TicketCategoryConfig)
    + build_module_urls(TicketConfig)
    + build_module_urls(TicketReplyConfig)
)
