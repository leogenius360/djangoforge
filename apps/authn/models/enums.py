"""
Authentication enums and constants.

Defines credential lifecycle states, authentication methods, MFA methods,
device types, login attempt results, and password-set methods.
"""

from django.db import models


class CredentialStatus(models.TextChoices):
    """Credential lifecycle states."""

    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    REVOKED = "revoked", "Revoked"
    EXPIRED = "expired", "Expired"


class AuthenticationStatus(models.TextChoices):
    """Authentication status states."""

    PENDING_MFA = "pending_mfa", "Pending MFA"
    AUTHENTICATED = "authenticated", "Fully Authenticated"


class AuthenticationMethod(models.TextChoices):
    """How the user authenticated for this session."""

    PASSWORD = "password", "Password"
    PASSWORDLESS = "passwordless", "Passwordless (Magic Link/OTP)"
    SSO = "sso", "Single Sign-On (SAML/OIDC)"
    OAUTH = "oauth", "OAuth 2.0"
    API_KEY = "api_key", "API Key"
    CERTIFICATE = "certificate", "Client Certificate (mTLS)"
    BIOMETRIC = "biometric", "Biometric"
    MFA_RECOVERY = "mfa_recovery", "MFA Recovery Code"


class MFAMethod(models.TextChoices):
    """MFA method used to complete authentication."""

    NONE = "none", "No MFA"
    TOTP = "totp", "TOTP Authenticator"
    SMS = "sms", "SMS Code"
    EMAIL = "email", "Email Code"
    PUSH = "push", "Push Notification"
    WEBAUTHN = "webauthn", "WebAuthn/FIDO2"
    RECOVERY = "recovery", "Recovery Code"


class DeviceType(models.TextChoices):
    """Device type classification."""

    DESKTOP = "desktop", "Desktop"
    MOBILE = "mobile", "Mobile"
    TABLET = "tablet", "Tablet"
    WEB = "web", "Web Browser"
    CLI = "cli", "Command Line Interface"
    API = "api", "API Client"
    IOT = "iot", "IoT Device"
    UNKNOWN = "unknown", "Unknown"


class TokenPurpose(models.TextChoices):
    """Purposes for verification tokens."""

    EMAIL_VERIFICATION = "email_verify", "Email Verification"
    PHONE_VERIFICATION = "phone_verify", "Phone Verification"
    PASSWORD_RESET = "password_reset", "Password Reset"
    PASSWORDLESS_LOGIN = "passwordless", "Passwordless Login"


class LoginAttemptResult(models.TextChoices):
    """Outcome of a login attempt."""

    SUCCESS = "success", "Success"
    INVALID_CREDENTIALS = "invalid_credentials", "Invalid Credentials"
    ACCOUNT_LOCKED = "account_locked", "Account Locked"
    ACCOUNT_DISABLED = "account_disabled", "Account Disabled"
    MFA_REQUIRED = "mfa_required", "MFA Required"
    MFA_FAILED = "mfa_failed", "MFA Failed"
    RATE_LIMITED = "rate_limited", "Rate Limited"


class PasswordSetMethod(models.TextChoices):
    """How a password was set or changed."""

    USER_CHANGE = "user_change", "User Change"
    ADMIN_RESET = "admin_reset", "Admin Reset"
    SYSTEM_RESET = "system_reset", "System Reset"
    INITIAL = "initial", "Initial Registration"
