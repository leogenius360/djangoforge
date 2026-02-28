"""
Development settings.
"""

from .base import *  # noqa: F401, F403

# Debug mode
DEBUG = True
ALLOWED_HOSTS = ["*"]

# Django Debug Toolbar
INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
MIDDLEWARE = [
    "debug_toolbar.middleware.DebugToolbarMiddleware",
] + MIDDLEWARE  # noqa: F405
INTERNAL_IPS = ["127.0.0.1"]

# Email backend
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# CORS
CORS_ALLOW_ALL_ORIGINS = True

# Security (disabled for dev)
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Sessions and cache already configured in base.py (no overrides needed)

# Use SQLite for development (no Docker/PostgreSQL required)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}

# Alternative: Keep PostgreSQL but with fallback to SQLite
# Uncomment below and comment above if you want to use PostgreSQL when available
# import os
# if os.path.exists("/.dockerenv") or env.bool("USE_POSTGRES", default=False):
#     # Use PostgreSQL from base.py
#     pass
# else:
#     # Fallback to SQLite
#     DATABASES = {
#         "default": {
#             "ENGINE": "django.db.backends.sqlite3",
#             "NAME": BASE_DIR / "db.sqlite3",
#         }
#     }
