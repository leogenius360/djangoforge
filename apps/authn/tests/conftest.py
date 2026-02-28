"""Shared fixtures for authn tests."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient as DRFAPIClient

User = get_user_model()


@pytest.fixture
def api_client():
    """DRF API test client."""
    return DRFAPIClient()


@pytest.fixture
def user(db):
    """Create a basic test user with principal."""
    return User.objects.create_user(
        email="test@example.com",
        password="TestPass123!",
        username="testuser",
    )


@pytest.fixture
def user_with_verified_email(db):
    """Create a user with verified email."""
    return User.objects.create_user(
        email="verified@example.com",
        password="TestPass123!",
        username="verifieduser",
        email_verified_at=timezone.now(),
    )


@pytest.fixture
def user_with_mfa(user):
    """Create a user with active TOTP credential."""
    import pyotp

    from apps.authn.models import CredentialStatus, TOTPCredential

    secret = pyotp.random_base32()
    TOTPCredential.objects.create(
        principal=user,
        label="Test MFA",
        secret=secret,
        algorithm="SHA1",
        digits=6,
        period=30,
        status=CredentialStatus.ACTIVE,
    )
    user._test_totp_secret = secret
    return user


@pytest.fixture
def user_factory(db):
    """Factory to create test users with unique defaults."""
    counter = 0

    def _create_user(**kwargs):
        nonlocal counter
        counter += 1
        defaults = {
            "email": f"user{counter}@example.com",
            "password": "TestPass123!",
            "username": f"user{counter}",
        }
        defaults.update(kwargs)
        return User.objects.create_user(**defaults)

    return _create_user


@pytest.fixture
def authenticated_client(api_client, user_with_verified_email):
    """Return API client authenticated as a verified user."""
    api_client.force_authenticate(user=user_with_verified_email)
    return api_client, user_with_verified_email


@pytest.fixture
def mock_request(rf):
    """Create a mock HTTP request."""
    request = rf.post("/fake/")
    request.META["HTTP_USER_AGENT"] = "TestAgent/1.0"
    request.META["REMOTE_ADDR"] = "127.0.0.1"
    return request
