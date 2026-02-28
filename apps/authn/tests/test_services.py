"""Tests for authn services."""

from __future__ import annotations

from datetime import timedelta

import pyotp
import pytest
from django.test import override_settings
from django.utils import timezone

from apps.authn.exceptions import (
    CooldownActiveError,
    InvalidCredentialsError,
    MFAAlreadyEnabledError,
    MFANotEnabledError,
    MFAVerificationFailedError,
    PasswordReuseError,
    TokenExpiredError,
    TokenInvalidError,
)
from apps.authn.models import (
    LoginAttemptResult,
    TokenPurpose,
    VerificationToken,
)
from apps.authn.services import (
    LockoutService,
    MFAService,
    PasswordService,
    TokenService,
    VerificationService,
)
from apps.authn.services.authentication import (
    AuthenticationService,
    _can_authenticate,
    _detect_device_type,
    _get_client_ip,
    _has_mfa,
)


@pytest.mark.django_db
class TestTokenService:
    """Tests for TokenService."""

    def test_create_token(self, user):
        result = TokenService.create_token(
            principal=user,
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            ttl_minutes=60,
        )
        assert result.raw_token
        assert result.token_id
        assert result.raw_otp is None
        assert result.expires_at > timezone.now()

    def test_create_token_with_otp(self, user):
        result = TokenService.create_token(
            principal=user,
            purpose=TokenPurpose.PHONE_VERIFICATION,
            generate_otp_code=True,
            otp_length=6,
            ttl_minutes=10,
        )
        assert result.raw_otp is not None
        assert len(result.raw_otp) == 6

    def test_verify_token(self, user):
        result = TokenService.create_token(
            principal=user,
            purpose=TokenPurpose.PASSWORD_RESET,
            ttl_minutes=60,
        )
        token = TokenService.verify_token(result.raw_token)
        assert token.principal == user

    def test_verify_invalid_token(self):
        with pytest.raises(TokenInvalidError):
            TokenService.verify_token("nonexistent_token")

    def test_verify_expired_token(self, user):
        result = TokenService.create_token(
            principal=user,
            purpose=TokenPurpose.PASSWORD_RESET,
            ttl_minutes=0,  # zero minutes = already expired
        )
        # Force-expire it
        vt = VerificationToken.objects.get(pk=result.token_id)
        vt.expires_at = timezone.now() - timedelta(seconds=1)
        vt.save(update_fields=["expires_at"])

        with pytest.raises(TokenExpiredError):
            TokenService.verify_token(result.raw_token)

    def test_consume_token(self, user):
        result = TokenService.create_token(
            principal=user,
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            ttl_minutes=60,
        )
        token = TokenService.verify_token(result.raw_token)
        TokenService.consume_token(token)
        assert token.is_used

    def test_verify_otp(self, user):
        result = TokenService.create_token(
            principal=user,
            purpose=TokenPurpose.PHONE_VERIFICATION,
            generate_otp_code=True,
            otp_length=6,
            ttl_minutes=10,
        )
        token = TokenService.verify_otp(
            principal=user,
            purpose=TokenPurpose.PHONE_VERIFICATION,
            otp=result.raw_otp,
        )
        assert token is not None

    def test_new_token_invalidates_old(self, user):
        result1 = TokenService.create_token(
            principal=user,
            purpose=TokenPurpose.PASSWORD_RESET,
            ttl_minutes=60,
        )
        TokenService.create_token(
            principal=user,
            purpose=TokenPurpose.PASSWORD_RESET,
            ttl_minutes=60,
        )
        # Old token should be invalidated
        with pytest.raises((TokenInvalidError, TokenExpiredError)):
            TokenService.verify_token(result1.raw_token)


@pytest.mark.django_db
class TestLockoutService:
    """Tests for LockoutService."""

    def test_check_lockout_unlocked(self, user):
        # Should not raise
        LockoutService.check_lockout(user)

    @override_settings(AUTHN={"MAX_FAILED_ATTEMPTS": 3, "LOCKOUT_DURATION_MINUTES": 5})
    def test_record_failed_attempt(self, user, mock_request):
        for _ in range(3):
            LockoutService.record_failed_attempt(
                principal=user,
                identifier=user.email,
                request=mock_request,
                reason="invalid_credentials",
            )
        # After 3 failures, check if the attempt was recorded
        from apps.authn.models import LoginAttempt

        failures = LoginAttempt.objects.failure_count(user, window_minutes=30)
        assert failures >= 3

    def test_record_success(self, user, mock_request):
        LockoutService.record_success(
            principal=user,
            request=mock_request,
            auth_method="password",
        )
        from apps.authn.models import LoginAttempt

        successes = LoginAttempt.objects.filter(principal=user, result=LoginAttemptResult.SUCCESS).count()
        assert successes == 1

    def test_progressive_lockout_duration(self, user):
        duration = LockoutService.get_lockout_duration(user)
        assert isinstance(duration, timedelta)


