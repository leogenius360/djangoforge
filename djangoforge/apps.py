"""DjangoForge application configuration."""

from django.apps import AppConfig


class DjangoForgeConfig(AppConfig):
    """AppConfig for the djangoforge package."""

    name = "djangoforge"
    verbose_name = "DjangoForge"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from djangoforge.settings import forge_settings

        forge_settings.validate()

        # Import checks so they are registered with Django's checks framework.
        import djangoforge.checks  # noqa: F401

        # Ensure models in sub-packages are discovered by Django.
        import djangoforge.events.models  # noqa: F401
