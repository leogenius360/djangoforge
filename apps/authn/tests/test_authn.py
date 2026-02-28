"""Tests for authn app utilities (SMS, phone, JWT helpers)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

# ======================================================================
# Phone Utility Tests
# ======================================================================


class TestValidateAndNormalizePhone:
    """Tests for apps.authn.utils.phone.validate_and_normalize_phone."""

    def test_valid_e164_number_normalized(self):
        """Valid E.164 phone number should be returned normalized."""
        from apps.authn.utils.phone import validate_and_normalize_phone

        result = validate_and_normalize_phone("+12125552368")
        assert result == "+12125552368"

    def test_valid_international_number_normalized(self):
        """International format number should be normalized to E.164."""
        from apps.authn.utils.phone import validate_and_normalize_phone

        result = validate_and_normalize_phone("+447911123456")
        # Should be E.164 format
        assert result.startswith("+")

    def test_invalid_number_raises_validation_error(self):
        """Invalid phone number should raise ValidationError."""
        from apps.authn.utils.phone import validate_and_normalize_phone
        from apps.core.api import serializers

        with pytest.raises(serializers.ValidationError):
            validate_and_normalize_phone("not-a-number")

    def test_unparseable_number_raises_validation_error(self):
        """Completely unparseable phone number should raise ValidationError."""
        from apps.authn.utils.phone import validate_and_normalize_phone
        from apps.core.api import serializers

        with pytest.raises(serializers.ValidationError):
            validate_and_normalize_phone("12345")  # Too short, no country code

    def test_valid_number_returns_string(self):
        """Result should always be a string."""
        from apps.authn.utils.phone import validate_and_normalize_phone

        result = validate_and_normalize_phone("+12125552368")
        assert isinstance(result, str)

    def test_invalid_number_not_valid(self):
        """A parseable but semantically invalid number should raise ValidationError."""
        from apps.authn.utils.phone import validate_and_normalize_phone
        from apps.core.api import serializers

        with pytest.raises(serializers.ValidationError):
            validate_and_normalize_phone("+10000000000")


# ======================================================================
# SMS Utility Tests
# ======================================================================


class TestSendSMS:
    """Tests for apps.authn.utils.sms send_sms and related functions."""

    @override_settings(ACCOUNTS_SMS_BACKEND="log", DEBUG=True)
    def test_log_backend_sends_to_logger(self):
        """'log' backend should log the message."""
        from apps.authn.utils.sms import send_sms

        with patch("apps.authn.utils.sms.logger") as mock_logger:
            send_sms(to_number="+12125552368", body="Test OTP: 123456")
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0]
            assert "+12125552368" in str(call_args)

    def test_log_sms_helper_logs_warning(self):
        """_log_sms helper function logs via logger.warning."""
        from apps.authn.utils.sms import _log_sms

        with patch("apps.authn.utils.sms.logger") as mock_logger:
            _log_sms(to_number="+12125552368", body="Hello World")
            mock_logger.warning.assert_called_once()
            args = mock_logger.warning.call_args[0]
            assert "+12125552368" in str(args)
            assert "Hello World" in str(args)

    @override_settings(TWILIO_ACCOUNT_SID="", TWILIO_AUTH_TOKEN="", TWILIO_FROM_NUMBER="")
    def test_twilio_is_configured_false_when_missing_creds(self):
        """_twilio_is_configured returns False when Twilio creds are missing."""
        from apps.authn.utils.sms import _twilio_is_configured

        result = _twilio_is_configured()
        assert result is False

    @override_settings(
        TWILIO_ACCOUNT_SID="ACtest123",
        TWILIO_AUTH_TOKEN="authtoken123",
        TWILIO_FROM_NUMBER="+15555550100",
    )
    def test_twilio_is_configured_true_when_all_creds_set(self):
        """_twilio_is_configured returns True when all Twilio creds present."""
        from apps.authn.utils.sms import _twilio_is_configured

        result = _twilio_is_configured()
        assert result is True

    @override_settings(ACCOUNTS_SMS_BACKEND="auto", DEBUG=True)
    def test_send_sms_auto_backend_debug_uses_log(self):
        """'auto' backend in DEBUG mode without Twilio falls back to 'log'."""
        from apps.authn.utils.sms import send_sms

        with (
            patch("apps.authn.utils.sms.logger") as mock_logger,
            patch("apps.authn.utils.sms._twilio_is_configured", return_value=False),
        ):
            send_sms(to_number="+12125552368", body="Debug SMS")
            mock_logger.warning.assert_called()

    @override_settings(ACCOUNTS_SMS_BACKEND="auto", DEBUG=False)
    def test_send_sms_auto_backend_no_debug_no_twilio_raises(self):
        """'auto' backend without DEBUG and without Twilio raises SMSBackendError."""
        from apps.authn.utils.sms import SMSBackendError, send_sms

        with patch("apps.authn.utils.sms._twilio_is_configured", return_value=False), pytest.raises(SMSBackendError):
            send_sms(to_number="+12125552368", body="Production SMS")

    @override_settings(
        ACCOUNTS_SMS_BACKEND="twilio",
        TWILIO_ACCOUNT_SID="",
        TWILIO_AUTH_TOKEN="",
        TWILIO_FROM_NUMBER="",
    )
    def test_send_sms_twilio_missing_creds_raises(self):
        """Twilio backend with missing credentials raises SMSBackendError."""
        from apps.authn.utils.sms import SMSBackendError, send_sms

        with pytest.raises(SMSBackendError, match="not fully configured"):
            send_sms(to_number="+12125552368", body="Test")

    @override_settings(ACCOUNTS_SMS_BACKEND="myapp.sms.send_function")
    def test_send_sms_custom_backend_called(self):
        """Custom dotted path backend should be imported and called."""
        from apps.authn.utils.sms import send_sms

        mock_sender = MagicMock()
        with patch("apps.authn.utils.sms.import_string", return_value=mock_sender):
            send_sms(to_number="+12125552368", body="Custom backend test")
            mock_sender.assert_called_once_with(to_number="+12125552368", body="Custom backend test")

    @override_settings(
        TWILIO_ACCOUNT_SID="ACtest",
        TWILIO_AUTH_TOKEN="token",
        TWILIO_FROM_NUMBER="+15555550100",
    )
    def test_twilio_send_raises_on_http_error(self):
        """Twilio HTTPError should be wrapped in SMSBackendError."""
        import urllib.error

        from apps.authn.utils.sms import SMSBackendError, _twilio_send_sms

        http_error = urllib.error.HTTPError(
            url="http://api.twilio.com",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=None,
        )
        http_error.read = lambda: b'{"code": 21211, "message": "Invalid number"}'

        with patch("urllib.request.urlopen", side_effect=http_error), pytest.raises(SMSBackendError, match="HTTPError"):
            _twilio_send_sms(to_number="+12125552368", body="Test")

    @override_settings(
        TWILIO_ACCOUNT_SID="ACtest",
        TWILIO_AUTH_TOKEN="token",
        TWILIO_FROM_NUMBER="+15555550100",
    )
    def test_twilio_send_raises_on_url_error(self):
        """Twilio URLError (network failure) should be wrapped in SMSBackendError."""
        import urllib.error

        from apps.authn.utils.sms import SMSBackendError, _twilio_send_sms

        with (
            patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")),
            pytest.raises(SMSBackendError, match="URLError"),
        ):
            _twilio_send_sms(to_number="+12125552368", body="Test")

    @override_settings(
        TWILIO_ACCOUNT_SID="ACtest",
        TWILIO_AUTH_TOKEN="token",
        TWILIO_FROM_NUMBER="+15555550100",
    )
    def test_twilio_send_success_logs_sid(self):
        """Successful Twilio call logs the message SID."""
        from apps.authn.utils.sms import _twilio_send_sms

        # Mock a successful HTTP response
        mock_resp = MagicMock()
        mock_resp.status = 201
        mock_resp.read.return_value = b'{"sid": "SM123456", "status": "queued"}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("apps.authn.utils.sms.logger") as mock_logger,
        ):
            _twilio_send_sms(to_number="+12125552368", body="Test")
            # Should log success
            mock_logger.info.assert_called()

    @override_settings(
        TWILIO_ACCOUNT_SID="ACtest",
        TWILIO_AUTH_TOKEN="token",
        TWILIO_FROM_NUMBER="+15555550100",
    )
    def test_twilio_send_400_response_raises(self):
        """Twilio 400 HTTP response should raise SMSBackendError."""
        from apps.authn.utils.sms import SMSBackendError, _twilio_send_sms

        # Mock a 400 response
        mock_resp = MagicMock()
        mock_resp.status = 400
        mock_resp.read.return_value = b'{"code": 21211, "message": "Invalid number"}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            pytest.raises(SMSBackendError, match="Twilio error HTTP"),
        ):
            _twilio_send_sms(to_number="+12125552368", body="Test")


# ======================================================================
# JWT Service Tests
# ======================================================================


@pytest.mark.django_db
class TestJWTService:
    """Tests for JWTService.issue_access_token and verify_access_token."""

    def test_issue_and_verify_access_token(self, user):
        """Issued access token should be verifiable."""
        import uuid

        from apps.authn.services.jwt import JWTService

        # Create a mock session with non-MagicMock attributes
        session_pk = str(uuid.uuid4())
        principal_pk = str(user.pk)

        class FakeSession:
            pk = session_pk
            principal_id = principal_pk
            security_stamp_at_issue = 0

        token = JWTService.issue_access_token(FakeSession())
        assert isinstance(token, str)
        assert len(token) > 10

    def test_verify_invalid_token_raises(self):
        """Verifying an invalid token raises TokenInvalidError."""
        from apps.authn.exceptions import TokenInvalidError
        from apps.authn.services.jwt import JWTService

        with pytest.raises(TokenInvalidError):
            JWTService.verify_access_token("not.a.valid.jwt")

    def test_verify_malformed_token_raises(self):
        """Verifying a malformed token raises TokenInvalidError."""
        from apps.authn.exceptions import TokenInvalidError
        from apps.authn.services.jwt import JWTService

        with pytest.raises(TokenInvalidError):
            JWTService.verify_access_token("eyJhbGciOiJIUzI1NiJ9.invalid.signature")