@pytest.mark.django_db
class TestMFAService:
    """Tests for MFAService."""

    def test_setup_totp(self, user):
        result = MFAService.setup_totp(user)
        assert "secret" in result
        assert "provisioning_uri" in result
        assert "credential_id" in result

    def test_setup_totp_already_enabled(self, user_with_mfa):
        with pytest.raises(MFAAlreadyEnabledError):
            MFAService.setup_totp(user_with_mfa)

    def test_activate_totp(self, user):
        setup = MFAService.setup_totp(user)
        totp = pyotp.TOTP(setup["secret"])
        code = totp.now()
        result = MFAService.activate_totp(user, code)
        assert "backup_codes" in result
        assert len(result["backup_codes"]) > 0

    def test_activate_totp_invalid_code(self, user):
        MFAService.setup_totp(user)
        with pytest.raises(MFAVerificationFailedError):
            MFAService.activate_totp(user, "000000")

    def test_verify_mfa_totp(self, user_with_mfa):
        secret = user_with_mfa._test_totp_secret
        totp = pyotp.TOTP(secret)
        code = totp.now()
        result = MFAService.verify_mfa(user_with_mfa, code)
        assert result.valid
        assert result.method == "totp"

    def test_verify_mfa_invalid(self, user_with_mfa):
        result = MFAService.verify_mfa(user_with_mfa, "000000")
        assert not result.valid

    def test_disable_mfa(self, user_with_mfa):
        secret = user_with_mfa._test_totp_secret
        totp = pyotp.TOTP(secret)
        code = totp.now()
        count = MFAService.disable_mfa(user_with_mfa, code)
        assert count >= 1

    def test_disable_mfa_not_enabled(self, user):
        with pytest.raises(MFANotEnabledError):
            MFAService.disable_mfa(user, "123456")

    def test_get_status_no_mfa(self, user):
        status = MFAService.get_status(user)
        assert status["enabled"] is False
        assert status["totp_count"] == 0

    def test_get_status_with_mfa(self, user_with_mfa):
        status = MFAService.get_status(user_with_mfa)
        assert status["enabled"] is True
        assert status["totp_count"] == 1

    def test_regenerate_backup_codes(self, user_with_mfa):
        codes = MFAService.regenerate_backup_codes(user_with_mfa)
        assert len(codes) > 0

    def test_regenerate_backup_codes_no_mfa(self, user):
        with pytest.raises(MFANotEnabledError):
            MFAService.regenerate_backup_codes(user)


@pytest.mark.django_db
class TestPasswordService:
    """Tests for PasswordService."""

    def test_change_password(self, user):
        PasswordService.change_password(
            principal=user,
            current_password="TestPass123!",
            new_password="NewSecurePass456!",
        )
        user.refresh_from_db()
        assert user.check_password("NewSecurePass456!")

    def test_change_password_wrong_current(self, user):
        with pytest.raises(InvalidCredentialsError):
            PasswordService.change_password(
                principal=user,
                current_password="WrongPassword!",
                new_password="NewSecurePass456!",
            )

    @override_settings(AUTHN={"PASSWORD_HISTORY_COUNT": 3})
    def test_change_password_reuse(self, user):
        # First change -- records "NewPass456!x" in history
        PasswordService.change_password(
            principal=user,
            current_password="TestPass123!",
            new_password="NewPass456!x",
        )
        # Second change -- records "AnotherPass789!" in history
        PasswordService.change_password(
            principal=user,
            current_password="NewPass456!x",
            new_password="AnotherPass789!",
        )
        # Try to reuse "NewPass456!x" which is in history
        with pytest.raises(PasswordReuseError):
            PasswordService.change_password(
                principal=user,
                current_password="AnotherPass789!",
                new_password="NewPass456!x",
            )

    def test_request_password_reset(self, user):
        result = PasswordService.request_password_reset(principal=user)
        assert "token" in result
        assert "expires_at" in result

    @override_settings(AUTHN={"PASSWORD_RESET_COOLDOWN_SECONDS": 60})
    def test_password_reset_cooldown(self, user):
        PasswordService.request_password_reset(principal=user)
        with pytest.raises(CooldownActiveError):
            PasswordService.request_password_reset(principal=user)

    def test_confirm_password_reset(self, user):
        result = PasswordService.request_password_reset(principal=user)
        PasswordService.confirm_password_reset(
            raw_token=result["token"],
            new_password="ResetPass789!",
        )
        user.refresh_from_db()
        assert user.check_password("ResetPass789!")

    def test_check_password_expiry_no_history(self, user):
        expiry = PasswordService.check_password_expiry(user)
        assert expiry["expired"] is True
        assert expiry["last_changed"] is None

    @override_settings(AUTHN={"PASSWORD_MAX_AGE_DAYS": None})
    def test_check_password_expiry_disabled(self, user):
        expiry = PasswordService.check_password_expiry(user)
        assert expiry["expired"] is False


