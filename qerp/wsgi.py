"""WSGI config for qerp project."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "qerp.settings.dev")

application = get_wsgi_application()
