from django.urls import path

from . import views

urlpatterns = [
    path("", views.RuleListView.as_view(), name="rule_list"),
    path("new/", views.rule_create_or_edit, name="rule_create"),
    path("<int:pk>/edit/", views.rule_create_or_edit, name="rule_edit"),
    path("<int:pk>/delete/", views.rule_delete, name="rule_delete"),
    path("runs/", views.RuleRunListView.as_view(), name="rulerun_list"),
]