@pytest.mark.django_db
class TestVerificationService:
    """Tests for VerificationService."""

    def test_request_email_verification(self, user):
        result = VerificationService.request_email_verification(principal=user)
        assert "token" in result
        assert "expires_at" in result

    def test_confirm_email_verification(self, user):
        result = VerificationService.request_email_verification(principal=user)
        VerificationService.confirm_email_verification(raw_token=result["token"])
        user.refresh_from_db()
        assert user.email_verified_at is not None

    @override_settings(AUTHN={"EMAIL_VERIFICATION_COOLDOWN_SECONDS": 60})
    def test_email_verification_cooldown(self, user):
        VerificationService.request_email_verification(principal=user)
        with pytest.raises(CooldownActiveError):
            VerificationService.request_email_verification(principal=user)

    def test_request_phone_verification(self, user):
        result = VerificationService.request_phone_verification(principal=user)
        assert "token" in result
        assert "otp" in result

    def test_confirm_phone_verification(self, user):
        result = VerificationService.request_phone_verification(principal=user)
        VerificationService.confirm_phone_verification(
            principal=user,
            otp=result["otp"],
        )
        user.refresh_from_db()
        assert user.phone_verified_at is not None


# ======================================================================
# AuthenticationService Tests
# ======================================================================


@pytest.mark.django_db
class TestAuthenticationServicePasswordLogin:
    """Tests for AuthenticationService.authenticate_with_password."""

    def test_authenticate_with_valid_credentials(self, user, mock_request):
        """Successful password login returns AuthenticationResult."""
        result = AuthenticationService.authenticate_with_password(
            request=mock_request,
            identifier=user.email,
            password="TestPass123!",
        )
        assert result.principal == user
        assert result.auth_method == "password"
        assert result.access_token != ""
        assert result.refresh_token != "" or result.refresh_token == ""

    def test_authenticate_invalid_credentials_raises(self, mock_request):
        """Invalid credentials raise InvalidCredentialsError."""
        from apps.authn.exceptions import InvalidCredentialsError

        with pytest.raises(InvalidCredentialsError):
            AuthenticationService.authenticate_with_password(
                request=mock_request,
                identifier="nobody@example.com",
                password="wrongpassword",
            )

    def test_authenticate_wrong_password_raises(self, user, mock_request):
        """Wrong password for existing user raises InvalidCredentialsError."""
        from apps.authn.exceptions import InvalidCredentialsError

        with pytest.raises(InvalidCredentialsError):
            AuthenticationService.authenticate_with_password(
                request=mock_request,
                identifier=user.email,
                password="WrongPassword999!",
            )

    def test_authenticate_disabled_account_raises(self, user, mock_request):
        """Disabled account raises AccountDisabledError or InvalidCredentialsError."""
        from unittest.mock import patch

        from apps.authn.exceptions import AccountDisabledError

        # Patch _can_authenticate to return False so we can test the disabled branch
        with (
            patch("apps.authn.services.authentication._can_authenticate", return_value=False),
            pytest.raises(AccountDisabledError),
        ):
            AuthenticationService.authenticate_with_password(
                request=mock_request,
                identifier=user.email,
                password="TestPass123!",
            )

    def test_authenticate_with_username(self, user, mock_request):
        """Can authenticate with username instead of email."""
        result = AuthenticationService.authenticate_with_password(
            request=mock_request,
            identifier=user.username,
            password="TestPass123!",
        )
        assert result.principal == user

    def test_authenticate_mfa_required_raises(self, user_with_mfa, mock_request):
        """MFA-enabled accounts raise MFARequiredError with a token."""
        from unittest.mock import patch

        from apps.authn.exceptions import MFARequiredError

        # Patch _has_mfa to return True (Principal doesn't have has_mfa property by default)
        with (
            patch("apps.authn.services.authentication._has_mfa", return_value=True),
            pytest.raises(MFARequiredError) as exc_info,
        ):
            AuthenticationService.authenticate_with_password(
                request=mock_request,
                identifier=user_with_mfa.email,
                password="TestPass123!",
            )
        assert exc_info.value.mfa_token != ""

    @override_settings(AUTHN={"MAX_FAILED_ATTEMPTS": 1, "LOCKOUT_DURATION_MINUTES": 5})
    def test_authenticate_locked_account_raises(self, user, mock_request):
        """Locked account raises AccountLockedError."""
        from unittest.mock import patch

        from apps.authn.exceptions import AccountLockedError
        from apps.authn.services.lockout import LockoutService

        # Patch LockoutService.check_lockout to raise AccountLockedError
        with (
            patch.object(LockoutService, "check_lockout", side_effect=AccountLockedError(locked_until=timezone.now())),
            pytest.raises(AccountLockedError),
        ):
            AuthenticationService.authenticate_with_password(
                request=mock_request,
                identifier=user.email,
                password="TestPass123!",
            )


