"""Authorization app configuration."""

from django.apps import AppConfig


class AuthzConfig(AppConfig):
    """Configuration for the authz app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.authz"
    verbose_name = "Authorization"
