"""Activity logging middleware."""
from __future__ import annotations

from django.urls import resolve, Resolver404

from .models import ActivityLog


SKIP_PREFIXES = ("/static/", "/media/", "/favicon.ico")


def _category_for(request, view_name: str | None) -> str:
    method = request.method.upper()
    path = request.path_info
    if path.startswith("/sys/"):
        return (
            ActivityLog.Category.SYSTEM_ADMIN
            if method != "GET"
            else ActivityLog.Category.SYSTEM_ADMIN
        )
    if "/admin/" in path and path.startswith("/t/"):
        return ActivityLog.Category.TENANT_ADMIN
    if path.startswith("/t/"):
        return (
            ActivityLog.Category.MODULE_WRITE
            if method in ("POST", "PUT", "PATCH", "DELETE")
            else ActivityLog.Category.MODULE_READ
        )
    return ActivityLog.Category.OTHER


def _action_from_view(view_name: str | None, method: str) -> str:
    if not view_name:
        return f"http.{method.lower()}"
    # `dashboard:home` -> "dashboard.home"; with method suffix for writes
    base = view_name.replace(":", ".")
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        return f"{base}.{method.lower()}"
    return base


class ActivityLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._log(request, response)
        except Exception:
            # Never let logging break the request
            pass
        return response

    def _log(self, request, response):
        path = request.path_info
        if any(path.startswith(p) for p in SKIP_PREFIXES):
            return
        user = getattr(request, "user", None)
        # Log unauthenticated traffic only for failed login (handled by signals).
        if user is None or not user.is_authenticated:
            return
        # Skip the login page noise (auth signals cover real auth events).
        if path.startswith("/accounts/login") or path.startswith("/accounts/logout"):
            return

        try:
            match = resolve(path)
            view_name = match.view_name
        except Resolver404:
            view_name = None

        extra = getattr(request, "_qerp_activity_extra", None) or {}
        action = extra.get("action") or _action_from_view(view_name, request.method)
        category = _category_for(request, view_name)

        ActivityLog.objects.create(
            tenant=getattr(request, "tenant", None),
            actor=user,
            actor_username_snapshot=user.get_username(),
            category=category,
            action=action[:120],
            object_type=extra.get("object_type", "")[:120],
            object_id=str(extra.get("object_id", ""))[:64],
            object_repr=extra.get("object_repr", "")[:255],
            ip_address=request.META.get("REMOTE_ADDR", ""),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            request_method=request.method,
            request_path=path[:512],
            status_code=getattr(response, "status_code", None),
            extra=extra.get("extra"),
        )
