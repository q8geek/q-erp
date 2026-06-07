from django.apps import AppConfig


class StatisticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.statistics"
    label = "statistics"

    def ready(self):
        from . import widgets  # noqa: F401 (registers built-in widgets)
