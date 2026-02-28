"""
Base settings shared across all environments.
"""

import os
from pathlib import Path

import environ

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Environment variables
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
)

# Read .env file if it exists
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY", default="django-insecure-CHANGE-THIS-IN-PRODUCTION")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
    "social_django",
]

LOCAL_APPS = [
    "apps.core.apps.CoreConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.authn.apps.AuthnConfig",
    "apps.authz.apps.AuthzConfig",
    "apps.sessions.apps.SessionsConfig",
    "apps.auditing.apps.AuditingConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.ActorTrackingMiddleware",  # Track current actor for audit fields
    "apps.sessions.middleware.SessionTrackingMiddleware",  # Track session activity
    "apps.auditing.middleware.AuditingMiddleware",  # Capture request context for audit logging
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Custom User Model
AUTH_USER_MODEL = "accounts.Principal"

# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases
DATABASES = {
    "default": env.db("DATABASE_URL", default="sqlite:///db.sqlite3"),
}

# Enable async database support with psycopg3
if DATABASES.get("default", {}).get("ENGINE") == "django.db.backends.postgresql":
    if "OPTIONS" not in DATABASES["default"]:
        DATABASES["default"]["OPTIONS"] = {}
    DATABASES["default"]["OPTIONS"].update(
        {
            "pool": {
                "min_size": env.int("DATABASE_POOL_MIN_SIZE", default=2),
                "max_size": env.int("DATABASE_POOL_MAX_SIZE", default=10),
                "timeout": env.int("DATABASE_POOL_TIMEOUT", default=30),
            }
        }
    )

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": 8,
        },
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Password Hasher Configuration (Argon2 for enterprise security)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

# Authentication Backends
AUTHENTICATION_BACKENDS = [
    "apps.authn.backends.EmailBackend",
    "apps.authn.backends.UsernameBackend",
    "apps.authn.backends.PhoneBackend",
    "apps.authn.backends.PasswordlessBackend",
    "social_core.backends.google.GoogleOAuth2",
    "social_core.backends.github.GithubOAuth2",
    "social_core.backends.microsoft.MicrosoftOAuth2",
    "social_core.backends.apple.AppleIdAuth",
    "django.contrib.auth.backends.ModelBackend",
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = []

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.sessions.authentication.DualAuthentication",  # JWT (our own) + cookie session
    ),
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

# ForgeAPIView exception handler (used by apps.core.api.base.ForgeAPIView)
FORGE_EXCEPTION_HANDLER = "apps.authn.exception_handler.authn_exception_handler"

# JWT Settings are now managed by the authn app (AUTHN["ACCESS_TOKEN_LIFETIME_SECONDS"]).
# SimpleJWT has been removed; tokens are issued by apps.authn.services.jwt.JWTService.

# CORS Settings
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:3000", "http://localhost:8000"])
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]

# DRF Spectacular Settings (API Documentation)
SPECTACULAR_SETTINGS = {
    "TITLE": "Backend API",
    "DESCRIPTION": "Production-grade Django 5 Backend API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api",
}

# Cache Configuration (default to local memory, override in prod if needed)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "default-cache",
    }
}

# Session configuration (database-backed by default, no Redis required)
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 1209600  # 2 weeks
SESSION_SAVE_EVERY_REQUEST = False

# =============================================================================
# Core auditing / actor attribution
# =============================================================================

# When enabled, models that define actor fields (created_by/updated_by) will
# require an actor to be resolvable (explicit, request context, or system actor)
# so audit attribution is never missing.
CORE_ENFORCE_ACTOR = env.bool("CORE_ENFORCE_ACTOR", default=False)

# Celery Configuration (optional - only used if Celery is installed)
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000

# Email Configuration (External SMTP - SES/Postmark ready)
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@example.com")
SERVER_EMAIL = env("SERVER_EMAIL", default="server@example.com")

