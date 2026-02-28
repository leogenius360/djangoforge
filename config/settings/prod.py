"""
Production settings.
"""

from .base import *  # noqa: F401, F403

# Security - Enforce required environment variables
DEBUG = False
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")  # noqa: F405

# CRITICAL: Fail fast if SECRET_KEY is not properly configured
if SECRET_KEY.startswith("django-insecure-"):  # noqa: F405
    raise ValueError(
        "Production deployment requires a secure SECRET_KEY. "
        "Set the SECRET_KEY environment variable to a strong, random value. "
        "Generate one with: python -c 'from django.core.management.utils "
        "import get_random_secret_key; print(get_random_secret_key())'"
    )

# Database - required in production
DATABASES = {  # noqa: F405
    "default": env.db("DATABASE_URL"),  # noqa: F405
}

# Security settings
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# CORS
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS")  # noqa: F405

# Static files
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
