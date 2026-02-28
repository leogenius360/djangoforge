"""
Passwordless authentication backend.

Delegates token verification to ``TokenService``. Session creation
is handled by ``AuthenticationService``.
"""

from __future__ import annotations

from .base import BaseAccountsBackend


class PasswordlessBackend(BaseAccountsBackend):
    """Authenticate by passwordless token (magic link).

    Token verification is handled by ``TokenService`` in the service layer.
    This backend exists for Django ``authenticate()`` compatibility but
    the primary passwordless flow goes through ``AuthenticationService``.
    """

    def authenticate(self, request, token=None, **kwargs):
        if token is None:
            return None

        from apps.authn.exceptions import VerificationTokenError
        from apps.authn.services.token import TokenService

        try:
            verification = TokenService.verify_token(token)
        except VerificationTokenError:
            return None

        user = verification.principal
        if self.user_can_authenticate(user):
            TokenService.consume_token(verification)
            return user
        return None

    def user_can_authenticate(self, user):
        """Require passwordless to be enabled."""
        base_check = super().user_can_authenticate(user)
        passwordless_enabled = getattr(user, "passwordless_enabled", False)
        return base_check and passwordless_enabled
