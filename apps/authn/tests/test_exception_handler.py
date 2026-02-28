"""Tests for authn DRF exception handler."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from rest_framework.test import APIRequestFactory

from apps.authn.exception_handler import authn_exception_handler
from apps.authn.exceptions import (
    AccountDisabledError,
    AccountLockedError,
    AuthenticationError,
    CooldownActiveError,
    CredentialExpiredError,
    InvalidCredentialsError,
    MFAAlreadyEnabledError,
    MFANotEnabledError,
    MFAPendingExpiredError,
    MFARequiredError,
    MFAVerificationFailedError,
    OTPAttemptsExceededError,
    PasswordlessNotEnabledError,
    PasswordReuseError,
    PasswordValidationError,
    RateLimitExceededError,
    TokenAlreadyUsedError,
    TokenExpiredError,
    TokenInvalidError,
    VerificationTokenError,
)


@pytest.fixture
def context():
    """Minimal DRF exception handler context."""
    factory = APIRequestFactory()
    request = factory.get("/fake/")
    return {"request": request, "view": None}


class TestAuthnExceptionHandler:
    """Tests for authn_exception_handler."""

    def test_base_authentication_error(self, context):
        exc = AuthenticationError("internal detail")
        response = authn_exception_handler(exc, context)
        assert response is not None
        assert response.status_code == 401
        assert response.data["detail"] == "An authentication error occurred."
        assert response.data["error_code"] == "AuthenticationError"

    def test_invalid_credentials_error(self, context):
        exc = InvalidCredentialsError("bad password")
        response = authn_exception_handler(exc, context)
        assert response.status_code == 401
        assert response.data["detail"] == "Invalid credentials."
        assert response.data["error_code"] == "InvalidCredentialsError"

    def test_credential_expired_error(self, context):
        exc = CredentialExpiredError()
        response = authn_exception_handler(exc, context)
        assert response.status_code == 401
        assert response.data["detail"] == "Credentials have expired."

    def test_password_reuse_error(self, context):
        exc = PasswordReuseError()
        response = authn_exception_handler(exc, context)
        assert response.status_code == 400
        assert response.data["detail"] == "Cannot reuse a recent password."

    def test_password_validation_error(self, context):
        errors = ["Too short", "Needs uppercase"]
        exc = PasswordValidationError(errors=errors)
        response = authn_exception_handler(exc, context)
        assert response.status_code == 400
        assert response.data["detail"] == "Password does not meet requirements."
        assert response.data["validation_errors"] == errors

    def test_password_validation_error_no_errors(self, context):
        exc = PasswordValidationError()
        response = authn_exception_handler(exc, context)
        assert response.status_code == 400
        # Empty errors list is falsy, so validation_errors won't be added
        assert "validation_errors" not in response.data

    def test_account_locked_error_with_time(self, context):
        locked = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        exc = AccountLockedError(locked_until=locked, detail="Too many attempts")
        response = authn_exception_handler(exc, context)
        assert response.status_code == 403
        assert response.data["detail"] == "Account is temporarily locked."
        assert response.data["locked_until"] == locked.isoformat()

    def test_account_locked_error_no_time(self, context):
        exc = AccountLockedError()
        response = authn_exception_handler(exc, context)
        assert response.status_code == 403
        assert "locked_until" not in response.data

    def test_account_disabled_error(self, context):
        exc = AccountDisabledError()
        response = authn_exception_handler(exc, context)
        assert response.status_code == 403
        assert response.data["detail"] == "Account is not available."

    def test_mfa_required_error(self, context):
        exc = MFARequiredError(mfa_token="abc-123-token")
        response = authn_exception_handler(exc, context)
        assert response.status_code == 200
        assert response.data["mfa_required"] is True
        assert response.data["mfa_token"] == "abc-123-token"
        assert response.data["detail"] == "MFA verification required."

    def test_mfa_verification_failed_error(self, context):
        exc = MFAVerificationFailedError()
        response = authn_exception_handler(exc, context)
        assert response.status_code == 401
        assert response.data["detail"] == "Invalid verification code."

    def test_mfa_pending_expired_error(self, context):
        exc = MFAPendingExpiredError()
        response = authn_exception_handler(exc, context)
        assert response.status_code == 401
        assert response.data["detail"] == "Session expired. Please log in again."

    def test_mfa_already_enabled_error(self, context):
        exc = MFAAlreadyEnabledError()
        response = authn_exception_handler(exc, context)
        assert response.status_code == 400
        assert response.data["detail"] == "MFA is already enabled."

    def test_mfa_not_enabled_error(self, context):
        exc = MFANotEnabledError()
        response = authn_exception_handler(exc, context)
        assert response.status_code == 400
        assert response.data["detail"] == "MFA is not enabled."

    def test_verification_token_error(self, context):
        exc = VerificationTokenError()
        response = authn_exception_handler(exc, context)
        assert response.status_code == 400
        assert response.data["detail"] == "Token error."

    def test_token_invalid_error(self, context):
        exc = TokenInvalidError()
        response = authn_exception_handler(exc, context)
        assert response.status_code == 400
        assert response.data["detail"] == "Invalid or expired token."

    def test_token_expired_error(self, context):
        exc = TokenExpiredError()
        response = authn_exception_handler(exc, context)
        assert response.status_code == 400
        assert response.data["detail"] == "Token has expired."

    def test_token_already_used_error(self, context):
        exc = TokenAlreadyUsedError()
        response = authn_exception_handler(exc, context)
        assert response.status_code == 400
        assert response.data["detail"] == "Token has already been used."

    def test_otp_attempts_exceeded_error(self, context):
        exc = OTPAttemptsExceededError()
        response = authn_exception_handler(exc, context)
        assert response.status_code == 400
        assert "Too many" in response.data["detail"]

    def test_rate_limit_exceeded_error(self, context):
        exc = RateLimitExceededError(retry_after=120)
        response = authn_exception_handler(exc, context)
        assert response.status_code == 429
        assert response.data["retry_after"] == 120

    def test_rate_limit_exceeded_error_no_retry(self, context):
        exc = RateLimitExceededError()
        response = authn_exception_handler(exc, context)
        assert response.status_code == 429
        assert "retry_after" not in response.data

    def test_passwordless_not_enabled_error(self, context):
        exc = PasswordlessNotEnabledError()
        response = authn_exception_handler(exc, context)
        assert response.status_code == 400

    def test_cooldown_active_error(self, context):
        exc = CooldownActiveError(retry_after=60)
        response = authn_exception_handler(exc, context)
        assert response.status_code == 429
        assert response.data["retry_after"] == 60

    def test_cooldown_active_error_no_retry(self, context):
        exc = CooldownActiveError()
        response = authn_exception_handler(exc, context)
        assert response.status_code == 429
        assert "retry_after" not in response.data

    def test_non_authn_exception_passes_through(self, context):
        exc = ValueError("Something else")
        response = authn_exception_handler(exc, context)
        # DRF default handler returns None for non-DRF exceptions
        assert response is None

    def test_error_code_matches_class_name(self, context):
        """Each exception's error_code should match its class name."""
        exceptions = [
            InvalidCredentialsError(),
            CredentialExpiredError(),
            PasswordReuseError(),
            AccountLockedError(),
            AccountDisabledError(),
            MFAVerificationFailedError(),
            MFAPendingExpiredError(),
            MFAAlreadyEnabledError(),
            MFANotEnabledError(),
            TokenInvalidError(),
            TokenExpiredError(),
            TokenAlreadyUsedError(),
            OTPAttemptsExceededError(),
            PasswordlessNotEnabledError(),
        ]
        for exc in exceptions:
            response = authn_exception_handler(exc, context)
            assert response.data["error_code"] == type(exc).__name__

    def test_internal_detail_not_leaked(self, context):
        """Internal detail (str(exc)) should not appear in response data."""
        exc = InvalidCredentialsError("user xyz password mismatch in DB")
        response = authn_exception_handler(exc, context)
        # The client_message should be the generic one
        assert response.data["detail"] == "Invalid credentials."
        # Internal detail should NOT appear in response
        assert "xyz" not in response.data["detail"]
        assert "mismatch" not in response.data["detail"]


