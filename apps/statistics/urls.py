from django.urls import path

from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("configure/", views.configure_view, name="configure"),
]
