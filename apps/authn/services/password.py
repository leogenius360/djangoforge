"""
Password service -- password change, reset, history enforcement, and expiry.

Handles the full password lifecycle: change (authenticated), reset
(unauthenticated via token), history enforcement, and optional expiry.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone

from apps.authn.exceptions import (
    CooldownActiveError,
    InvalidCredentialsError,
    PasswordReuseError,
    PasswordValidationError,
)
from apps.authn.models import (
    CredentialStatus,
    PasswordHistory,
    PasswordSetMethod,
    TokenPurpose,
)
from apps.authn.settings import authn_settings

logger = logging.getLogger(__name__)


class PasswordService:
    """Password lifecycle management.

    Responsibilities:
    - Change password (authenticated principal, verifies current password)
    - Request password reset (generates HMAC-hashed token)
    - Confirm password reset (verifies token, sets new password)
    - Password history enforcement (prevents reuse)
    - Password expiry checking
    """

    @staticmethod
    def change_password(
        *,
        principal: object,
        current_password: str,
        new_password: str,
    ) -> None:
        """Change password for an authenticated principal.

        Steps:
        1. Verify current password.
        2. Validate new password against Django validators.
        3. Check password history for reuse.
        4. Update credential, record history, bump security stamp.

        Raises:
            InvalidCredentialsError: Current password is incorrect.
            PasswordValidationError: New password fails policy checks.
            PasswordReuseError: New password matches a recent password.
        """
        # 1. Verify current password
        if not principal.check_password(current_password):
            raise InvalidCredentialsError("Current password is incorrect")

        # 2. Validate new password
        _validate_new_password(new_password, principal)

        # 3. Check history
        _check_password_history(principal, new_password)

        # 4. Set password
        _set_password(principal, new_password, set_by=PasswordSetMethod.USER_CHANGE)

        from apps.authn.audit import authn_audit

        authn_audit(event_type="PASSWORD_CHANGED", principal=principal)

        logger.info("Password changed for principal %s", getattr(principal, "pk", "?"))

    @staticmethod
    def request_password_reset(*, principal: object, delivery_target: str = "") -> dict:
        """Create a password reset token.

        Returns ``{"token": raw_token, "expires_at": datetime}`` for delivery.

        The caller is responsible for sending the token via email/SMS.
        Always succeeds from the HTTP perspective (no information leakage).

        Raises:
            CooldownActiveError: If a reset was requested too recently.
        """
        from apps.authn.services.token import TokenService

        # Check cooldown
        _check_reset_cooldown(principal)

        result = TokenService.create_token(
            principal=principal,
            purpose=TokenPurpose.PASSWORD_RESET,
            ttl_minutes=authn_settings.PASSWORD_RESET_TOKEN_TTL_MINUTES,
            delivery_target=delivery_target or getattr(principal, "email", ""),
        )

        from apps.authn.audit import authn_audit

        authn_audit(event_type="PASSWORD_RESET_REQUESTED", principal=principal, token_id=result.token_id)

        logger.info(
            "Password reset requested for principal %s",
            getattr(principal, "pk", "?"),
        )

        return {
            "token": result.raw_token,
            "expires_at": result.expires_at,
        }

    @staticmethod
    def confirm_password_reset(*, raw_token: str, new_password: str) -> object:
        """Confirm a password reset using the token.

        Steps:
        1. Verify and consume the token.
        2. Validate the new password.
        3. Check password history.
        4. Set the new password, record history, bump security stamp.

        Returns the principal object.

        Raises:
            TokenInvalidError / TokenExpiredError / TokenAlreadyUsedError: Token issues.
            PasswordValidationError: New password fails policy checks.
            PasswordReuseError: New password matches a recent password.
        """
        from apps.authn.services.token import TokenService

        # 1. Verify token
        token = TokenService.verify_token(raw_token)
        principal = token.principal

        # 2. Validate new password
        _validate_new_password(new_password, principal)

        # 3. Check history
        _check_password_history(principal, new_password)

        # 4. Consume token
        TokenService.consume_token(token)

        # 5. Set password
        _set_password(principal, new_password, set_by=PasswordSetMethod.SYSTEM_RESET)

        from apps.authn.audit import authn_audit

        authn_audit(event_type="PASSWORD_CHANGED", principal=principal)

        logger.info(
            "Password reset confirmed for principal %s",
            getattr(principal, "pk", "?"),
        )

        return principal

    @staticmethod
    def check_password_expiry(principal: object) -> dict:
        """Check if the principal's password has expired.

        Returns ``{"expired": bool, "days_remaining": int | None, "last_changed": datetime | None}``.
        """
        max_age = authn_settings.PASSWORD_MAX_AGE_DAYS
        if max_age is None:
            return {
                "expired": False,
                "days_remaining": None,
                "last_changed": None,
            }

        last_entry = PasswordHistory.objects.filter(principal=principal).order_by("-created_at").first()

        if last_entry is None:
            # No history -- treat as expired so principal must set a new password
            return {
                "expired": True,
                "days_remaining": 0,
                "last_changed": None,
            }

        age = timezone.now() - last_entry.created_at
        max_age_delta = timedelta(days=max_age)
        expired = age >= max_age_delta
        days_remaining = max((max_age_delta - age).days, 0) if not expired else 0

        return {
            "expired": expired,
            "days_remaining": days_remaining,
            "last_changed": last_entry.created_at,
        }

    @staticmethod
    def admin_reset_password(*, principal: object, new_password: str) -> None:
        """Admin-initiated password reset (no current password needed).

        Sets ``require_change=True`` so principal must change on next login.
        """
        _validate_new_password(new_password, principal)
        _set_password(
            principal,
            new_password,
            set_by=PasswordSetMethod.ADMIN_RESET,
            require_change=True,
        )
        logger.info("Admin reset password for principal %s", getattr(principal, "pk", "?"))


# ── Private helpers ──────────────────────────────────────────────────


def _validate_new_password(raw_password: str, principal: object) -> None:
    """Run Django password validators and raise on failure."""
    try:
        validate_password(raw_password, user=principal)
    except DjangoValidationError as exc:
        raise PasswordValidationError(
            errors=exc.messages,
            detail="; ".join(exc.messages),
        ) from exc


def _check_password_history(principal: object, raw_password: str) -> None:
    """Check password against recent history."""
    history_count = authn_settings.PASSWORD_HISTORY_COUNT
    if history_count <= 0:
        return

    if PasswordHistory.objects.check_reuse(principal, raw_password, count=history_count):
        raise PasswordReuseError("Password matches a recent password")


def _set_password(
    principal: object,
    raw_password: str,
    *,
    set_by: str = PasswordSetMethod.USER_CHANGE,
    require_change: bool = False,
) -> None:
    """Set password on principal and credential, record history, bump security stamp."""
    from apps.authn.models import PasswordCredential

    # Hash the new password
    password_hash = make_password(raw_password)

    # Update or create credential
    cred = PasswordCredential.objects.filter(
        principal=principal,
        status=CredentialStatus.ACTIVE,
        deleted_at__isnull=True,
    ).first()

    if cred:
        cred.password_hash = password_hash
        cred.require_change = require_change
        cred.save(
            update_fields=[
                "password_hash",
                "require_change",
                "version",
                "updated_at",
            ]
        )
    else:
        PasswordCredential.objects.create(
            principal=principal,
            password_hash=password_hash,
            require_change=require_change,
            status=CredentialStatus.ACTIVE,
        )

    # Also update Django's password hash for compatibility
    principal.set_password(raw_password)
    principal.save(update_fields=["password"])

    # Record in history
    PasswordHistory.objects.record(
        principal=principal,
        password_hash=password_hash,
        set_by=set_by,
    )

    # Prune old history
    PasswordHistory.objects.prune(principal, keep=authn_settings.PASSWORD_HISTORY_COUNT)

    # Bump security stamp to invalidate existing sessions
    principal = getattr(principal, "principal", None)
    if principal and hasattr(principal, "bump_security_stamp"):
        principal.bump_security_stamp()


def _check_reset_cooldown(principal: object) -> None:
    """Check if a password reset was requested too recently."""
    from apps.authn.models import VerificationToken

    cooldown = authn_settings.PASSWORD_RESET_COOLDOWN_SECONDS
    if cooldown <= 0:
        return

    cutoff = timezone.now() - timedelta(seconds=cooldown)
    recent = VerificationToken.objects.filter(
        principal=principal,
        purpose=TokenPurpose.PASSWORD_RESET,
        created_at__gte=cutoff,
    ).exists()

    if recent:
        raise CooldownActiveError(
            retry_after=cooldown,
            detail="Password reset requested too recently",
        )
