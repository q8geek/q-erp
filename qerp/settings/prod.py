"""Production settings (Postgres-ready).

Operator quick reference (full details: README → "Production deployment"):

  * ``DJANGO_SECRET_KEY``    — REQUIRED. Import-time fail-fast if missing.
  * ``DJANGO_ALLOWED_HOSTS`` — REQUIRED, comma-separated. Fail-fast if empty.
  * ``DB_PASSWORD``          — REQUIRED. Fail-fast if missing.
  * ``DJANGO_SSL_REDIRECT``  — default "1". Set "0" during the first deploy
    until the TLS chain & proxy are verified; otherwise expect a redirect
    loop if the upstream proxy is not setting X-Forwarded-Proto correctly.
  * ``DJANGO_HSTS_SECONDS``  — default 31536000 (1 year). Use 60 for the
    first 24h after going live; raise only once stable. HSTS is sticky in
    browsers and cannot be rolled back from the server side.
  * ``DJANGO_CACHE_BACKEND`` — optional. Either a JSON object describing the
    default cache (e.g.
    ``{"BACKEND": "django.core.cache.backends.redis.RedisCache",
       "LOCATION": "redis://cache:6379/1"}``)
    or a bare dotted backend path. Without this, the per-process LocMemCache
    declared in base.py is used; that is only acceptable for SINGLE-WORKER
    deploys because cache invalidations do not cross worker boundaries.
  * ``X-Forwarded-Proto`` is trusted via SECURE_PROXY_SSL_HEADER. The upstream
    proxy MUST (a) set this header on every request and (b) strip any
    client-supplied copy to prevent scheme-downgrade attacks.
  * ``ALLOW_SEED_DEMO=1`` overrides the seed_demo DEBUG-only guard. CI/dev
    only — NEVER set in production.
"""
import json
import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403


def _require(name: str) -> str:
    """Read a required env var. Raise ImproperlyConfigured if missing/empty."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"Required environment variable '{name}' is not set or empty."
        )
    return value


DEBUG = False

SECRET_KEY = _require("DJANGO_SECRET_KEY")

# ALLOWED_HOSTS: comma-separated, stripped, empty entries dropped.
_raw_allowed_hosts = _require("DJANGO_ALLOWED_HOSTS")
ALLOWED_HOSTS = [h.strip() for h in _raw_allowed_hosts.split(",") if h.strip()]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must contain at least one non-empty host."
    )

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "qerp"),
        "USER": os.environ.get("DB_USER", "qerp"),
        "PASSWORD": _require("DB_PASSWORD"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# --- Hardening (HTTPS / cookies / headers) -------------------------------

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SSL_REDIRECT", "1") == "1"
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"

X_FRAME_OPTIONS = "DENY"

# --- Cache override -------------------------------------------------------
# ``DJANGO_CACHE_BACKEND`` may be one of:
#   * a JSON object string like
#       {"BACKEND": "django.core.cache.backends.redis.RedisCache",
#        "LOCATION": "redis://cache:6379/1"}
#     in which case it is used verbatim as CACHES["default"].
#   * a bare dotted path like
#       django.core.cache.backends.memcached.PyMemcacheCache
#     in which case it becomes the "BACKEND" of the default cache with no
#     additional options.
# When unset, the LocMemCache from base.py is kept (single-worker only).
_cache_url = os.environ.get("DJANGO_CACHE_BACKEND", "").strip()
if _cache_url:
    if _cache_url.startswith("{"):
        try:
            CACHES = {"default": json.loads(_cache_url)}
        except json.JSONDecodeError as exc:
            raise ImproperlyConfigured(
                f"DJANGO_CACHE_BACKEND is not valid JSON: {exc}"
            ) from exc
    else:
        CACHES = {"default": {"BACKEND": _cache_url}}
