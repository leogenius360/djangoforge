"""Tests for authn models."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.hashers import make_password
from django.utils import timezone

from apps.authn.models import (
    BackupCode,
    CredentialStatus,
    LoginAttempt,
    LoginAttemptResult,
    MFAPendingAuthentication,
    PasswordCredential,
    PasswordHistory,
    PasswordSetMethod,
    TokenPurpose,
    TOTPCredential,
    VerificationToken,
)
from apps.authn.utils.tokens import hmac_hash


@pytest.mark.django_db
class TestVerificationToken:
    """Tests for VerificationToken model (HMAC-hashed storage)."""

    def test_create_for_user(self, user):
        token = VerificationToken.create_for_principal(
            principal=user,
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            token_hash=hmac_hash("raw_token_123"),
            ttl=timedelta(hours=24),
            delivery_target=user.email,
        )
        assert token.principal == user
        assert token.purpose == TokenPurpose.EMAIL_VERIFICATION
        assert token.token_hash != ""
        assert token.delivery_target == user.email
        assert token.is_valid

    def test_is_valid_checks(self, user):
        token = VerificationToken.create_for_principal(
            principal=user,
            purpose=TokenPurpose.PASSWORD_RESET,
            token_hash=hmac_hash("test"),
            ttl=timedelta(hours=1),
        )
        assert token.is_valid
        assert not token.is_expired
        assert not token.is_used
        assert not token.attempts_exceeded

    def test_expired_token(self, user):
        token = VerificationToken.create_for_principal(
            principal=user,
            purpose=TokenPurpose.PASSWORD_RESET,
            token_hash=hmac_hash("test"),
            ttl=timedelta(seconds=-1),  # Already expired
        )
        assert token.is_expired
        assert not token.is_valid

    def test_mark_used(self, user):
        token = VerificationToken.create_for_principal(
            principal=user,
            purpose=TokenPurpose.PASSWORD_RESET,
            token_hash=hmac_hash("test"),
            ttl=timedelta(hours=1),
        )
        token.mark_used()
        assert token.is_used
        assert not token.is_valid

    def test_increment_attempts(self, user):
        token = VerificationToken.create_for_principal(
            principal=user,
            purpose=TokenPurpose.PHONE_VERIFICATION,
            token_hash=hmac_hash("test"),
            otp_hash=hmac_hash("123456"),
            ttl=timedelta(minutes=10),
            max_attempts=3,
        )
        token.increment_attempts()
        assert token.attempt_count == 1
        token.increment_attempts()
        token.increment_attempts()
        assert token.attempts_exceeded
        assert not token.is_valid

    def test_invalidate_existing(self, user):
        VerificationToken.create_for_principal(
            principal=user,
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            token_hash=hmac_hash("old"),
            ttl=timedelta(hours=24),
        )
        # Creating a new one should invalidate the old
        VerificationToken.create_for_principal(
            principal=user,
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            token_hash=hmac_hash("new"),
            ttl=timedelta(hours=24),
        )
        # Only the new one should remain active
        active = VerificationToken.objects.filter(
            principal=user,
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            used_at__isnull=True,
        )
        assert active.count() == 1


@pytest.mark.django_db
class TestLoginAttempt:
    """Tests for LoginAttempt model and managers."""

    def test_create_attempt(self, user):
        attempt = LoginAttempt.objects.create(
            principal=user,
            identifier=user.email,
            result=LoginAttemptResult.SUCCESS,
            auth_method="password",
            ip_address="127.0.0.1",
        )
        assert attempt.pk is not None
        assert attempt.result == LoginAttemptResult.SUCCESS

    def test_failure_count(self, user):
        for _ in range(3):
            LoginAttempt.objects.create(
                principal=user,
                identifier=user.email,
                result=LoginAttemptResult.INVALID_CREDENTIALS,
                ip_address="127.0.0.1",
            )
        count = LoginAttempt.objects.failure_count(user, window_minutes=30)
        assert count == 3

    def test_recent_failures_filter(self, user):
        LoginAttempt.objects.create(
            principal=user,
            identifier=user.email,
            result=LoginAttemptResult.INVALID_CREDENTIALS,
            ip_address="127.0.0.1",
        )
        LoginAttempt.objects.create(
            principal=user,
            identifier=user.email,
            result=LoginAttemptResult.SUCCESS,
            ip_address="127.0.0.1",
        )
        failures = LoginAttempt.objects.recent_failures(user, window_minutes=30)
        assert failures.count() == 1


@pytest.mark.django_db
class TestPasswordHistory:
    """Tests for PasswordHistory model."""

    def test_record_password(self, user):
        entry = PasswordHistory.objects.record(
            principal=user,
            password_hash=make_password("OldPass123!"),
            set_by=PasswordSetMethod.USER_CHANGE,
        )
        assert entry.pk is not None

    def test_check_reuse_detects_match(self, user):
        raw = "TestPass123!"
        PasswordHistory.objects.record(
            principal=user,
            password_hash=make_password(raw),
        )
        assert PasswordHistory.objects.check_reuse(user, raw, count=5) is True

    def test_check_reuse_no_match(self, user):
        PasswordHistory.objects.record(
            principal=user,
            password_hash=make_password("OldPass123!"),
        )
        assert PasswordHistory.objects.check_reuse(user, "NewPass456!", count=5) is False

    def test_prune(self, user):
        for i in range(10):
            PasswordHistory.objects.record(
                principal=user,
                password_hash=make_password(f"Pass{i}!"),
            )
        deleted = PasswordHistory.objects.prune(user, keep=3)
        assert deleted == 7
        assert PasswordHistory.objects.filter(principal=user).count() == 3


@pytest.mark.django_db
class TestMFAPendingAuthentication:
    """Tests for MFAPendingAuthentication model."""

    def test_create_pending(self, user):
        pending = MFAPendingAuthentication.objects.create(
            principal=user,
            token_hash=hmac_hash("mfa_token"),
            auth_method="password",
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        assert pending.is_valid
        assert not pending.is_consumed
        assert not pending.is_expired

    def test_consume(self, user):
        pending = MFAPendingAuthentication.objects.create(
            principal=user,
            token_hash=hmac_hash("mfa_token"),
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        pending.consume()
        assert pending.is_consumed
        assert not pending.is_valid

    def test_expired(self, user):
        pending = MFAPendingAuthentication.objects.create(
            principal=user,
            token_hash=hmac_hash("mfa_token"),
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        assert pending.is_expired
        assert not pending.is_valid

    def test_attempts_exceeded(self, user):
        pending = MFAPendingAuthentication.objects.create(
            principal=user,
            token_hash=hmac_hash("mfa_token"),
            max_attempts=3,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        for _ in range(3):
            pending.increment_attempts()
        assert pending.attempts_exceeded
        assert not pending.is_valid


@pytest.mark.django_db
class TestCredentialModels:
    """Tests for credential models."""

    def test_password_credential(self, user):
        cred = PasswordCredential.objects.create(
            principal=user,
            password_hash=make_password("test"),
            status=CredentialStatus.ACTIVE,
        )
        assert cred.is_usable
        assert cred.check_password("test")
        assert not cred.check_password("wrong")

    def test_credential_revoke(self, user):
        cred = PasswordCredential.objects.create(
            principal=user,
            password_hash=make_password("test"),
            status=CredentialStatus.ACTIVE,
        )
        cred.revoke()
        assert cred.status == CredentialStatus.REVOKED
        assert not cred.is_usable

    def test_totp_credential(self, user):
        cred = TOTPCredential.objects.create(
            principal=user,
            label="Test",
            secret="JBSWY3DPEHPK3PXP",
            status=CredentialStatus.ACTIVE,
        )
        assert cred.is_usable
        cred.mark_used()
        assert cred.last_used_at is not None

    def test_backup_code_verify_and_consume(self, user):
        raw_code = "ABCD1234"
        code = BackupCode.objects.create(
            principal=user,
            code_hash=make_password(raw_code),
            status=CredentialStatus.ACTIVE,
        )
        assert code.verify_and_consume(raw_code) is True
        assert code.is_used
        assert code.status == CredentialStatus.INACTIVE

    def test_backup_code_cannot_reuse(self, user):
        raw_code = "ABCD1234"
        code = BackupCode.objects.create(
            principal=user,
            code_hash=make_password(raw_code),
            status=CredentialStatus.ACTIVE,
        )
        code.verify_and_consume(raw_code)
        assert code.verify_and_consume(raw_code) is False
