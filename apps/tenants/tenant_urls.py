"""URLs mounted under /t/<tenant_slug>/."""
from django.urls import include, path

urlpatterns = [
    path("dashboard/", include(("apps.dashboard.urls", "dashboard"), namespace="dashboard")),
    path("admin/", include(("apps.tenant_admin.urls", "tenant_admin"), namespace="tenant_admin")),
    # Core modules (always active)
    path("finance/", include(("apps.finance.urls", "finance"), namespace="finance")),
    path("inventory/", include(("apps.inventory.urls", "inventory"), namespace="inventory")),
    path("procurement/", include(("apps.procurement.urls", "procurement"), namespace="procurement")),
    path("org/", include(("apps.org.urls", "org"), namespace="org")),
    path("tasks/", include(("apps.tasks.urls", "tasks"), namespace="tasks")),
    path("messaging/", include(("apps.messaging.urls", "messaging"), namespace="messaging")),
    path("automation/", include(("apps.automation.urls", "automation"), namespace="automation")),
    path("statistics/", include(("apps.statistics.urls", "statistics"), namespace="statistics")),
    # Add-on modules
    path("hr/", include(("apps.hr.urls", "hr"), namespace="hr")),
    path("crm/", include(("apps.crm.urls", "crm"), namespace="crm")),
    path("manufacturing/", include(("apps.manufacturing.urls", "manufacturing"), namespace="manufacturing")),
    path("documents/", include(("apps.documents.urls", "documents"), namespace="documents")),
    path("sales/", include(("apps.sales.urls", "sales"), namespace="sales")),
    path("projects/", include(("apps.projects.urls", "projects"), namespace="projects")),
    path("assets/", include(("apps.assets.urls", "assets"), namespace="assets")),
    path("support_tickets/", include(("apps.support_tickets.urls", "support_tickets"), namespace="support_tickets")),
]