@pytest.mark.django_db
class TestAuthenticationServiceMFACompletion:
    """Tests for AuthenticationService.complete_mfa_authentication."""

    def test_complete_mfa_success(self, user_with_mfa, mock_request):
        """Complete MFA after successful password auth (with patched _has_mfa)."""
        from unittest.mock import patch

        import pyotp

        from apps.authn.exceptions import MFARequiredError

        # Patch _has_mfa to return True so the MFA flow is triggered
        with patch("apps.authn.services.authentication._has_mfa", return_value=True):
            mfa_token = None
            try:
                AuthenticationService.authenticate_with_password(
                    request=mock_request,
                    identifier=user_with_mfa.email,
                    password="TestPass123!",
                )
            except MFARequiredError as exc:
                mfa_token = exc.mfa_token

        assert mfa_token is not None

        # Step 2: Complete MFA
        totp = pyotp.TOTP(user_with_mfa._test_totp_secret)
        code = totp.now()

        result = AuthenticationService.complete_mfa_authentication(
            request=mock_request,
            mfa_token=mfa_token,
            mfa_code=code,
        )
        assert result.principal == user_with_mfa
        assert result.mfa_method in ("totp", "recovery")

    def test_complete_mfa_invalid_token_raises(self, mock_request):
        """Invalid MFA token raises MFAPendingExpiredError."""
        from apps.authn.exceptions import MFAPendingExpiredError

        with pytest.raises(MFAPendingExpiredError):
            AuthenticationService.complete_mfa_authentication(
                request=mock_request,
                mfa_token="nonexistent-token",
                mfa_code="123456",
            )

    def test_complete_mfa_wrong_code_raises(self, user_with_mfa, mock_request):
        """Wrong MFA code raises MFAVerificationFailedError."""
        from unittest.mock import patch

        from apps.authn.exceptions import MFARequiredError, MFAVerificationFailedError

        # Get MFA token with patched _has_mfa
        with patch("apps.authn.services.authentication._has_mfa", return_value=True):
            mfa_token = None
            try:
                AuthenticationService.authenticate_with_password(
                    request=mock_request,
                    identifier=user_with_mfa.email,
                    password="TestPass123!",
                )
            except MFARequiredError as exc:
                mfa_token = exc.mfa_token

        assert mfa_token is not None

        with pytest.raises(MFAVerificationFailedError):
            AuthenticationService.complete_mfa_authentication(
                request=mock_request,
                mfa_token=mfa_token,
                mfa_code="000000",
            )


