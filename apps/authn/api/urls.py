"""
URL configuration for authn app.

Provides endpoints for:
- Authentication (password, passwordless, MFA)
- MFA management
- Password management
- Email/phone verification
"""

from django.urls import path

from .views import (
    BackupCodesRegenerateView,
    EmailVerificationConfirmView,
    EmailVerificationRequestView,
    LoginView,
    LogoutView,
    MFADisableView,
    MFALoginView,
    MFASetupView,
    MFAStatusView,
    PasswordChangeView,
    PasswordlessRequestView,
    PasswordlessTOTPLoginView,
    PasswordlessVerifyView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PhoneVerificationConfirmView,
    PhoneVerificationRequestView,
    TokenRefreshView,
    TokenVerifyView,
)

app_name = "authn"

urlpatterns = [
    # ── Authentication ───────────────────────────────────────────────
    path("login/", LoginView.as_view(), name="login"),
    path("login/mfa/", MFALoginView.as_view(), name="login-mfa"),
    path("logout/", LogoutView.as_view(), name="logout"),
    # ── Token management (replaces simplejwt endpoints) ──────────────
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("token/verify/", TokenVerifyView.as_view(), name="token-verify"),
    # ── Password management ──────────────────────────────────────────
    path("password/change/", PasswordChangeView.as_view(), name="password-change"),
    path("password/reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path("password/reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    # ── MFA management ───────────────────────────────────────────────
    path("mfa/status/", MFAStatusView.as_view(), name="mfa-status"),
    path("mfa/setup/", MFASetupView.as_view(), name="mfa-setup"),
    path("mfa/disable/", MFADisableView.as_view(), name="mfa-disable"),
    path("mfa/backup-codes/", BackupCodesRegenerateView.as_view(), name="mfa-backup-codes"),
    # ── Passwordless authentication ──────────────────────────────────
    path("passwordless/request/", PasswordlessRequestView.as_view(), name="passwordless-request"),
    path("passwordless/verify/", PasswordlessVerifyView.as_view(), name="passwordless-verify"),
    path("passwordless/totp/", PasswordlessTOTPLoginView.as_view(), name="passwordless-totp"),
    # ── Verification ─────────────────────────────────────────────────
    path("verify/email/request/", EmailVerificationRequestView.as_view(), name="verify-email-request"),
    path("verify/email/confirm/", EmailVerificationConfirmView.as_view(), name="verify-email-confirm"),
    path("verify/phone/request/", PhoneVerificationRequestView.as_view(), name="verify-phone-request"),
    path("verify/phone/confirm/", PhoneVerificationConfirmView.as_view(), name="verify-phone-confirm"),
]
