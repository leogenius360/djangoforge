"""
Authentication exception hierarchy.

All exceptions carry a security-conscious ``client_message`` that is safe to
return in HTTP responses.  Internal details are logged, never sent to the client.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


class AuthenticationError(Exception):
    """Base for all authn-domain exceptions."""

    client_message: str = "An authentication error occurred."
    status_code: int = 401

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.client_message)


# ── Credential verification ────────────────────────────────────────


class InvalidCredentialsError(AuthenticationError):
    """Credential verification failed (password, token, OTP)."""

    client_message = "Invalid credentials."
    status_code = 401


class CredentialExpiredError(AuthenticationError):
    """Credential (password, token) has expired."""

    client_message = "Credentials have expired."
    status_code = 401


class PasswordReuseError(AuthenticationError):
    """Password matches a recent historical password."""

    client_message = "Cannot reuse a recent password."
    status_code = 400


class PasswordValidationError(AuthenticationError):
    """Password does not meet policy requirements."""

    client_message = "Password does not meet requirements."
    status_code = 400

    def __init__(self, errors: list[str] | None = None, detail: str | None = None) -> None:
        self.errors = errors or []
        super().__init__(detail)


# ── Account state ──────────────────────────────────────────────────


class AccountLockedError(AuthenticationError):
    """Account is locked due to too many failed attempts."""

    client_message = "Account is temporarily locked."
    status_code = 403

    def __init__(self, locked_until: datetime | None = None, detail: str | None = None) -> None:
        self.locked_until = locked_until
        super().__init__(detail)


class AccountDisabledError(AuthenticationError):
    """Account is disabled, suspended, or deleted."""

    client_message = "Account is not available."
    status_code = 403


# ── MFA ────────────────────────────────────────────────────────────


class MFARequiredError(AuthenticationError):
    """Primary auth succeeded but MFA verification is required."""

    client_message = "MFA verification required."
    status_code = 200  # Not an error per se; signals next step

    def __init__(self, mfa_token: str, detail: str | None = None) -> None:
        self.mfa_token = mfa_token
        super().__init__(detail)


class MFAVerificationFailedError(AuthenticationError):
    """MFA code was invalid."""

    client_message = "Invalid verification code."
    status_code = 401


class MFAPendingExpiredError(AuthenticationError):
    """MFA pending session expired or not found."""

    client_message = "Session expired. Please log in again."
    status_code = 401


class MFAAlreadyEnabledError(AuthenticationError):
    """User already has active MFA."""

    client_message = "MFA is already enabled."
    status_code = 400


class MFANotEnabledError(AuthenticationError):
    """MFA is not enabled for this user."""

    client_message = "MFA is not enabled."
    status_code = 400


# ── Verification tokens ───────────────────────────────────────────


class VerificationTokenError(AuthenticationError):
    """Base for token-related errors."""

    client_message = "Token error."
    status_code = 400


class TokenInvalidError(VerificationTokenError):
    """Token not found or tampered."""

    client_message = "Invalid or expired token."


class TokenExpiredError(VerificationTokenError):
    """Token TTL exceeded."""

    client_message = "Token has expired."


class TokenAlreadyUsedError(VerificationTokenError):
    """Token already consumed."""

    client_message = "Token has already been used."


class OTPAttemptsExceededError(VerificationTokenError):
    """Too many OTP verification attempts for this token."""

    client_message = "Too many verification attempts. Please request a new code."


# ── Rate limiting ──────────────────────────────────────────────────


class RateLimitExceededError(AuthenticationError):
    """Too many attempts."""

    client_message = "Too many attempts. Please try again later."
    status_code = 429

    def __init__(self, retry_after: int | None = None, detail: str | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(detail)


# ── Passwordless ───────────────────────────────────────────────────


class PasswordlessNotEnabledError(AuthenticationError):
    """Passwordless auth not enabled for this user."""

    client_message = "Passwordless authentication is not enabled."
    status_code = 400


# ── Cooldown ───────────────────────────────────────────────────────


class CooldownActiveError(AuthenticationError):
    """Request is within cooldown period."""

    client_message = "Please wait before requesting again."
    status_code = 429

    def __init__(self, retry_after: int | None = None, detail: str | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(detail)
