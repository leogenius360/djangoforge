"""
Authentication models package.

Exports all models and enums for the authn subsystem.
"""

from .challenges import VerificationToken
from .credentials import (
    BackupCode,
    BaseCredential,
    PasswordCredential,
    TOTPCredential,
    WebAuthnCredential,
)
from .enums import (
    AuthenticationMethod,
    AuthenticationStatus,
    CredentialStatus,
    DeviceType,
    LoginAttemptResult,
    MFAMethod,
    PasswordSetMethod,
    TokenPurpose,
)
from .login_attempts import LoginAttempt
from .mfa_pending import MFAPendingAuthentication
from .password_history import PasswordHistory

__all__ = [
    # Enums
    "AuthenticationMethod",
    "AuthenticationStatus",
    "CredentialStatus",
    "DeviceType",
    "LoginAttemptResult",
    "MFAMethod",
    "PasswordSetMethod",
    "TokenPurpose",
    # Credential models
    "BaseCredential",
    "PasswordCredential",
    "WebAuthnCredential",
    "TOTPCredential",
    "BackupCode",
    # Verification / challenges
    "VerificationToken",
    # Login tracking
    "LoginAttempt",
    # MFA pending
    "MFAPendingAuthentication",
    # Password history
    "PasswordHistory",
]
