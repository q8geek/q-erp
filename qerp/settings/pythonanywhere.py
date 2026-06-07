"""Settings for the PythonAnywhere free-tier deployment.

Inherits the hardening posture from prod.py (HTTPS-aware cookies, env-var
fail-fast on SECRET_KEY/ALLOWED_HOSTS) but adapts to PA-specific reality:

  * PA free tier does NOT offer Postgres — use SQLite on the persistent
    home filesystem. The DB file lives outside the repo so `git pull`
    doesn't touch it.
  * PA terminates TLS upstream on *.pythonanywhere.com. We do NOT control
    that proxy, so SECURE_PROXY_SSL_HEADER is intentionally unset (trusting
    an unverified X-Forwarded-Proto is the easier-to-misuse failure mode
    than not trusting it).
  * SECURE_SSL_REDIRECT and SECURE_HSTS_SECONDS default OFF — the user
    doesn't own *.pythonanywhere.com and shouldn't ship a 1-year HSTS pin
    on a hostname they don't control. Both are env-overridable for users
    who attach a custom domain on PA's paid tier.

Required env vars (set in the PA WSGI config file):
  DJANGO_SECRET_KEY      Long random string. Fail-fast at import if unset.
  DJANGO_ALLOWED_HOSTS   Comma-separated. Usually "<username>.pythonanywhere.com".

Optional env vars:
  QERP_DB_PATH           Default: <BASE_DIR>/../qerp-data/db.sqlite3
  QERP_MEDIA_ROOT        Default: <BASE_DIR>/../qerp-data/media
  DJANGO_SSL_REDIRECT    Default: "0". Set "1" only on custom-domain deploys.
  DJANGO_HSTS_SECONDS    Default: 0. Set after verifying TLS chain end-to-end.
"""
import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import BASE_DIR


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"Required environment variable {name!r} is not set or empty."
        )
    return value


DEBUG = False

SECRET_KEY = _require("DJANGO_SECRET_KEY")

_raw_hosts = _require("DJANGO_ALLOWED_HOSTS")
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(",") if h.strip()]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must contain at least one non-empty host."
    )

# Persistent data sits OUTSIDE the repo so `git pull` is non-destructive.
_default_data_root = BASE_DIR.parent / "qerp-data"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get(
            "QERP_DB_PATH", str(_default_data_root / "db.sqlite3")
        ),
    }
}

MEDIA_ROOT = os.environ.get(
    "QERP_MEDIA_ROOT", str(_default_data_root / "media")
)
# Static files are served by PA's "Static files" web-tab mapping pointed at
# STATIC_ROOT (set in base.py to <BASE_DIR>/staticfiles). Run
# `python manage.py collectstatic` on first deploy and after static changes.

# --- Hardening (mirrors prod.py for cookies; HTTPS-redirect & HSTS off
# by default because we don't control the upstream proxy on PA free tier)
SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SSL_REDIRECT", "0") == "1"
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"

X_FRAME_OPTIONS = "DENY"
