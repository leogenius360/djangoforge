"""
Base authentication backend.

Provides common functionality for authentication backends:
- Account status checking (active, locked)
- Timing attack prevention

Session creation is handled by ``AuthenticationService``, NOT by backends.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from apps.authn.settings import authn_settings

logger = logging.getLogger(__name__)


class BaseAccountsBackend(ModelBackend):
    """Abstract base class for authentication backends.

    Backends are responsible ONLY for credential verification.
    Session creation is handled by ``AuthenticationService``.
    """

    def user_can_authenticate(self, user):
        """Check if user can authenticate.

        Extends default to check:
        - Account active status
        - Account lock status
        """
        is_active = getattr(user, "is_active", None)
        is_locked = getattr(user, "is_locked", False)
        return is_active and not is_locked

    def _prevent_timing_attack(self, password):
        """Run password hasher to prevent timing attacks.

        Ensures consistent response time whether or not a user exists.
        """
        if not authn_settings.CONSTANT_TIME_BACKEND_RESPONSES:
            return
        user_model = get_user_model()
        user_model().set_password(password)

    def get_user_model(self):
        return get_user_model()
