"""Authentication serializers."""

from .auth import (
    AuthResponseSerializer,
    LoginSerializer,
    LogoutSerializer,
    MFALoginSerializer,
    PasswordlessRequestSerializer,
    PasswordlessTOTPLoginSerializer,
    PasswordlessVerifySerializer,
)
from .mfa import (
    BackupCodesRegenerateSerializer,
    MFAActivateResponseSerializer,
    MFADisableResponseSerializer,
    MFADisableSerializer,
    MFASetupResponseSerializer,
    MFAStatusSerializer,
    MFAVerifySetupSerializer,
)
from .mfa import (
    MFASetupResponseSerializer as MFASetupSerializer,
)
from .password import (
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
)
from .token import (
    TokenRefreshResponseSerializer,
    TokenRefreshSerializer,
    TokenVerifyResponseSerializer,
    TokenVerifySerializer,
)
from .verification import (
    EmailVerificationConfirmSerializer,
    EmailVerificationRequestSerializer,
    PhoneVerificationConfirmSerializer,
    PhoneVerificationRequestSerializer,
)

__all__ = [
    # Auth
    "LoginSerializer",
    "LogoutSerializer",
    "AuthResponseSerializer",
    "MFALoginSerializer",
    "PasswordlessRequestSerializer",
    "PasswordlessVerifySerializer",
    "PasswordlessTOTPLoginSerializer",
    # MFA
    "MFASetupResponseSerializer",
    "MFASetupSerializer",
    "MFAVerifySetupSerializer",
    "MFADisableSerializer",
    "MFAStatusSerializer",
    "BackupCodesRegenerateSerializer",
    "MFAActivateResponseSerializer",
    "MFADisableResponseSerializer",
    # Password
    "PasswordChangeSerializer",
    "PasswordResetRequestSerializer",
    "PasswordResetConfirmSerializer",
    # Token
    "TokenRefreshSerializer",
    "TokenRefreshResponseSerializer",
    "TokenVerifySerializer",
    "TokenVerifyResponseSerializer",
    # Verification
    "EmailVerificationRequestSerializer",
    "EmailVerificationConfirmSerializer",
    "PhoneVerificationRequestSerializer",
    "PhoneVerificationConfirmSerializer",
]
