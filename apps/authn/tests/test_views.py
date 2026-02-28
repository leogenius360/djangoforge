"""Tests for authn API views."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.authn.services import (
    AuthenticationResult,
)
from apps.core.api import status

User = get_user_model()


@pytest.fixture
def api_client():
    from django.test import Client

    return Client()


# ── Login Views ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestLoginView:
    """Tests for the login endpoint."""

    def test_login_missing_fields(self, api_client):
        url = reverse("authn:login")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_missing_password(self, api_client):
        url = reverse("authn:login")
        response = api_client.post(url, {"identifier": "test@example.com"}, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("apps.authn.api.views.auth.AuthenticationService.authenticate_with_password")
    def test_login_success(self, mock_auth, api_client, user):
        mock_session = MagicMock()
        mock_session.pk = "session-id-123"
        mock_auth.return_value = AuthenticationResult(
            principal=user,
            session=mock_session,
            auth_method="password",
        )

        url = reverse("authn:login")
        response = api_client.post(
            url,
            {"identifier": user.email, "password": "TestPass123!"},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["principal_id"] == str(user.pk)
        assert data["auth_method"] == "password"

    @patch("apps.authn.api.views.auth.AuthenticationService.authenticate_with_password")
    def test_login_invalid_credentials(self, mock_auth, api_client):
        from apps.authn.exceptions import InvalidCredentialsError

        mock_auth.side_effect = InvalidCredentialsError("bad creds")

        url = reverse("authn:login")
        response = api_client.post(
            url,
            {"identifier": "test@example.com", "password": "wrong"},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("apps.authn.api.views.auth.AuthenticationService.authenticate_with_password")
    def test_login_mfa_required(self, mock_auth, api_client):
        from apps.authn.exceptions import MFARequiredError

        mock_auth.side_effect = MFARequiredError(mfa_token="mfa-token-abc")

        url = reverse("authn:login")
        response = api_client.post(
            url,
            {"identifier": "test@example.com", "password": "TestPass123!"},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["mfa_required"] is True
        assert data["mfa_token"] == "mfa-token-abc"

    @patch("apps.authn.api.views.auth.AuthenticationService.authenticate_with_password")
    def test_login_account_locked(self, mock_auth, api_client):
        from apps.authn.exceptions import AccountLockedError

        mock_auth.side_effect = AccountLockedError(locked_until=timezone.now(), detail="Locked")

        url = reverse("authn:login")
        response = api_client.post(
            url,
            {"identifier": "test@example.com", "password": "TestPass123!"},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestMFALoginView:
    """Tests for the MFA login endpoint."""

    def test_mfa_login_missing_fields(self, api_client):
        url = reverse("authn:login-mfa")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("apps.authn.api.views.auth.AuthenticationService.complete_mfa_authentication")
    def test_mfa_login_success(self, mock_complete, api_client, user):
        mock_session = MagicMock()
        mock_session.pk = "session-id-456"
        mock_complete.return_value = AuthenticationResult(
            principal=user,
            session=mock_session,
            auth_method="password",
            mfa_method="totp",
        )

        url = reverse("authn:login-mfa")
        response = api_client.post(
            url,
            {"mfa_token": "abc123", "code": "123456"},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["mfa_method"] == "totp"

    @patch("apps.authn.api.views.auth.AuthenticationService.complete_mfa_authentication")
    def test_mfa_login_expired(self, mock_complete, api_client):
        from apps.authn.exceptions import MFAPendingExpiredError

        mock_complete.side_effect = MFAPendingExpiredError()

        url = reverse("authn:login-mfa")
        response = api_client.post(
            url,
            {"mfa_token": "expired", "code": "123456"},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ── Logout View ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestLogoutView:
    """Tests for the logout endpoint."""

    def test_logout_unauthenticated(self, api_client):
        url = reverse("authn:logout")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    @patch("apps.authn.api.views.auth.AuthenticationService.logout")
    def test_logout_success(self, mock_logout, api_client, user):
        api_client.force_login(user)
        url = reverse("authn:logout")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["detail"] == "Logged out successfully."
        mock_logout.assert_called_once()

    @patch("apps.authn.api.views.auth.AuthenticationService.logout")
    def test_logout_all_sessions(self, mock_logout, api_client, user):
        api_client.force_login(user)
        url = reverse("authn:logout")
        response = api_client.post(url, {"all_sessions": True}, content_type="application/json")
        assert response.status_code == status.HTTP_200_OK
        call_kwargs = mock_logout.call_args[1]
        assert call_kwargs["all_sessions"] is True


# ── Password Views ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestPasswordChangeView:
    """Tests for the password change endpoint."""

    def test_change_password_unauthenticated(self, api_client):
        url = reverse("authn:password-change")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    @patch("apps.authn.api.views.password.PasswordService.change_password")
    def test_change_password_success(self, mock_change, api_client, user):
        api_client.force_login(user)
        url = reverse("authn:password-change")
        response = api_client.post(
            url,
            {
                "current_password": "TestPass123!",
                "new_password": "NewSecurePass4!k",
            },
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        mock_change.assert_called_once()

    def test_change_password_missing_fields(self, api_client, user):
        api_client.force_login(user)
        url = reverse("authn:password-change")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestPasswordResetRequestView:
    """Tests for the password reset request endpoint."""

    def test_reset_request_always_succeeds(self, api_client):
        """Should return 200 even for nonexistent email (no enumeration)."""
        url = reverse("authn:password-reset")
        response = api_client.post(url, {"email": "nobody@example.com"}, content_type="application/json")
        assert response.status_code == status.HTTP_200_OK

    @patch("apps.authn.api.views.password.PasswordService.request_password_reset")
    def test_reset_request_with_existing_user(self, mock_reset, api_client, user):
        mock_reset.return_value = {
            "token": "raw-token-123",
            "expires_at": timezone.now(),
        }

        url = reverse("authn:password-reset")
        response = api_client.post(url, {"email": user.email}, content_type="application/json")
        assert response.status_code == status.HTTP_200_OK
        mock_reset.assert_called_once()

    def test_reset_request_missing_email(self, api_client):
        url = reverse("authn:password-reset")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestPasswordResetConfirmView:
    """Tests for the password reset confirm endpoint."""

    @patch("apps.authn.api.views.password.PasswordService.confirm_password_reset")
    def test_reset_confirm_success(self, mock_confirm, api_client):
        url = reverse("authn:password-reset-confirm")
        response = api_client.post(
            url,
            {"token": "valid-token", "new_password": "NewSecurePass4!k"},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        mock_confirm.assert_called_once()

    def test_reset_confirm_missing_fields(self, api_client):
        url = reverse("authn:password-reset-confirm")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ── MFA Views ───────────────────────────────────────────────────────


@pytest.mark.django_db
class TestMFAStatusView:
    """Tests for the MFA status endpoint."""

    def test_mfa_status_unauthenticated(self, api_client):
        url = reverse("authn:mfa-status")
        response = api_client.get(url, content_type="application/json")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    @patch("apps.authn.api.views.mfa.MFAService.get_status")
    def test_mfa_status_success(self, mock_status, api_client, user):
        mock_status.return_value = {
            "enabled": False,
            "totp_count": 0,
            "backup_codes_remaining": 0,
            "last_used": None,
        }
        api_client.force_login(user)
        url = reverse("authn:mfa-status")
        response = api_client.get(url, content_type="application/json")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["enabled"] is False


@pytest.mark.django_db
class TestMFASetupView:
    """Tests for the MFA setup endpoint."""

    def test_mfa_setup_unauthenticated(self, api_client):
        url = reverse("authn:mfa-setup")
        response = api_client.get(url, content_type="application/json")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    @patch("apps.authn.api.views.mfa.MFAService.setup_totp")
    def test_mfa_setup_get(self, mock_setup, api_client, user):
        mock_setup.return_value = {
            "secret": "JBSWY3DPEHPK3PXP",
            "provisioning_uri": "otpauth://totp/test?secret=...",
            "credential_id": "cred-id-123",
        }
        api_client.force_login(user)
        url = reverse("authn:mfa-setup")
        response = api_client.get(url, content_type="application/json")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "secret" in data
        assert "provisioning_uri" in data

    @patch("apps.authn.api.views.mfa.MFAService.activate_totp")
    def test_mfa_setup_post_activate(self, mock_activate, api_client, user):
        mock_activate.return_value = {
            "backup_codes": ["ABCD-1234", "EFGH-5678"],
        }
        api_client.force_login(user)
        url = reverse("authn:mfa-setup")
        response = api_client.post(url, {"code": "123456"}, content_type="application/json")
        assert response.status_code == status.HTTP_200_OK
        assert "backup_codes" in response.json()

    def test_mfa_setup_post_missing_code(self, api_client, user):
        api_client.force_login(user)
        url = reverse("authn:mfa-setup")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestMFADisableView:
    """Tests for the MFA disable endpoint."""

    def test_mfa_disable_unauthenticated(self, api_client):
        url = reverse("authn:mfa-disable")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    @patch("apps.authn.api.views.mfa.MFAService.disable_mfa")
    def test_mfa_disable_success(self, mock_disable, api_client, user):
        mock_disable.return_value = 2
        api_client.force_login(user)
        url = reverse("authn:mfa-disable")
        response = api_client.post(url, {"code": "123456"}, content_type="application/json")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["credentials_revoked"] == 2


@pytest.mark.django_db
class TestBackupCodesRegenerateView:
    """Tests for the backup codes regenerate endpoint."""

    @patch("apps.authn.api.views.mfa.MFAService.regenerate_backup_codes")
    def test_regenerate_success(self, mock_regen, api_client, user):
        mock_regen.return_value = ["ABCD-1234", "EFGH-5678"]
        api_client.force_login(user)
        url = reverse("authn:mfa-backup-codes")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()["backup_codes"]) == 2


# ── Passwordless Views ──────────────────────────────────────────────


@pytest.mark.django_db
class TestPasswordlessRequestView:
    """Tests for the passwordless request endpoint."""

    def test_passwordless_request_always_succeeds(self, api_client):
        """Should return 200 even for nonexistent email (no enumeration)."""
        url = reverse("authn:passwordless-request")
        response = api_client.post(
            url,
            {"email": "nobody@example.com", "method": "email"},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK

    def test_passwordless_request_missing_email(self, api_client):
        url = reverse("authn:passwordless-request")
        response = api_client.post(
            url,
            {"method": "email"},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestPasswordlessVerifyView:
    """Tests for the passwordless verify endpoint."""

    @patch("apps.authn.api.views.passwordless.AuthenticationService.verify_passwordless_login")
    def test_passwordless_verify_success(self, mock_verify, api_client, user):
        mock_session = MagicMock()
        mock_session.pk = "session-id-789"
        mock_verify.return_value = AuthenticationResult(
            principal=user,
            session=mock_session,
            auth_method="passwordless",
        )
        url = reverse("authn:passwordless-verify")
        response = api_client.post(
            url,
            {"token": "valid-token-abc"},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["auth_method"] == "passwordless"

    def test_passwordless_verify_missing_token(self, api_client):
        url = reverse("authn:passwordless-verify")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestPasswordlessTOTPLoginView:
    """Tests for the passwordless TOTP login endpoint."""

    @patch("apps.authn.api.views.passwordless.AuthenticationService.authenticate_totp_only")
    def test_totp_login_success(self, mock_totp, api_client, user):
        mock_session = MagicMock()
        mock_session.pk = "session-id-xxx"
        mock_totp.return_value = AuthenticationResult(
            principal=user,
            session=mock_session,
            auth_method="passwordless",
            mfa_method="totp",
        )
        url = reverse("authn:passwordless-totp")
        response = api_client.post(
            url,
            {"identifier": user.email, "code": "123456"},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["mfa_method"] == "totp"

    def test_totp_login_missing_fields(self, api_client):
        url = reverse("authn:passwordless-totp")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ── Verification Views ──────────────────────────────────────────────


@pytest.mark.django_db
class TestEmailVerificationRequestView:
    """Tests for the email verification request endpoint."""

    def test_email_verify_request_unauthenticated(self, api_client):
        url = reverse("authn:verify-email-request")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    @patch("apps.authn.api.views.verification.VerificationService.request_email_verification")
    def test_email_verify_request_success(self, mock_req, api_client, user):
        mock_req.return_value = {
            "token": "raw-token",
            "expires_at": timezone.now(),
        }
        api_client.force_login(user)
        url = reverse("authn:verify-email-request")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestEmailVerificationConfirmView:
    """Tests for the email verification confirm endpoint."""

    @patch("apps.authn.api.views.verification.VerificationService.confirm_email_verification")
    def test_email_verify_confirm_success(self, mock_confirm, api_client, user):
        mock_confirm.return_value = user
        url = reverse("authn:verify-email-confirm")
        response = api_client.post(url, {"token": "valid-token"}, content_type="application/json")
        assert response.status_code == status.HTTP_200_OK

    def test_email_verify_confirm_missing_token(self, api_client):
        url = reverse("authn:verify-email-confirm")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestPhoneVerificationRequestView:
    """Tests for the phone verification request endpoint."""

    def test_phone_verify_request_unauthenticated(self, api_client):
        url = reverse("authn:verify-phone-request")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    @patch("apps.authn.api.views.verification.VerificationService.request_phone_verification")
    def test_phone_verify_request_success(self, mock_req, api_client, user):
        mock_req.return_value = {
            "token": "raw-token",
            "otp": "123456",
            "expires_at": timezone.now(),
        }
        api_client.force_login(user)
        url = reverse("authn:verify-phone-request")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestPhoneVerificationConfirmView:
    """Tests for the phone verification confirm endpoint."""

    @patch("apps.authn.api.views.verification.VerificationService.confirm_phone_verification")
    def test_phone_verify_confirm_success(self, mock_confirm, api_client, user):
        mock_confirm.return_value = user
        api_client.force_login(user)
        url = reverse("authn:verify-phone-confirm")
        response = api_client.post(url, {"otp": "123456"}, content_type="application/json")
        assert response.status_code == status.HTTP_200_OK

    def test_phone_verify_confirm_missing_otp(self, api_client, user):
        api_client.force_login(user)
        url = reverse("authn:verify-phone-confirm")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ── Token Views ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTokenRefreshView:
    """Tests for TokenRefreshView (POST /api/authn/token/refresh/)."""

    def test_refresh_missing_token_returns_400(self, api_client):
        """Empty body should return 400."""
        url = reverse("authn:token-refresh")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "refresh_token" in response.json()["detail"]

    def test_refresh_empty_string_returns_400(self, api_client):
        """Whitespace-only token should return 400."""
        url = reverse("authn:token-refresh")
        response = api_client.post(url, {"refresh_token": "   "}, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_refresh_invalid_token_returns_401(self, api_client):
        """Non-existent refresh token returns 401."""
        url = reverse("authn:token-refresh")
        response = api_client.post(url, {"refresh_token": "nonexistent-token"}, content_type="application/json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()

    @patch("apps.sessions.models.credentials.SessionCredential.objects")
    def test_refresh_revoked_session_credential_returns_401(self, mock_sc_objects, api_client):
        """If no valid credential found (already revoked), return 401."""
        mock_sc_objects.select_related.return_value.filter.return_value.first.return_value = None
        url = reverse("authn:token-refresh")
        response = api_client.post(url, {"refresh_token": "some-valid-looking-token"}, content_type="application/json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("apps.sessions.models.credentials.SessionCredential.objects")
    def test_refresh_invalid_session_returns_401(self, mock_sc_objects, api_client):
        """If the underlying session is not valid, return 401."""
        mock_session = MagicMock()
        mock_session.is_valid = False

        mock_credential = MagicMock()
        mock_credential.session = mock_session

        mock_sc_objects.select_related.return_value.filter.return_value.first.return_value = mock_credential

        url = reverse("authn:token-refresh")
        response = api_client.post(url, {"refresh_token": "valid-token"}, content_type="application/json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Session is no longer valid" in response.json()["detail"]

    @patch("apps.authn.api.views.token.JWTService")
    @patch("apps.sessions.models.credentials.SessionCredential.objects")
    def test_refresh_success_returns_new_tokens(self, mock_sc_objects, mock_jwt, api_client):
        """Successful refresh returns new access_token and refresh_token."""
        from django.utils import timezone as tz

        mock_session = MagicMock()
        mock_session.is_valid = True
        mock_session.credentials = MagicMock()
        mock_session.credentials.create = MagicMock()

        mock_credential = MagicMock()
        mock_credential.session = mock_session
        mock_credential.family_id = None
        mock_credential.pk = "cred-pk-123"
        mock_credential.expires_at = tz.now()

        mock_sc_objects.select_related.return_value.filter.return_value.first.return_value = mock_credential
        mock_jwt.issue_access_token.return_value = "new-access-token-jwt"

        url = reverse("authn:token-refresh")
        response = api_client.post(url, {"refresh_token": "valid-refresh-token"}, content_type="application/json")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "Bearer"
        assert "expires_in" in data
        # Old credential should be revoked
        assert mock_credential.is_revoked is True
        mock_credential.save.assert_called_once()


@pytest.mark.django_db
class TestTokenVerifyView:
    """Tests for TokenVerifyView (POST /api/authn/token/verify/)."""

    def test_verify_missing_token_returns_400(self, api_client):
        """Empty body should return 400."""
        url = reverse("authn:token-verify")
        response = api_client.post(url, {}, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "token" in response.json()["detail"]

    def test_verify_empty_string_returns_400(self, api_client):
        """Whitespace-only token should return 400."""
        url = reverse("authn:token-verify")
        response = api_client.post(url, {"token": "   "}, content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("apps.authn.api.views.token.JWTService")
    def test_verify_expired_token_returns_401(self, mock_jwt, api_client):
        """Expired JWT should return 401."""
        from apps.authn.exceptions import TokenExpiredError

        mock_jwt.verify_access_token.side_effect = TokenExpiredError("expired")
        url = reverse("authn:token-verify")
        response = api_client.post(url, {"token": "expired.jwt.token"}, content_type="application/json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "expired" in response.json()["detail"].lower()

    @patch("apps.authn.api.views.token.JWTService")
    def test_verify_invalid_token_returns_401(self, mock_jwt, api_client):
        """Invalid JWT signature/format should return 401."""
        from apps.authn.exceptions import TokenInvalidError

        mock_jwt.verify_access_token.side_effect = TokenInvalidError("bad signature")
        url = reverse("authn:token-verify")
        response = api_client.post(url, {"token": "bad.jwt.token"}, content_type="application/json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "bad signature" in response.json()["detail"]

    @patch("apps.authn.api.views.token.JWTService")
    def test_verify_valid_token_returns_200(self, mock_jwt, api_client):
        """Valid JWT should return 200 with payload fields."""
        import time

        exp = int(time.time()) + 3600
        mock_jwt.verify_access_token.return_value = {
            "sub": "principal-uuid",
            "sid": "session-uuid",
            "exp": exp,
        }
        url = reverse("authn:token-verify")
        response = api_client.post(url, {"token": "valid.jwt.token"}, content_type="application/json")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["valid"] is True
        assert data["sub"] == "principal-uuid"
        assert data["sid"] == "session-uuid"
        assert data["exp"] == exp