# Security Settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
SESSION_COOKIE_HTTPONLY = True

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
        "require_debug_true": {
            "()": "django.utils.log.RequireDebugTrue",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "django.log",
            "maxBytes": 1024 * 1024 * 15,  # 15MB
            "backupCount": 10,
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

# =============================================================================
# Social Authentication Configuration
# =============================================================================

# Python Social Auth settings
SOCIAL_AUTH_JSONFIELD_ENABLED = True
SOCIAL_AUTH_URL_NAMESPACE = "social"
SOCIAL_AUTH_REDIRECT_IS_HTTPS = env.bool("SOCIAL_AUTH_REDIRECT_IS_HTTPS", default=False)

# Social Auth Pipeline
SOCIAL_AUTH_PIPELINE = (
    "social_core.pipeline.social_auth.social_details",
    "social_core.pipeline.social_auth.social_uid",
    "social_core.pipeline.social_auth.auth_allowed",
    "social_core.pipeline.social_auth.social_user",
    "social_core.pipeline.user.get_username",
    "social_core.pipeline.social_auth.associate_by_email",
    "social_core.pipeline.user.create_user",
    "social_core.pipeline.social_auth.associate_user",
    "social_core.pipeline.social_auth.load_extra_data",
    "social_core.pipeline.user.user_details",
)

# Google OAuth2
SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = env("GOOGLE_OAUTH2_KEY", default="")
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = env("GOOGLE_OAUTH2_SECRET", default="")
SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE = [
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

# GitHub OAuth
SOCIAL_AUTH_GITHUB_KEY = env("GITHUB_OAUTH_KEY", default="")
SOCIAL_AUTH_GITHUB_SECRET = env("GITHUB_OAUTH_SECRET", default="")
SOCIAL_AUTH_GITHUB_SCOPE = ["user:email"]

# Microsoft OAuth2
SOCIAL_AUTH_MICROSOFT_GRAPH_KEY = env("MICROSOFT_OAUTH_KEY", default="")
SOCIAL_AUTH_MICROSOFT_GRAPH_SECRET = env("MICROSOFT_OAUTH_SECRET", default="")

# Apple Sign-In
SOCIAL_AUTH_APPLE_ID_CLIENT = env("APPLE_CLIENT_ID", default="")
SOCIAL_AUTH_APPLE_ID_TEAM = env("APPLE_TEAM_ID", default="")
SOCIAL_AUTH_APPLE_ID_KEY = env("APPLE_KEY_ID", default="")
SOCIAL_AUTH_APPLE_ID_SECRET = env("APPLE_PRIVATE_KEY", default="")
SOCIAL_AUTH_APPLE_ID_SCOPE = ["email", "name"]

# Login/Logout URLs for social auth
LOGIN_URL = "/api/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# =============================================================================
# Accounts App Configuration
# =============================================================================

# MFA Settings
MFA_ISSUER_NAME = env("MFA_ISSUER_NAME", default="App")

# Account Lockout Settings
ACCOUNT_LOCKOUT_ATTEMPTS = env.int("ACCOUNT_LOCKOUT_ATTEMPTS", default=5)
ACCOUNT_LOCKOUT_DURATION_MINUTES = env.int("ACCOUNT_LOCKOUT_DURATION_MINUTES", default=30)

# Verification Token Settings
EMAIL_VERIFICATION_EXPIRY_HOURS = env.int("EMAIL_VERIFICATION_EXPIRY_HOURS", default=24)
PASSWORD_RESET_EXPIRY_HOURS = env.int("PASSWORD_RESET_EXPIRY_HOURS", default=24)
PASSWORDLESS_LOGIN_EXPIRY_HOURS = env.int("PASSWORDLESS_LOGIN_EXPIRY_HOURS", default=1)

# Frontend URL for email links
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:3000")


AUDITING = {
    "ENABLED": True,
    # What to audit
    "AUDITED_APPS": ["accounts", "authn", "authz", "sessions"],
    # "AUDITED_MODELS": {
    #     # "app_label.ModelName": {...}
    #     "accounts.UserAccount": {"exclude_fields": ["created_at", "status"]},
    # },
    "EXCLUDED_MODELS": ["admin.LogEntry"],
    # Outbox backends
    "BACKENDS": ["file"],
    "BACKEND_OPTIONS": {
        "file": {"path": "logs/audit", "rotate_daily": True, "compress": False},
    },
    # Snapshots / deltas
    "TRACK_DELTAS": True,
    "SNAPSHOT_ON_CREATE": True,
    "SNAPSHOT_ON_DELETE": True,
    "SNAPSHOT_INTERVAL": 10,  # 0 = always store snapshot
    # Integrity + compression
    "INTEGRITY_ENABLED": True,
    "INTEGRITY_ALGORITHM": "sha256",
    "COMPRESSION_ENABLED": False,
    "COMPRESSION_ALGORITHM": "zlib",
    "COMPRESSION_THRESHOLD": 1024,
    # Security/compliance controls
    "GLOBAL_EXCLUDE_FIELDS": ["password", "token", "secret", "key"],
    "UNDO_ENABLED": True,
    "MAX_UNDO_DEPTH": 10,
    "RETENTION_DAYS": None,
}
