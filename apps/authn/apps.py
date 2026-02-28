"""Authentication app configuration."""

from django.apps import AppConfig


class AuthnConfig(AppConfig):
    """Configuration for the authn app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.authn"
    verbose_name = "Authentication"
