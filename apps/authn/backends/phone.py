"""
Phone authentication backend.

Credential verification only. Session creation is handled by
``AuthenticationService``.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

from .base import BaseAccountsBackend

User = get_user_model()


class PhoneBackend(BaseAccountsBackend):
    """Authenticate by phone number and password.

    Requires the phone number to be verified.
    """

    def authenticate(self, request, phone_number=None, password=None, **kwargs):
        if phone_number is None:
            phone_number = kwargs.get("username")

        if phone_number is None or password is None:
            return None

        try:
            # phone_number now lives on Principal
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            self._prevent_timing_attack(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def user_can_authenticate(self, user):
        """Also require phone to be verified."""
        base_check = super().user_can_authenticate(user)
        # phone_verified_at now lives on Principal
        return base_check and user.is_phone_verified
