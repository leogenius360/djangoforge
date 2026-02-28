"""
Accounts app configuration.
"""

from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AccountsConfig(AppConfig):
    """Configuration for the accounts app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Accounts"

    def ready(self) -> None:
        """
        Validate configuration at startup and wire up signal handlers.

        Replaces Django's built-in ``update_last_login`` with a custom handler
        that satisfies ``Principal.ACTOR_REQUIRED = True`` by running the save
        under ``set_current_actor(user)``.
        """
        from django.contrib.auth.signals import user_logged_in

        from apps.accounts.signals import update_last_login

        # Django connects its built-in with dispatch_uid="update_last_login"; use the same uid.
        user_logged_in.disconnect(dispatch_uid="update_last_login")
        user_logged_in.connect(update_last_login, dispatch_uid="accounts.update_last_login")

        self._validate_config()

    @staticmethod
    def _validate_config() -> None:
        """
        Run semantic validation on accounts settings.

        In DEBUG mode, misconfiguration is logged as a warning so development
        is not blocked.  In production, it raises ``ImproperlyConfigured`` to
        fail fast.
        """
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured

        from apps.accounts.settings import validate_accounts_config

        is_valid, errors = validate_accounts_config()
        if is_valid:
            return

        message = "Accounts configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)

        if getattr(settings, "DEBUG", False):
            logger.warning(message)
        else:
            raise ImproperlyConfigured(message)
