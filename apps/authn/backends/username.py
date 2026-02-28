"""
Username authentication backend.

Credential verification only. Session creation is handled by
``AuthenticationService``.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

from .base import BaseAccountsBackend

User = get_user_model()


class UsernameBackend(BaseAccountsBackend):
    """Authenticate by username and password."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        try:
            user = User.objects.get(username__iexact=username)
        except User.DoesNotExist:
            self._prevent_timing_attack(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
