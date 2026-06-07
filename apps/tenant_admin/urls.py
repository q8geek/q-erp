from django.urls import path

from . import views

urlpatterns = [
    path("", views.TenantAdminHome.as_view(), name="home"),
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/new/", views.user_create_or_edit, name="user_create"),
    path("users/<int:user_id>/edit/", views.user_create_or_edit, name="user_edit"),
    path("users/<int:user_id>/delete/", views.user_delete, name="user_delete"),
    path("groups/", views.GroupListView.as_view(), name="group_list"),
    path("groups/new/", views.group_create_or_edit, name="group_create"),
    path("groups/<int:group_id>/edit/", views.group_create_or_edit, name="group_edit"),
    path("groups/<int:group_id>/delete/", views.group_delete, name="group_delete"),
    path("settings/", views.settings_view, name="settings"),
    path("activity/", views.ActivityView.as_view(), name="activity"),
]
