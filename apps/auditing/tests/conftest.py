"""
Pytest fixtures for auditing app tests.
"""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user("aud_testuser", "testpass123", email="aud_testuser@example.com")


@pytest.fixture
def user_factory(db):
    """Factory to create test users."""
    _counter = [0]

    def _create_user(**kwargs):
        _counter[0] += 1
        idx = _counter[0]
        username = kwargs.pop("username", f"aud_user{idx}")
        password = kwargs.pop("password", "testpass123")
        defaults = {
            "email": f"aud_user{idx}@example.com",
        }
        defaults.update(kwargs)
        return User.objects.create_user(username, password, **defaults)

    return _create_user


@pytest.fixture
def process_audit_outbox():
    """Mock fixture for outbox processing."""
    return lambda: None
