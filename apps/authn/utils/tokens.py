"""
Token utilities for HMAC-based token hashing and generation.

Tokens and OTP codes are never stored in plaintext.  This module provides
the HMAC primitives used by ``VerificationToken`` and ``MFA pending`` flows.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string

from django.conf import settings


def _get_hmac_key() -> bytes:
    """Return the HMAC signing key (authn setting or Django SECRET_KEY)."""
    from apps.authn.settings import authn_settings

    key = authn_settings.TOKEN_HMAC_KEY or settings.SECRET_KEY
    return key.encode("utf-8") if isinstance(key, str) else key


def hmac_hash(value: str) -> str:
    """Return a hex-encoded HMAC-SHA256 digest of *value*."""
    return hmac.new(_get_hmac_key(), value.encode("utf-8"), hashlib.sha256).hexdigest()


def hmac_verify(value: str, expected_hash: str) -> bool:
    """Constant-time comparison of *value* against *expected_hash*."""
    return hmac.compare_digest(hmac_hash(value), expected_hash)


def generate_token(nbytes: int = 32) -> str:
    """Generate a URL-safe random token."""
    return secrets.token_urlsafe(nbytes)


def generate_otp(length: int = 6) -> str:
    """Generate a numeric OTP code of the given *length*."""
    digits = string.digits
    return "".join(secrets.choice(digits) for _ in range(length))
