from django.apps import AppConfig


class AutomationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.automation"
    label = "automation"

    def ready(self):
        # Import action handlers so they self-register.
        from . import actions  # noqa: F401
        from . import builtin_events  # noqa: F401
