"""Base settings shared across environments."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY: str | None = None  # MUST be set by an environment-specific settings module.
DEBUG = False
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local apps
    "apps.core",
    "apps.accounts",
    "apps.tenants",
    "apps.activity",
    "apps.dashboard",
    "apps.tenant_admin",
    "apps.sys_admin",
    # Core modules
    "apps.finance",
    "apps.inventory",
    "apps.procurement",
    "apps.org",
    "apps.tasks",
    "apps.messaging",
    "apps.automation",
    "apps.statistics",
    # Add-on modules
    "apps.hr",
    "apps.crm",
    "apps.manufacturing",
    "apps.documents",
    "apps.sales",
    "apps.projects",
    "apps.assets",
    "apps.support_tickets",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Custom
    "apps.tenants.middleware.TenantResolutionMiddleware",
    "apps.tenants.middleware.TenantAccessMiddleware",
    "apps.tenants.middleware.SubscriptionEnforcementMiddleware",
    "apps.activity.middleware.ActivityLoggingMiddleware",
]

ROOT_URLCONF = "qerp.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.tenant_branding",
                "apps.core.context_processors.menu",
            ],
        },
    },
]

WSGI_APPLICATION = "qerp.wsgi.application"

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Cache configuration
# ---------------------------------------------------------------------------
# Default is process-local in-memory cache. This is correct for dev / single
# worker test runs, but it is critical to understand the consequences:
#
#   * Every gunicorn/uwsgi worker has its own independent cache. Invalidations
#     (e.g. menu cache bumps from tenant_module_toggle) only affect the worker
#     that handled the toggle; other workers serve stale data until their
#     copies expire or are evicted.
#   * The cache is lost on every process restart.
#
# Production deployments MUST override this with a shared backend (Redis,
# Memcached, …) via the ``DJANGO_CACHE_BACKEND`` env var, which prod.py reads.
# See README "Production deployment" for details.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "qerp-default",
    },
}

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/post-login/"
LOGOUT_REDIRECT_URL = "/accounts/login/"
