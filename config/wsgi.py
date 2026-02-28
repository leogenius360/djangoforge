"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Use centralized settings selection utility
from config.settings_selector import get_settings_module

# Set the appropriate settings module (defaults to prod for wsgi.py)
# The utility handles all cases including package-only "config.settings"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", get_settings_module(default_env="prod"))

application = get_wsgi_application()
