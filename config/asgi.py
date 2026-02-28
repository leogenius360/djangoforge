"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

# Use centralized settings selection utility
from config.settings_selector import get_settings_module

# Set the appropriate settings module (defaults to prod for asgi.py)
# The utility handles all cases including package-only "config.settings"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", get_settings_module(default_env="production"))

application = get_asgi_application()
