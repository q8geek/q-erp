from django.urls import path

from . import views

urlpatterns = [
    path("", views.InboxView.as_view(), name="inbox"),
    path("threads/", views.ThreadListView.as_view(), name="thread_list"),
    path("threads/<int:pk>/", views.thread_detail, name="thread_detail"),
    path("new/", views.new_direct, name="new_direct"),
]
