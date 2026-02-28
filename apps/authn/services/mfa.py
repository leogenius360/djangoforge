"""
MFA service -- TOTP and backup code management.

Handles TOTP setup/activation, verification during login, backup code
generation/regeneration, and MFA status reporting.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

import pyotp
from django.contrib.auth.hashers import make_password

from apps.authn.exceptions import (
    MFAAlreadyEnabledError,
    MFANotEnabledError,
    MFAVerificationFailedError,
)
from apps.authn.models import BackupCode, CredentialStatus, TOTPCredential
from apps.authn.settings import authn_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MFAVerificationResult:
    """Result of MFA code verification."""

    valid: bool
    method: str | None  # "totp" | "backup_code" | None


class MFAService:
    """MFA credential management and verification."""

    @staticmethod
    def setup_totp(principal: object) -> dict:
        """Begin TOTP setup by creating an INACTIVE credential.

        Returns a dict with ``secret``, ``provisioning_uri``, and ``credential_id``.

        Raises:
            MFAAlreadyEnabledError: If principal already has active TOTP.
        """
        if _has_active_totp(principal):
            raise MFAAlreadyEnabledError("User already has active MFA enabled")

        # Delete any stale pending (INACTIVE) TOTP credentials
        TOTPCredential.objects.filter(
            principal=principal,
            status=CredentialStatus.INACTIVE,
            deleted_at__isnull=True,
        ).delete()

        secret = pyotp.random_base32()
        totp_cred = TOTPCredential.objects.create(
            principal=principal,
            label=authn_settings.MFA_ISSUER_NAME,
            secret=secret,
            algorithm="SHA1",
            digits=6,
            period=30,
            status=CredentialStatus.INACTIVE,
        )

        provisioning_uri = pyotp.TOTP(secret).provisioning_uri(
            name=getattr(principal, "email", str(principal)),
            issuer_name=authn_settings.MFA_ISSUER_NAME,
        )

        logger.info("TOTP setup initiated for principal %s", getattr(principal, "pk", "?"))

        return {
            "secret": secret,
            "provisioning_uri": provisioning_uri,
            "credential_id": str(totp_cred.pk),
        }

    @staticmethod
    def activate_totp(principal: object, code: str) -> dict:
        """Activate a pending TOTP credential after verifying the first code.

        Returns ``{"backup_codes": [...]}``.

        Raises:
            MFAVerificationFailedError: If code is invalid or no pending setup.
        """
        pending = TOTPCredential.objects.filter(
            principal=principal,
            status=CredentialStatus.INACTIVE,
            deleted_at__isnull=True,
        ).first()

        if pending is None:
            raise MFAVerificationFailedError("No pending MFA setup found")

        totp = pyotp.TOTP(pending.secret)
        if not totp.verify(code, valid_window=authn_settings.TOTP_VALID_WINDOW):
            raise MFAVerificationFailedError("Invalid TOTP code")

        pending.status = CredentialStatus.ACTIVE
        pending.save(update_fields=["status", "version", "updated_at"])

        backup_codes = MFAService._generate_backup_codes(principal, count=authn_settings.MFA_BACKUP_CODE_COUNT)

        logger.info("TOTP activated for principal %s", getattr(principal, "pk", "?"))

        return {"backup_codes": backup_codes}

    @staticmethod
    def verify_mfa(principal: object, code: str) -> MFAVerificationResult:
        """Verify MFA code for a user (TOTP first, then backup codes).

        Returns ``MFAVerificationResult`` indicating success and method used.
        """
        # Try TOTP first for numeric codes of appropriate length
        if code.isdigit() and len(code) in (6, 8) and _verify_totp(principal, code):
            return MFAVerificationResult(valid=True, method="totp")

        # Try backup code
        if _verify_backup_code(principal, code):
            return MFAVerificationResult(valid=True, method="backup_code")

        return MFAVerificationResult(valid=False, method=None)

    @staticmethod
    def disable_mfa(principal: object, code: str) -> int:
        """Disable MFA by verifying code and revoking all credentials.

        Returns the number of credentials revoked.

        Raises:
            MFANotEnabledError: If MFA is not enabled.
            MFAVerificationFailedError: If code is invalid.
        """
        if not _has_active_totp(principal):
            raise MFANotEnabledError()

        result = MFAService.verify_mfa(principal, code)
        if not result.valid:
            raise MFAVerificationFailedError("Invalid code for MFA disable")

        count = 0

        # Revoke all TOTP credentials
        for totp in TOTPCredential.objects.filter(principal=principal, deleted_at__isnull=True):
            totp.revoke()
            count += 1

        # Revoke all unused backup codes
        for backup in BackupCode.objects.filter(principal=principal, is_used=False, deleted_at__isnull=True):
            backup.revoke()
            count += 1

        logger.info(
            "MFA disabled for principal %s (%d credentials revoked)",
            getattr(principal, "pk", "?"),
            count,
        )
        return count

    @staticmethod
    def regenerate_backup_codes(principal: object) -> list[str]:
        """Revoke existing backup codes and generate new ones.

        Returns plaintext codes (only time they are visible).

        Raises:
            MFANotEnabledError: If MFA is not enabled.
        """
        if not _has_active_totp(principal):
            raise MFANotEnabledError()

        # Revoke existing unused backup codes
        BackupCode.objects.filter(principal=principal, is_used=False, deleted_at__isnull=True).update(
            status=CredentialStatus.REVOKED
        )

        codes = MFAService._generate_backup_codes(principal, count=authn_settings.MFA_BACKUP_CODE_COUNT)
        logger.info(
            "Backup codes regenerated for principal %s",
            getattr(principal, "pk", "?"),
        )
        return codes

    @staticmethod
    def get_status(principal: object) -> dict:
        """Return MFA status for the user."""
        totp_creds = TOTPCredential.objects.filter(
            principal=principal,
            status=CredentialStatus.ACTIVE,
            deleted_at__isnull=True,
        )
        totp_count = totp_creds.count()

        backup_remaining = BackupCode.objects.filter(
            principal=principal,
            is_used=False,
            status=CredentialStatus.ACTIVE,
            deleted_at__isnull=True,
        ).count()

        last_used = None
        latest = totp_creds.order_by("-last_used_at").first()
        if latest and latest.last_used_at:
            last_used = latest.last_used_at

        return {
            "enabled": totp_count > 0,
            "totp_count": totp_count,
            "backup_codes_remaining": backup_remaining,
            "last_used": last_used,
        }

    @staticmethod
    def _generate_backup_codes(principal: object, count: int = 10) -> list[str]:
        """Generate backup codes and return plaintext versions."""
        plain_codes = []
        for _ in range(count):
            raw_code = secrets.token_hex(4).upper()
            BackupCode.objects.create(
                principal=principal,
                code_hash=make_password(raw_code),
                status=CredentialStatus.ACTIVE,
            )
            plain_codes.append(f"{raw_code[:4]}-{raw_code[4:]}")
        return plain_codes


# ── Private helpers ──────────────────────────────────────────────────


def _has_active_totp(principal: object) -> bool:
    """Return True if user has at least one active TOTP credential."""
    return TOTPCredential.objects.filter(
        principal=principal,
        status=CredentialStatus.ACTIVE,
        deleted_at__isnull=True,
    ).exists()


def _verify_totp(principal: object, code: str) -> bool:
    """Verify TOTP code against active credentials."""
    for cred in TOTPCredential.objects.filter(
        principal=principal,
        status=CredentialStatus.ACTIVE,
        deleted_at__isnull=True,
    ):
        totp = pyotp.TOTP(cred.secret)
        if totp.verify(code, valid_window=authn_settings.TOTP_VALID_WINDOW):
            cred.mark_used()
            return True
    return False


def _verify_backup_code(principal: object, code: str) -> bool:
    """Verify and consume a backup code."""
    normalized = code.upper().replace("-", "").replace(" ", "")
    for backup in BackupCode.objects.filter(
        principal=principal,
        is_used=False,
        status=CredentialStatus.ACTIVE,
        deleted_at__isnull=True,
    ):
        if backup.verify_and_consume(normalized):
            return True
    return False


# Backward-compatible alias for external consumers
def get_mfa_status(principal: object) -> dict:
    """Alias for ``MFAService.get_status()``."""
    return MFAService.get_status(principal)
