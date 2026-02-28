"""
Token service -- centralized VerificationToken lifecycle management.

All tokens are stored as HMAC-SHA256 hashes.  Raw values are returned
only at creation time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from apps.authn.exceptions import (
    OTPAttemptsExceededError,
    TokenAlreadyUsedError,
    TokenExpiredError,
    TokenInvalidError,
)
from apps.authn.models import TokenPurpose, VerificationToken
from apps.authn.settings import authn_settings
from apps.authn.utils.tokens import generate_otp, generate_token, hmac_hash, hmac_verify

if TYPE_CHECKING:
    from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TokenCreationResult:
    """Result of creating a verification token."""

    token_id: UUID
    raw_token: str
    raw_otp: str | None
    expires_at: datetime


class TokenService:
    """Centralized VerificationToken lifecycle management.

    All tokens are stored as HMAC-SHA256 hashes.  Raw values are returned
    only at creation time.
    """

    @staticmethod
    def create_token(
        *,
        principal: object,
        purpose: str,
        generate_otp_code: bool = False,
        otp_length: int | None = None,
        ttl_minutes: int | None = None,
        delivery_target: str = "",
        max_attempts: int = 5,
    ) -> TokenCreationResult:
        """Create a verification token with HMAC-hashed storage.

        Steps:
        1. Invalidate existing unused tokens of same purpose for principal.
        2. Generate raw token via ``secrets.token_urlsafe``.
        3. Optionally generate OTP.
        4. Store HMAC hashes in ``VerificationToken``.
        5. Return raw values (only time they are available).
        """
        # Determine TTL from purpose-specific settings or fallback
        if ttl_minutes is None:
            ttl_minutes = _get_default_ttl(purpose)

        raw_token = generate_token()

        raw_otp: str | None = None
        otp_hash = ""
        if generate_otp_code:
            length = otp_length or _get_default_otp_length(purpose)
            raw_otp = generate_otp(length)
            otp_hash = hmac_hash(raw_otp)

        token = VerificationToken.create_for_principal(
            principal=principal,
            purpose=purpose,
            token_hash=hmac_hash(raw_token),
            otp_hash=otp_hash,
            ttl=timedelta(minutes=ttl_minutes),
            max_attempts=max_attempts,
            delivery_target=delivery_target,
        )

        logger.info(
            "Created %s token for principal %s (id=%s, expires=%s)",
            purpose,
            getattr(principal, "pk", "?"),
            token.pk,
            token.expires_at,
        )

        return TokenCreationResult(
            token_id=token.pk,
            raw_token=raw_token,
            raw_otp=raw_otp,
            expires_at=token.expires_at,
        )

    @staticmethod
    def verify_token(raw_token: str) -> VerificationToken:
        """Verify a token by computing its HMAC and looking it up.

        Raises:
            TokenInvalidError: Token not found.
            TokenExpiredError: Token TTL exceeded.
            TokenAlreadyUsedError: Token already consumed.
        """
        token_hash = hmac_hash(raw_token)
        token = VerificationToken.objects.select_related("principal").filter(token_hash=token_hash).first()
        if token is None:
            raise TokenInvalidError("Token not found")

        if token.is_used:
            raise TokenAlreadyUsedError("Token already consumed")

        if token.is_expired:
            raise TokenExpiredError("Token has expired")

        return token

    @staticmethod
    def verify_otp(
        *,
        principal: object,
        purpose: str,
        otp: str,
    ) -> VerificationToken:
        """Verify an OTP for a given principal and purpose.

        Increments ``attempt_count`` on each call.

        Raises:
            TokenInvalidError: No valid token found.
            TokenExpiredError: Token has expired.
            OTPAttemptsExceededError: Too many failed attempts.
            TokenInvalidError: OTP does not match.
        """
        token = (
            VerificationToken.objects.filter(
                principal=principal,
                purpose=purpose,
                used_at__isnull=True,
                otp_hash__gt="",  # must have an OTP hash
            )
            .order_by("-created_at")
            .first()
        )

        if token is None:
            raise TokenInvalidError("No valid OTP token found")

        if token.is_expired:
            raise TokenExpiredError("OTP token has expired")

        if token.attempts_exceeded:
            raise OTPAttemptsExceededError("Too many OTP verification attempts")

        # Increment attempts before verification (fail-safe)
        token.increment_attempts()

        if not hmac_verify(otp, token.otp_hash):
            if token.attempts_exceeded:
                raise OTPAttemptsExceededError("Too many OTP verification attempts")
            raise TokenInvalidError("Invalid OTP code")

        return token

    @staticmethod
    def consume_token(token: VerificationToken) -> None:
        """Mark a token as used."""
        token.mark_used()
        logger.info(
            "Token consumed: purpose=%s, principal=%s, id=%s",
            token.purpose,
            token.principal_id,
            token.pk,
        )


def _get_default_ttl(purpose: str) -> int:
    """Return default TTL in minutes for the given purpose."""
    ttl_map = {
        TokenPurpose.EMAIL_VERIFICATION: authn_settings.EMAIL_VERIFICATION_TOKEN_TTL_MINUTES,
        TokenPurpose.PHONE_VERIFICATION: authn_settings.PHONE_VERIFICATION_OTP_TTL_MINUTES,
        TokenPurpose.PASSWORD_RESET: authn_settings.PASSWORD_RESET_TOKEN_TTL_MINUTES,
        TokenPurpose.PASSWORDLESS_LOGIN: authn_settings.PASSWORDLESS_TOKEN_TTL_MINUTES,
    }
    return ttl_map.get(purpose, authn_settings.VERIFICATION_TOKEN_TTL_MINUTES)


def _get_default_otp_length(purpose: str) -> int:
    """Return default OTP length for the given purpose."""
    length_map = {
        TokenPurpose.PHONE_VERIFICATION: authn_settings.PHONE_VERIFICATION_OTP_LENGTH,
        TokenPurpose.PASSWORDLESS_LOGIN: authn_settings.PASSWORDLESS_OTP_LENGTH,
    }
    return length_map.get(purpose, 6)
