"""Authentication views."""

from .auth import LoginView, LogoutView, MFALoginView
from .mfa import BackupCodesRegenerateView, MFADisableView, MFASetupView, MFAStatusView
from .password import PasswordChangeView, PasswordResetConfirmView, PasswordResetRequestView
from .passwordless import (
    PasswordlessRequestView,
    PasswordlessTOTPLoginView,
    PasswordlessVerifyView,
)
from .token import TokenRefreshView, TokenVerifyView
from .verification import (
    EmailVerificationConfirmView,
    EmailVerificationRequestView,
    PhoneVerificationConfirmView,
    PhoneVerificationRequestView,
)

__all__ = [
    # Login/logout
    "LoginView",
    "LogoutView",
    "MFALoginView",
    # Token management
    "TokenRefreshView",
    "TokenVerifyView",
    # MFA management
    "MFAStatusView",
    "MFASetupView",
    "MFADisableView",
    "BackupCodesRegenerateView",
    # Password management
    "PasswordChangeView",
    "PasswordResetRequestView",
    "PasswordResetConfirmView",
    # Passwordless auth
    "PasswordlessRequestView",
    "PasswordlessVerifyView",
    "PasswordlessTOTPLoginView",
    # Verification
    "EmailVerificationRequestView",
    "EmailVerificationConfirmView",
    "PhoneVerificationRequestView",
    "PhoneVerificationConfirmView",
]
