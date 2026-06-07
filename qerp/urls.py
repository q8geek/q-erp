"""Top-level URL configuration."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from apps.accounts.views import post_login_redirect


urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("post-login/", post_login_redirect, name="post_login_redirect"),
    path("sys/", include(("apps.sys_admin.urls", "sys_admin"), namespace="sys_admin")),
    path("t/<slug:tenant_slug>/", include("apps.tenants.tenant_urls")),
    path("", RedirectView.as_view(url="/accounts/login/", permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
