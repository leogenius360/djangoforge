"""
Exception handler for the authn subsystem.

Maps the ``AuthenticationError`` hierarchy to structured HTTP responses,
ensuring internal details never leak to clients.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apps.authn.exceptions import (
    AccountLockedError,
    AuthenticationError,
    CooldownActiveError,
    MFARequiredError,
    PasswordValidationError,
    RateLimitExceededError,
)
from apps.core.api.base import api_response

if TYPE_CHECKING:
    from django.http import JsonResponse

logger = logging.getLogger(__name__)


def authn_exception_handler(exc: Exception, context: dict) -> JsonResponse | None:
    """Map ``AuthenticationError`` subclasses to JSON responses.

    For non-authn exceptions, returns ``None`` so that the base
    ``ForgeAPIView`` can handle unknown exceptions.
    """
    if isinstance(exc, AuthenticationError):
        # Log the internal detail at warning level (never sent to client)
        internal_detail = str(exc)
        if internal_detail != exc.client_message:
            logger.warning(
                "AuthenticationError [%s]: %s",
                type(exc).__name__,
                internal_detail,
            )

        data: dict = {
            "detail": exc.client_message,
            "error_code": type(exc).__name__,
        }

        # Attach extra context for specific exception types
        if isinstance(exc, AccountLockedError) and exc.locked_until:
            data["locked_until"] = exc.locked_until.isoformat()

        if isinstance(exc, MFARequiredError):
            data["mfa_required"] = True
            data["mfa_token"] = exc.mfa_token

        if isinstance(exc, RateLimitExceededError) and exc.retry_after:
            data["retry_after"] = exc.retry_after

        if isinstance(exc, CooldownActiveError) and exc.retry_after:
            data["retry_after"] = exc.retry_after

        if isinstance(exc, PasswordValidationError) and exc.errors:
            data["validation_errors"] = exc.errors

        return api_response(data, status=exc.status_code)

    return None
