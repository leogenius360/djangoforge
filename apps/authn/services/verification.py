"""
Verification service -- email and phone verification flows.

Handles request/confirm cycles for email and phone verification using
HMAC-hashed tokens with cooldown enforcement.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from apps.authn.exceptions import CooldownActiveError
from apps.authn.models import TokenPurpose, VerificationToken
from apps.authn.settings import authn_settings

logger = logging.getLogger(__name__)


class VerificationService:
    """Email and phone verification lifecycle management.

    All tokens are created via ``TokenService`` (HMAC-hashed storage).
    Cooldown enforcement prevents rapid-fire requests.
    """

    # ── Email verification ───────────────────────────────────────────

    @staticmethod
    def request_email_verification(*, principal: object) -> dict:
        """Request an email verification token.

        Returns ``{"token": raw_token, "expires_at": datetime}`` for delivery.

        Raises:
            CooldownActiveError: If a request was made too recently.
        """
        from apps.authn.services.token import TokenService

        _check_cooldown(
            principal=principal,
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            cooldown_seconds=authn_settings.EMAIL_VERIFICATION_COOLDOWN_SECONDS,
        )

        email = getattr(principal, "email", "")
        result = TokenService.create_token(
            principal=principal,
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            ttl_minutes=authn_settings.EMAIL_VERIFICATION_TOKEN_TTL_MINUTES,
            delivery_target=email,
        )

        from apps.authn.audit import authn_audit

        authn_audit(
            event_type="VERIFICATION_TOKEN_CREATED",
            principal=principal,
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            token_id=result.token_id,
        )

        logger.info(
            "Email verification requested for principal %s (%s)",
            getattr(principal, "pk", "?"),
            email,
        )

        return {
            "token": result.raw_token,
            "expires_at": result.expires_at,
        }

    @staticmethod
    def confirm_email_verification(*, raw_token: str) -> object:
        """Confirm email verification using a token.

        Steps:
        1. Verify the token.
        2. Mark principal's email as verified.
        3. Consume the token.

        Returns the principal object.

        Raises:
            TokenInvalidError / TokenExpiredError / TokenAlreadyUsedError: Token issues.
        """
        from apps.authn.services.token import TokenService

        token = TokenService.verify_token(raw_token)

        if token.purpose != TokenPurpose.EMAIL_VERIFICATION:
            from apps.authn.exceptions import TokenInvalidError

            raise TokenInvalidError("Token is not for email verification")

        principal = token.principal

        # Mark email as verified
        if hasattr(principal, "email_verified_at"):
            principal.email_verified_at = timezone.now()
            principal.save(update_fields=["email_verified_at"])

        # Consume token
        TokenService.consume_token(token)

        from apps.authn.audit import authn_audit

        authn_audit(event_type="EMAIL_VERIFIED", principal=principal)

        logger.info("Email verified for principal %s", getattr(principal, "pk", "?"))

        return principal

    # ── Phone verification ───────────────────────────────────────────

    @staticmethod
    def request_phone_verification(*, principal: object) -> dict:
        """Request a phone verification OTP.

        Returns ``{"token": raw_token, "otp": raw_otp, "expires_at": datetime}``
        for delivery.  The ``token`` is needed to verify OTP; the ``otp`` is
        sent to the principal's phone.

        Raises:
            CooldownActiveError: If a request was made too recently.
        """
        from apps.authn.services.token import TokenService

        _check_cooldown(
            principal=principal,
            purpose=TokenPurpose.PHONE_VERIFICATION,
            cooldown_seconds=authn_settings.PHONE_VERIFICATION_COOLDOWN_SECONDS,
        )

        phone = getattr(principal, "phone_number", "") or ""
        result = TokenService.create_token(
            principal=principal,
            purpose=TokenPurpose.PHONE_VERIFICATION,
            generate_otp_code=True,
            otp_length=authn_settings.PHONE_VERIFICATION_OTP_LENGTH,
            ttl_minutes=authn_settings.PHONE_VERIFICATION_OTP_TTL_MINUTES,
            max_attempts=authn_settings.PHONE_VERIFICATION_MAX_ATTEMPTS,
            delivery_target=phone,
        )

        from apps.authn.audit import authn_audit

        authn_audit(
            event_type="VERIFICATION_TOKEN_CREATED",
            principal=principal,
            purpose=TokenPurpose.PHONE_VERIFICATION,
            token_id=result.token_id,
        )

        logger.info(
            "Phone verification requested for principal %s (%s)",
            getattr(principal, "pk", "?"),
            phone,
        )

        return {
            "token": result.raw_token,
            "otp": result.raw_otp,
            "expires_at": result.expires_at,
        }

    @staticmethod
    def confirm_phone_verification(*, principal: object, otp: str) -> object:
        """Confirm phone verification using an OTP.

        Steps:
        1. Verify the OTP via ``TokenService``.
        2. Mark principal's phone as verified.
        3. Consume the token.

        Returns the principal object.

        Raises:
            TokenInvalidError / TokenExpiredError: Token issues.
            OTPAttemptsExceededError: Too many failed OTP attempts.
        """
        from apps.authn.services.token import TokenService

        token = TokenService.verify_otp(
            principal=principal,
            purpose=TokenPurpose.PHONE_VERIFICATION,
            otp=otp,
        )

        # Mark phone as verified
        if hasattr(principal, "phone_verified_at"):
            principal.phone_verified_at = timezone.now()
            principal.save(update_fields=["phone_verified_at"])

        # Consume token
        TokenService.consume_token(token)

        from apps.authn.audit import authn_audit

        authn_audit(event_type="PHONE_VERIFIED", principal=principal)

        logger.info("Phone verified for principal %s", getattr(principal, "pk", "?"))

        return principal


# ── Private helpers ──────────────────────────────────────────────────


def _check_cooldown(*, principal: object, purpose: str, cooldown_seconds: int) -> None:
    """Raise ``CooldownActiveError`` if a token was created too recently."""
    if cooldown_seconds <= 0:
        return

    cutoff = timezone.now() - timedelta(seconds=cooldown_seconds)
    recent = VerificationToken.objects.filter(
        principal=principal,
        purpose=purpose,
        created_at__gte=cutoff,
    ).exists()

    if recent:
        raise CooldownActiveError(
            retry_after=cooldown_seconds,
            detail=f"{purpose} verification requested too recently",
        )
