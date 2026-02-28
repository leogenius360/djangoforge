"""
Staging settings.
"""

import os

from .base import *  # noqa: F401, F403

# Security
DEBUG = env.bool("DEBUG", default=False)  # noqa: F405
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])  # noqa: F405

# Use PostgreSQL in staging
DATABASES = {  # noqa: F405
    "default": env.db("DATABASE_URL"),  # noqa: F405
}

# Use Redis in staging
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL"),  # noqa: F405
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "backend_staging",
    }
}

# Email - Use external SMTP
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# Security settings for staging
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 0  # Don't enforce HSTS in staging
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Logging - Include file logging for staging
log_dir = env("LOG_DIR", default=str(BASE_DIR / "logs"))  # noqa: F405
os.makedirs(log_dir, exist_ok=True)
LOGGING["handlers"]["file"]["filename"] = os.path.join(log_dir, "staging.log")  # noqa: F405
LOGGING["loggers"]["django"]["handlers"] = ["console", "file"]  # noqa: F405
LOGGING["loggers"]["django.request"]["handlers"] = ["console", "file"]  # noqa: F405

# CORS - Restrict to specific origins
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])  # noqa: F405
