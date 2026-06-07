from django.urls import path

from . import views

urlpatterns = [
    path("", views.SysAdminDashboard.as_view(), name="dashboard"),
    path("tenants/", views.TenantListView.as_view(), name="tenant_list"),
    path("tenants/new/", views.tenant_create, name="tenant_create"),
    path("tenants/<int:tenant_id>/", views.tenant_detail, name="tenant_detail"),
    path("tenants/<int:tenant_id>/edit/", views.tenant_edit, name="tenant_edit"),
    path(
        "tenants/<int:tenant_id>/modules/<int:module_id>/toggle/",
        views.tenant_module_toggle,
        name="tenant_module_toggle",
    ),
    path("tenants/<int:tenant_id>/subscription/", views.subscription_edit, name="subscription_edit"),
    path("sysadmins/", views.sysadmin_user_list, name="sysadmin_list"),
    path("sysadmins/new/", views.sysadmin_user_create, name="sysadmin_create"),
    path("activity/", views.SysActivityView.as_view(), name="activity"),
]
