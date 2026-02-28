"""
Authn settings loader.

Reads from Django settings::

    AUTHN = {
        "MAX_FAILED_ATTEMPTS": 5,
        "LOCKOUT_DURATION_MINUTES": 30,
        "PROGRESSIVE_LOCKOUT": True,
        "PROGRESSIVE_LOCKOUT_MAX_MINUTES": 1440,
        "PASSWORD_HISTORY_COUNT": 5,
        "PASSWORD_MAX_AGE_DAYS": 90,
        "MFA_ISSUER_NAME": "BBRI",
        "MFA_BACKUP_CODE_COUNT": 10,
        "MFA_PENDING_TTL_MINUTES": 5,
        "MFA_PENDING_MAX_ATTEMPTS": 5,
        "TOTP_VALID_WINDOW": 1,
        "VERIFICATION_TOKEN_TTL_MINUTES": 30,
        "PASSWORDLESS_TOKEN_TTL_MINUTES": 10,
        "PASSWORDLESS_OTP_LENGTH": 6,
        "PASSWORDLESS_OTP_MAX_ATTEMPTS": 5,
        "PASSWORDLESS_RESEND_COOLDOWN_SECONDS": 60,
        "PASSWORD_RESET_TOKEN_TTL_MINUTES": 60,
        "PASSWORD_RESET_COOLDOWN_SECONDS": 60,
        "EMAIL_VERIFICATION_TOKEN_TTL_MINUTES": 1440,
        "EMAIL_VERIFICATION_COOLDOWN_SECONDS": 60,
        "PHONE_VERIFICATION_OTP_TTL_MINUTES": 10,
        "PHONE_VERIFICATION_OTP_LENGTH": 6,
        "PHONE_VERIFICATION_COOLDOWN_SECONDS": 60,
        "PHONE_VERIFICATION_MAX_ATTEMPTS": 5,
        "TOKEN_HMAC_KEY": "",
        "CONSTANT_TIME_BACKEND_RESPONSES": True,
        "ACCESS_TOKEN_LIFETIME_SECONDS": 3600,
        "JWT_ALGORITHM": "HS256",
    }

Unknown keys raise ``ImproperlyConfigured`` at startup (strict namespace).
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

from django.test.signals import setting_changed

from apps.auditing.settings import BaseSettings


class AuthnSettings(BaseSettings):
    """Typed, validated settings for the authentication subsystem."""

    settings_key: ClassVar[str] = "AUTHN"
    strict_namespace: ClassVar[bool] = True

    # ── Lockout policy ──────────────────────────────────────────────
    MAX_FAILED_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 30
    PROGRESSIVE_LOCKOUT: bool = True
    PROGRESSIVE_LOCKOUT_MAX_MINUTES: int = 1440  # 24 hours cap

    # ── Password policy ─────────────────────────────────────────────
    PASSWORD_HISTORY_COUNT: int = 5
    PASSWORD_MAX_AGE_DAYS: int | None = 90  # None = no expiry

    # ── MFA ──────────────────────────────────────────────────────────
    MFA_ISSUER_NAME: str = "BBRI"
    MFA_BACKUP_CODE_COUNT: int = 10
    TOTP_VALID_WINDOW: int = 1  # +/- N periods

    # ── MFA pending ─────────────────────────────────────────────────
    MFA_PENDING_TTL_MINUTES: int = 5
    MFA_PENDING_MAX_ATTEMPTS: int = 5

    # ── Verification tokens ─────────────────────────────────────────
    VERIFICATION_TOKEN_TTL_MINUTES: int = 30
    PASSWORDLESS_TOKEN_TTL_MINUTES: int = 10
    PASSWORDLESS_OTP_LENGTH: int = 6
    PASSWORDLESS_OTP_MAX_ATTEMPTS: int = 5
    PASSWORDLESS_RESEND_COOLDOWN_SECONDS: int = 60

    # ── Password reset ──────────────────────────────────────────────
    PASSWORD_RESET_TOKEN_TTL_MINUTES: int = 60
    PASSWORD_RESET_COOLDOWN_SECONDS: int = 60

    # ── Email verification ──────────────────────────────────────────
    EMAIL_VERIFICATION_TOKEN_TTL_MINUTES: int = 1440  # 24 hours
    EMAIL_VERIFICATION_COOLDOWN_SECONDS: int = 60

    # ── Phone verification ──────────────────────────────────────────
    PHONE_VERIFICATION_OTP_TTL_MINUTES: int = 10
    PHONE_VERIFICATION_OTP_LENGTH: int = 6
    PHONE_VERIFICATION_COOLDOWN_SECONDS: int = 60
    PHONE_VERIFICATION_MAX_ATTEMPTS: int = 5

    # ── Security ────────────────────────────────────────────────────
    TOKEN_HMAC_KEY: str = ""  # Falls back to Django SECRET_KEY
    CONSTANT_TIME_BACKEND_RESPONSES: bool = True

    # ── JWT access tokens ────────────────────────────────────────────
    # Lifetime in seconds for short-lived JWT access tokens (default 60 min).
    ACCESS_TOKEN_LIFETIME_SECONDS: int = 3600
    # Algorithm used to sign/verify JWT access tokens.
    JWT_ALGORITHM: str = "HS256"


authn_settings: Final[AuthnSettings] = AuthnSettings()


def _on_setting_changed(sender: object, setting: str, **_: Any) -> None:
    if authn_settings.is_related_setting(setting):
        authn_settings.reload()


setting_changed.connect(_on_setting_changed)
