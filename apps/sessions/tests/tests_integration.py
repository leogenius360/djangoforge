"""
Tests for session authentication and tracking.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.authn.services.authentication import AuthenticationService
from apps.sessions.authentication import DualAuthentication, SessionAuthentication
from apps.sessions.models import AuthenticationMethod, AuthSession

User = get_user_model()


@pytest.mark.django_db
class TestSessionCreation:
    """Test session creation during authentication."""

    def test_email_backend_creates_session(self):
        """Test that AuthenticationService creates a session on successful password auth."""
        # Create user
        User.objects.create_user(
            "sess_email_auth",
            "testpass123",
            email="sess_email_auth@example.com",
        )

        # Create request
        factory = RequestFactory()
        request = factory.post("/login/")
        request.session = {}

        # Authenticate via AuthenticationService (which creates sessions)
        result = AuthenticationService.authenticate_with_password(
            request=request,
            identifier="sess_email_auth@example.com",
            password="testpass123",
        )

        # Verify authentication succeeded
        assert result.principal is not None

        # Verify session was created
        sessions = AuthSession.objects.for_principal(result.principal)
        assert sessions.count() == 1

        session = sessions.first()
        assert session.is_active
        assert session.metadata.get("auth_method") == AuthenticationMethod.PASSWORD

    def test_session_stored_in_django_session(self):
        """Test that session ID is stored in Django session after AuthenticationService auth."""
        User.objects.create_user(
            "sess_stored",
            "testpass123",
            email="sess_stored@example.com",
        )

        factory = RequestFactory()
        request = factory.post("/login/")
        request.session = {}  # Mock session

        # Authenticate via AuthenticationService
        AuthenticationService.authenticate_with_password(
            request=request,
            identifier="sess_stored@example.com",
            password="testpass123",
        )

        # Verify session ID stored
        assert "user_session_id" in request.session


@pytest.mark.django_db
class TestDualAuthentication:
    """Test dual authentication class."""

    def test_session_authentication(self):
        """Test cookie-based session authentication."""
        # Create user and session
        user = User.objects.create_user(
            "sess_cookie",
            "testpass123",
            email="sess_cookie@example.com",
        )

        session = AuthSession.create_session(
            principal=user,
            auth_method=AuthenticationMethod.PASSWORD,
            require_mfa=False,
        )

        # Create request with session
        factory = RequestFactory()
        request = factory.get("/api/test/")
        request.session = {"user_session_id": str(session.pk)}

        # Authenticate
        auth = SessionAuthentication()
        result = auth.authenticate(request)

        assert result is not None
        authenticated_user, auth_session = result
        assert authenticated_user == user
        assert auth_session == session

    def test_dual_authentication_fallback(self):
        """Test that DualAuthentication tries multiple methods."""
        user = User.objects.create_user(
            "sess_dual",
            "testpass123",
            email="sess_dual@example.com",
        )

        session = AuthSession.create_session(
            principal=user,
            auth_method=AuthenticationMethod.PASSWORD,
            require_mfa=False,
        )

        # Create request with session
        factory = RequestFactory()
        request = factory.get("/api/test/")
        request.session = {"user_session_id": str(session.pk)}

        # Authenticate with DualAuthentication
        auth = DualAuthentication()
        result = auth.authenticate(request)

        assert result is not None
        authenticated_user, _ = result
        assert authenticated_user == user


@pytest.mark.django_db
class TestSessionTracking:
    """Test session activity tracking."""

    def test_session_activity_update(self):
        """Test that session activity is updated."""
        user = User.objects.create_user(
            "sess_tracking",
            "testpass123",
            email="sess_tracking@example.com",
        )

        session = AuthSession.create_session(
            principal=user,
            auth_method=AuthenticationMethod.PASSWORD,
            require_mfa=False,
        )

        # Update activity
        session.touch_activity(ip_address="1.2.3.4", path="/api/users/")

        # Reload and verify
        session.refresh_from_db()
        assert session.ip_last == "1.2.3.4"
        assert session.metadata.get("last_path") == "/api/users/"
        assert session.last_seen_at is not None