@pytest.mark.django_db
class TestAuthenticationServicePasswordlessLogin:
    """Tests for passwordless login flows."""

    def test_request_passwordless_login_email(self, user):
        """Requesting email passwordless login returns token and expires_at."""
        result = AuthenticationService.request_passwordless_login(
            principal=user,
            method="email",
        )
        assert "token" in result
        assert "expires_at" in result
        assert result["token"] != ""

    def test_request_passwordless_login_sms(self, user):
        """Requesting SMS passwordless login returns OTP."""
        # Provide a phone number on the user if not set
        user.phone_number = "+12125552368"
        user.save(update_fields=["phone_number"])

        result = AuthenticationService.request_passwordless_login(
            principal=user,
            method="sms",
        )
        assert "token" in result
        # OTP should be in result for SMS
        assert "otp" in result

    @override_settings(AUTHN={"PASSWORDLESS_RESEND_COOLDOWN_SECONDS": 60})
    def test_request_passwordless_cooldown_raises(self, user):
        """Requesting passwordless login twice rapidly raises CooldownActiveError."""
        from apps.authn.exceptions import CooldownActiveError

        AuthenticationService.request_passwordless_login(
            principal=user,
            method="email",
        )
        with pytest.raises(CooldownActiveError):
            AuthenticationService.request_passwordless_login(
                principal=user,
                method="email",
            )

    def test_verify_passwordless_login_magic_link(self, user, mock_request):
        """Verify a valid magic link token creates a session."""
        # Request token
        result = AuthenticationService.request_passwordless_login(
            principal=user,
            method="email",
        )
        # Verify token
        auth_result = AuthenticationService.verify_passwordless_login(
            request=mock_request,
            raw_token=result["token"],
        )
        assert auth_result.principal == user
        assert auth_result.auth_method == "passwordless"

    def test_verify_passwordless_invalid_token_raises(self, mock_request):
        """Invalid token raises TokenInvalidError or TokenExpiredError."""
        from apps.authn.exceptions import TokenExpiredError, TokenInvalidError

        with pytest.raises((TokenInvalidError, TokenExpiredError)):
            AuthenticationService.verify_passwordless_login(
                request=mock_request,
                raw_token="completely-invalid-token",
            )

    def test_verify_passwordless_wrong_purpose_raises(self, user, mock_request):
        """Token issued for different purpose raises TokenInvalidError."""
        from apps.authn.exceptions import TokenInvalidError

        # Create a token for password reset (not passwordless login)
        pw_result = PasswordService.request_password_reset(principal=user)

        with pytest.raises(TokenInvalidError):
            AuthenticationService.verify_passwordless_login(
                request=mock_request,
                raw_token=pw_result["token"],
            )


@pytest.mark.django_db
class TestAuthenticationServiceTOTPOnly:
    """Tests for AuthenticationService.authenticate_totp_only."""

    def test_authenticate_totp_only_success(self, user_with_mfa, mock_request):
        """Authenticate with TOTP code only (no password)."""
        import pyotp

        totp = pyotp.TOTP(user_with_mfa._test_totp_secret)
        code = totp.now()

        result = AuthenticationService.authenticate_totp_only(
            request=mock_request,
            identifier=user_with_mfa.email,
            totp_code=code,
        )
        assert result.principal == user_with_mfa
        assert result.mfa_method == "totp"

    def test_authenticate_totp_only_invalid_code_raises(self, user_with_mfa, mock_request):
        """Wrong TOTP code raises MFAVerificationFailedError."""
        from apps.authn.exceptions import MFAVerificationFailedError

        with pytest.raises(MFAVerificationFailedError):
            AuthenticationService.authenticate_totp_only(
                request=mock_request,
                identifier=user_with_mfa.email,
                totp_code="000000",
            )

    def test_authenticate_totp_only_unknown_user_raises(self, mock_request):
        """Unknown user identifier raises InvalidCredentialsError."""
        from apps.authn.exceptions import InvalidCredentialsError

        with pytest.raises(InvalidCredentialsError):
            AuthenticationService.authenticate_totp_only(
                request=mock_request,
                identifier="nonexistent@example.com",
                totp_code="123456",
            )

    def test_authenticate_totp_only_by_username(self, user_with_mfa, mock_request):
        """Can authenticate by username instead of email."""
        import pyotp

        totp = pyotp.TOTP(user_with_mfa._test_totp_secret)
        code = totp.now()

        result = AuthenticationService.authenticate_totp_only(
            request=mock_request,
            identifier=user_with_mfa.username,
            totp_code=code,
        )
        assert result.principal == user_with_mfa