class TestExceptionHierarchy:
    """Test the exception class hierarchy."""

    def test_all_inherit_from_authentication_error(self):
        assert issubclass(InvalidCredentialsError, AuthenticationError)
        assert issubclass(CredentialExpiredError, AuthenticationError)
        assert issubclass(PasswordReuseError, AuthenticationError)
        assert issubclass(PasswordValidationError, AuthenticationError)
        assert issubclass(AccountLockedError, AuthenticationError)
        assert issubclass(AccountDisabledError, AuthenticationError)
        assert issubclass(MFARequiredError, AuthenticationError)
        assert issubclass(MFAVerificationFailedError, AuthenticationError)
        assert issubclass(MFAPendingExpiredError, AuthenticationError)
        assert issubclass(MFAAlreadyEnabledError, AuthenticationError)
        assert issubclass(MFANotEnabledError, AuthenticationError)
        assert issubclass(VerificationTokenError, AuthenticationError)
        assert issubclass(TokenInvalidError, VerificationTokenError)
        assert issubclass(TokenExpiredError, VerificationTokenError)
        assert issubclass(TokenAlreadyUsedError, VerificationTokenError)
        assert issubclass(OTPAttemptsExceededError, VerificationTokenError)
        assert issubclass(RateLimitExceededError, AuthenticationError)
        assert issubclass(PasswordlessNotEnabledError, AuthenticationError)
        assert issubclass(CooldownActiveError, AuthenticationError)

    def test_default_client_messages_are_safe(self):
        """client_message should not contain technical details."""
        safe_exceptions = [
            InvalidCredentialsError,
            CredentialExpiredError,
            PasswordReuseError,
            AccountLockedError,
            AccountDisabledError,
            MFAVerificationFailedError,
            MFAPendingExpiredError,
            MFAAlreadyEnabledError,
            MFANotEnabledError,
            TokenInvalidError,
            TokenExpiredError,
            TokenAlreadyUsedError,
            OTPAttemptsExceededError,
            RateLimitExceededError,
            PasswordlessNotEnabledError,
            CooldownActiveError,
        ]
        for exc_cls in safe_exceptions:
            msg = exc_cls.client_message
            # Should not contain technical terms
            assert "traceback" not in msg.lower()
            assert "stack" not in msg.lower()
            assert "exception" not in msg.lower()
            assert "error" not in msg.lower() or "error" in msg.lower()
