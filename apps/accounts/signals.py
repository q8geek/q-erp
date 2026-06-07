"""Auth-related signal handlers (login/logout/failed logins -> ActivityLog)."""
from __future__ import annotations

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.utils import timezone


def _client_meta(request):
    if request is None:
        return {"ip": "", "ua": ""}
    ip = request.META.get("REMOTE_ADDR", "")
    ua = request.META.get("HTTP_USER_AGENT", "")[:255]
    return {"ip": ip, "ua": ua}


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    from apps.activity.models import ActivityLog

    meta = _client_meta(request)
    user.last_seen_at = timezone.now()
    # Skip full_clean on this per-login write — it would otherwise run the
    # uniqueness SELECTs against auth_user on every login. The User object
    # has already passed validation when it was created/edited; touching
    # last_seen_at can't change any invariant the check enforces.
    user.save(update_fields=["last_seen_at"], _skip_clean=True)
    ActivityLog.objects.create(
        tenant=getattr(user, "tenant", None),
        actor=user,
        actor_username_snapshot=user.get_username(),
        category=ActivityLog.Category.AUTH,
        action="user.login",
        ip_address=meta["ip"],
        user_agent=meta["ua"],
        request_method="POST",
        request_path=request.path if request else "",
        status_code=200,
    )


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    from apps.activity.models import ActivityLog

    meta = _client_meta(request)
    ActivityLog.objects.create(
        tenant=getattr(user, "tenant", None) if user else None,
        actor=user if user else None,
        actor_username_snapshot=user.get_username() if user else "",
        category=ActivityLog.Category.AUTH,
        action="user.logout",
        ip_address=meta["ip"],
        user_agent=meta["ua"],
        request_method="POST",
        request_path=request.path if request else "",
        status_code=200,
    )


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request, **kwargs):
    from apps.activity.models import ActivityLog

    meta = _client_meta(request)
    username = (credentials or {}).get("username") or (credentials or {}).get("email") or ""
    ActivityLog.objects.create(
        tenant=None,
        actor=None,
        actor_username_snapshot=str(username)[:150],
        category=ActivityLog.Category.AUTH,
        action="user.login_failed",
        ip_address=meta["ip"],
        user_agent=meta["ua"],
        request_method="POST",
        request_path=request.path if request else "",
        status_code=401,
    )
