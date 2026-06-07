"""Development settings (SQLite)."""
from .base import *  # noqa: F401,F403
from .base import BASE_DIR

DEBUG = True
ALLOWED_HOSTS = ["*"]

SECRET_KEY = "dev-insecure-key-do-not-use-in-production"  # noqa: S105

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Fail fast if a future settings module forgets to override SECRET_KEY.
assert SECRET_KEY, "SECRET_KEY must be set by the environment settings module."
