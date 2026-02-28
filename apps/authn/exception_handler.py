"""
DRF exception handler for the authn subsystem.

Maps the ``AuthenticationError`` hierarchy to structured HTTP responses,
ensuring internal details never leak to clients.
"""

from __future__ import annotations

import logging

from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.authn.exceptions import (
    AccountLockedError,
    AuthenticationError,
    CooldownActiveError,
    MFARequiredError,
    PasswordValidationError,
    RateLimitExceededError,
)

logger = logging.getLogger(__name__)


def authn_exception_handler(exc: Exception, context: dict) -> Response | None:
    """Map ``AuthenticationError`` subclasses to DRF responses.

    For non-authn exceptions, falls through to the default DRF handler.
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

        return Response(data, status=exc.status_code)

    return drf_exception_handler(exc, context)
