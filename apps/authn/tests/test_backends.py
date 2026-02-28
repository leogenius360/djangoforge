"""Tests for authn authentication backends."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings

from apps.authn.backends.email import EmailBackend
from apps.authn.backends.passwordless import PasswordlessBackend
from apps.authn.backends.phone import PhoneBackend
from apps.authn.backends.username import UsernameBackend
from apps.authn.models import TokenPurpose

User = get_user_model()


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def request_obj(rf):
    return rf.post("/fake/")


# ── EmailBackend ────────────────────────────────────────────────────


@pytest.mark.django_db
class TestEmailBackend:
    """Tests for EmailBackend."""

    def test_authenticate_valid(self, user, request_obj):
        backend = EmailBackend()
        result = backend.authenticate(request_obj, email=user.email, password="TestPass123!")
        assert result == user

    def test_authenticate_wrong_password(self, user, request_obj):
        backend = EmailBackend()
        result = backend.authenticate(request_obj, email=user.email, password="WrongPass!")
        assert result is None

    def test_authenticate_nonexistent_email(self, request_obj):
        backend = EmailBackend()
        result = backend.authenticate(request_obj, email="nobody@example.com", password="TestPass123!")
        assert result is None

    def test_authenticate_none_email(self, request_obj):
        backend = EmailBackend()
        result = backend.authenticate(request_obj, email=None, password="pass")
        assert result is None

    def test_authenticate_none_password(self, user, request_obj):
        backend = EmailBackend()
        result = backend.authenticate(request_obj, email=user.email, password=None)
        assert result is None

    def test_authenticate_falls_back_to_username_kwarg(self, user, request_obj):
        backend = EmailBackend()
        result = backend.authenticate(request_obj, username=user.email, password="TestPass123!")
        assert result == user

    def test_authenticate_case_insensitive_email(self, user, request_obj):
        backend = EmailBackend()
        result = backend.authenticate(request_obj, email=user.email.upper(), password="TestPass123!")
        assert result == user

    def test_authenticate_locked_user(self, user, request_obj):
        user.lock()

        backend = EmailBackend()
        result = backend.authenticate(request_obj, email=user.email, password="TestPass123!")
        assert result is None

    def test_authenticate_inactive_user(self, user, request_obj):
        user.disable(actor=user)

        backend = EmailBackend()
        result = backend.authenticate(request_obj, email=user.email, password="TestPass123!")
        assert result is None


# ── UsernameBackend ─────────────────────────────────────────────────


@pytest.mark.django_db
class TestUsernameBackend:
    """Tests for UsernameBackend."""

    def test_authenticate_valid(self, user, request_obj):
        backend = UsernameBackend()
        result = backend.authenticate(request_obj, username=user.username, password="TestPass123!")
        assert result == user

    def test_authenticate_wrong_password(self, user, request_obj):
        backend = UsernameBackend()
        result = backend.authenticate(request_obj, username=user.username, password="WrongPass!")
        assert result is None

    def test_authenticate_nonexistent_username(self, request_obj):
        backend = UsernameBackend()
        result = backend.authenticate(request_obj, username="nobody", password="TestPass123!")
        assert result is None

    def test_authenticate_none_username(self, request_obj):
        backend = UsernameBackend()
        result = backend.authenticate(request_obj, username=None, password="pass")
        assert result is None

    def test_authenticate_none_password(self, user, request_obj):
        backend = UsernameBackend()
        result = backend.authenticate(request_obj, username=user.username, password=None)
        assert result is None

    def test_authenticate_case_insensitive(self, user, request_obj):
        backend = UsernameBackend()
        result = backend.authenticate(request_obj, username=user.username.upper(), password="TestPass123!")
        assert result == user

    def test_authenticate_locked_user(self, user, request_obj):
        user.lock()

        backend = UsernameBackend()
        result = backend.authenticate(request_obj, username=user.username, password="TestPass123!")
        assert result is None


# ── PhoneBackend ────────────────────────────────────────────────────


@pytest.mark.django_db
class TestPhoneBackend:
    """Tests for PhoneBackend."""

    @pytest.fixture
    def phone_user(self, db):
        from django.utils import timezone

        return User.objects.create_user(
            email="phone@example.com",
            password="TestPass123!",
            username="phoneuser",
            phone_number="+1234567890",
            phone_verified_at=timezone.now(),
        )

    def test_authenticate_valid(self, phone_user, request_obj):
        backend = PhoneBackend()
        result = backend.authenticate(
            request_obj,
            phone_number=phone_user.phone_number,
            password="TestPass123!",
        )
        assert result == phone_user

    def test_authenticate_unverified_phone(self, db, request_obj):
        unverified = User.objects.create_user(
            email="unverified_phone@example.com",
            password="TestPass123!",
            username="unverifiedphone",
            phone_number="+9876543210",
        )
        backend = PhoneBackend()
        result = backend.authenticate(
            request_obj,
            phone_number=unverified.phone_number,
            password="TestPass123!",
        )
        assert result is None

    def test_authenticate_wrong_password(self, phone_user, request_obj):
        backend = PhoneBackend()
        result = backend.authenticate(
            request_obj,
            phone_number=phone_user.phone_number,
            password="WrongPass!",
        )
        assert result is None

    def test_authenticate_nonexistent_phone(self, request_obj):
        backend = PhoneBackend()
        result = backend.authenticate(request_obj, phone_number="+0000000000", password="TestPass123!")
        assert result is None

    def test_authenticate_none_phone(self, request_obj):
        backend = PhoneBackend()
        result = backend.authenticate(request_obj, phone_number=None, password="pass")
        assert result is None

    def test_authenticate_falls_back_to_username_kwarg(self, phone_user, request_obj):
        backend = PhoneBackend()
        result = backend.authenticate(
            request_obj,
            username=phone_user.phone_number,
            password="TestPass123!",
        )
        assert result == phone_user


# ── PasswordlessBackend ─────────────────────────────────────────────


@pytest.mark.django_db
class TestPasswordlessBackend:
    """Tests for PasswordlessBackend."""

    @pytest.fixture
    def passwordless_user(self, db):
        return User.objects.create_user(
            email="passwordless@example.com",
            password="TestPass123!",
            username="passwordlessuser",
            passwordless_enabled=True,
        )

    def test_authenticate_valid_token(self, passwordless_user, request_obj):
        from apps.authn.services.token import TokenService

        result = TokenService.create_token(
            principal=passwordless_user,
            purpose=TokenPurpose.PASSWORDLESS_LOGIN,
            ttl_minutes=10,
        )

        backend = PasswordlessBackend()
        auth_result = backend.authenticate(request_obj, token=result.raw_token)
        assert auth_result == passwordless_user

    def test_authenticate_invalid_token(self, request_obj):
        backend = PasswordlessBackend()
        result = backend.authenticate(request_obj, token="invalid_token_xyz")
        assert result is None

    def test_authenticate_none_token(self, request_obj):
        backend = PasswordlessBackend()
        result = backend.authenticate(request_obj, token=None)
        assert result is None

    def test_authenticate_passwordless_disabled(self, user, request_obj):
        """User without passwordless_enabled should fail."""
        from apps.authn.services.token import TokenService

        result = TokenService.create_token(
            principal=user,
            purpose=TokenPurpose.PASSWORDLESS_LOGIN,
            ttl_minutes=10,
        )

        backend = PasswordlessBackend()
        auth_result = backend.authenticate(request_obj, token=result.raw_token)
        assert auth_result is None

    def test_token_consumed_after_auth(self, passwordless_user, request_obj):
        from apps.authn.services.token import TokenService

        result = TokenService.create_token(
            principal=passwordless_user,
            purpose=TokenPurpose.PASSWORDLESS_LOGIN,
            ttl_minutes=10,
        )

        backend = PasswordlessBackend()
        backend.authenticate(request_obj, token=result.raw_token)

        # Second use should fail -- token is consumed
        second_result = backend.authenticate(request_obj, token=result.raw_token)
        assert second_result is None


# ── BaseAccountsBackend ─────────────────────────────────────────────


@pytest.mark.django_db
class TestBaseAccountsBackend:
    """Tests for base backend shared functionality."""

    def test_user_can_authenticate_active(self, user):
        from apps.authn.backends.base import BaseAccountsBackend

        backend = BaseAccountsBackend()
        assert backend.user_can_authenticate(user) is True

    def test_user_can_authenticate_inactive(self, user):
        from apps.authn.backends.base import BaseAccountsBackend

        user.is_active = False
        backend = BaseAccountsBackend()
        assert backend.user_can_authenticate(user) is False

    def test_user_can_authenticate_locked(self, user):
        from apps.authn.backends.base import BaseAccountsBackend

        user.lock()
        backend = BaseAccountsBackend()
        assert backend.user_can_authenticate(user) is False

    @override_settings(AUTHN={"CONSTANT_TIME_BACKEND_RESPONSES": True})
    def test_prevent_timing_attack_runs_hasher(self):
        from apps.authn.backends.base import BaseAccountsBackend

        backend = BaseAccountsBackend()
        # Should not raise -- just runs hasher as timing pad
        backend._prevent_timing_attack("some_password")

    @override_settings(AUTHN={"CONSTANT_TIME_BACKEND_RESPONSES": False})
    def test_prevent_timing_attack_skipped_when_disabled(self):
        from apps.authn.backends.base import BaseAccountsBackend

        backend = BaseAccountsBackend()
        # Should return immediately
        backend._prevent_timing_attack("some_password")
