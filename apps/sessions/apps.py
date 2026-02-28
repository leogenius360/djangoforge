"""Sessions app configuration."""

from django.apps import AppConfig


class SessionsConfig(AppConfig):
    """Configuration for the sessions app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sessions"
    label = "user_sessions"  # Unique label to avoid conflict with django.contrib.sessions
    verbose_name = "User Sessions"

    def ready(self) -> None:
        # Register drf-spectacular OpenAPI authentication extensions so that
        # Swagger UI recognises DualAuthentication / SessionJWTAuthentication
        # and shows the "Authorize" (Bearer JWT) button correctly.
        import apps.sessions.openapi  # noqa: F401