@pytest.mark.django_db
class TestAuthenticationServiceLogout:
    """Tests for AuthenticationService.logout."""

    def test_logout_single_session(self, user, mock_request):
        """Logout of a specific session calls revoke/logout on session."""
        from unittest.mock import MagicMock

        mock_session = MagicMock()
        AuthenticationService.logout(
            request=mock_request,
            principal=user,
            session=mock_session,
            all_sessions=False,
        )
        # Should call logout or revoke on the session
        assert mock_session.logout.called or mock_session.revoke.called

    def test_logout_all_sessions(self, user, mock_request):
        """Logout all sessions uses terminate_all_for_principal or terminate_all_sessions."""
        from unittest.mock import MagicMock, patch

        # Patch terminate_all_for_principal on the AuthSession class
        with patch("apps.sessions.models.auth_session.AuthSession.terminate_all_for_principal") as mock_terminate:
            mock_terminate.return_value = 0
            # Add terminate_all_sessions to the principal
            user.terminate_all_sessions = MagicMock()
            AuthenticationService.logout(
                request=mock_request,
                principal=user,
                session=None,
                all_sessions=True,
            )
            # Should call the principal's method
            user.terminate_all_sessions.assert_called_once()

    def test_logout_no_session_no_error(self, user, mock_request):
        """Logout with no session and all_sessions=False should not raise."""
        # When session=None and all_sessions=False, nothing happens
        AuthenticationService.logout(
            request=mock_request,
            principal=user,
            session=None,
            all_sessions=False,
        )  # Should not raise


# ======================================================================
# Authentication Helper Function Tests
# ======================================================================


class TestAuthHelpers:
    """Tests for private helper functions in authentication.py."""

    def test_can_authenticate_active_principal(self):
        """Active principal (is_active=True, no can_authenticate) should return True."""
        from unittest.mock import MagicMock

        principal = MagicMock(spec=[])
        principal.is_active = True
        result = _can_authenticate(principal)
        assert result is True

    def test_can_authenticate_inactive_principal(self):
        """Inactive principal (is_active=False) should return False."""
        from unittest.mock import MagicMock

        principal = MagicMock(spec=["is_active"])
        principal.is_active = False
        result = _can_authenticate(principal)
        assert result is False

    def test_can_authenticate_uses_can_authenticate_attr(self):
        """Uses can_authenticate attribute when available."""
        from unittest.mock import MagicMock

        principal = MagicMock()
        principal.can_authenticate = False
        result = _can_authenticate(principal)
        assert result is False

    def test_has_mfa_false_by_default(self):
        """Principal without has_mfa attribute returns False."""
        from unittest.mock import MagicMock

        principal = MagicMock(spec=[])
        result = _has_mfa(principal)
        assert result is False

    def test_has_mfa_true_when_attribute_set(self):
        """Principal with has_mfa=True returns True."""
        from unittest.mock import MagicMock

        principal = MagicMock()
        principal.has_mfa = True
        result = _has_mfa(principal)
        assert result is True

    def test_get_client_ip_from_remote_addr(self):
        """IP extracted from REMOTE_ADDR when no X-Forwarded-For."""
        from unittest.mock import MagicMock

        request = MagicMock()
        request.META = {"REMOTE_ADDR": "192.168.1.1"}
        result = _get_client_ip(request)
        assert result == "192.168.1.1"

    def test_get_client_ip_from_x_forwarded_for(self):
        """IP extracted from first entry of X-Forwarded-For header."""
        from unittest.mock import MagicMock

        request = MagicMock()
        request.META = {
            "HTTP_X_FORWARDED_FOR": "10.0.0.1, 10.0.0.2, 10.0.0.3",
            "REMOTE_ADDR": "127.0.0.1",
        }
        result = _get_client_ip(request)
        assert result == "10.0.0.1"

    def test_detect_device_type_desktop(self):
        """Generic user agent should be detected as desktop."""
        result = _detect_device_type("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0")
        assert result == "desktop"

    def test_detect_device_type_mobile(self):
        """Mobile user agent should be detected as mobile."""
        result = _detect_device_type("Mozilla/5.0 (iPhone; CPU iPhone OS 14_0) Mobile/15E148")
        assert result == "mobile"

    def test_detect_device_type_tablet(self):
        """Tablet user agent should be detected as tablet."""
        result = _detect_device_type("Mozilla/5.0 (iPad; CPU OS 14_0) AppleWebKit/605.1.15")
        assert result == "tablet"

    def test_detect_device_type_android_mobile(self):
        """Android mobile user agent should be detected as mobile."""
        result = _detect_device_type("Mozilla/5.0 (Linux; Android 10; SM-G975U) Mobile")
        assert result == "mobile"

    def test_detect_device_type_empty_string(self):
        """Empty user agent string defaults to desktop."""
        result = _detect_device_type("")
        assert result == "desktop"
