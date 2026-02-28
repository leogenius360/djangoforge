"""
Tests for actor tracking middleware and context.
"""

import pytest
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.context import get_current_actor, set_current_actor
from apps.core.middleware import ActorTrackingMiddleware

User = get_user_model()


@pytest.fixture
def user_with_principal(db):
    """Create a test user with principal."""
    user = User.objects.create_user("core-mw-user", "TestPass123!", email="test@example.com")
    return user


@pytest.fixture
def request_factory():
    """Provide Django request factory."""
    return RequestFactory()


@pytest.fixture
def get_response():
    """Mock get_response callable for middleware."""

    def _get_response(request):
        return HttpResponse("OK")

    return _get_response


@pytest.mark.django_db
class TestActorTrackingMiddleware:
    """Tests for ActorTrackingMiddleware."""

    def test_actor_context_set_for_authenticated_user(self, request_factory, get_response, user_with_principal):
        """Test that actor context is set for authenticated users."""
        request = request_factory.get("/")
        request.user = user_with_principal

        middleware = ActorTrackingMiddleware(get_response)

        # Capture baseline actor (may be ambient system actor from conftest)
        baseline_actor = get_current_actor()

        # Call middleware (context is set inside)
        response = middleware(request)

        # After middleware, context should be restored to baseline
        assert response.status_code == 200
        assert get_current_actor() is baseline_actor

    def test_actor_context_not_set_for_anonymous(self, request_factory, get_response):
        """Test that actor context is NOT set for anonymous users."""

        class AnonymousUser:
            is_authenticated = False

        request = request_factory.get("/")
        request.user = AnonymousUser()

        middleware = ActorTrackingMiddleware(get_response)

        baseline_actor = get_current_actor()
        middleware(request)
        assert get_current_actor() is baseline_actor

    def test_actor_context_cleanup_on_exception(self, request_factory, user_with_principal):
        """Test that actor context is cleaned up even on exception."""

        def get_response_with_error(request):
            # Verify context is set during request processing
            assert get_current_actor() is not None
            raise ValueError("Simulated error")

        request = request_factory.get("/")
        request.user = user_with_principal

        middleware = ActorTrackingMiddleware(get_response_with_error)

        baseline_actor = get_current_actor()

        with pytest.raises(ValueError):
            middleware(request)

        # Context should still be restored after exception
        assert get_current_actor() is baseline_actor


@pytest.mark.django_db
class TestActorContext:
    """Tests for actor context management."""

    def test_actor_context_isolated(self, user_with_principal):
        """Test that actor context is properly isolated."""
        principal = user_with_principal

        baseline_actor = get_current_actor()

        # Set actor in context
        with set_current_actor(principal):
            assert get_current_actor() == principal

        # Context restored after exiting
        assert get_current_actor() is baseline_actor

    def test_actor_context_nested(self, db):
        """Test that nested actor contexts work correctly."""
        user1 = User.objects.create_user("core-mw-user1", "Pass123!", email="user1@example.com")
        user2 = User.objects.create_user("core-mw-user2", "Pass123!", email="user2@example.com")

        principal1 = user1
        principal2 = user2

        baseline_actor = get_current_actor()

        with set_current_actor(principal1):
            assert get_current_actor() == principal1

            with set_current_actor(principal2):
                assert get_current_actor() == principal2

            # Back to principal1
            assert get_current_actor() == principal1

        # Fully restored
        assert get_current_actor() is baseline_actor

    def test_actor_context_none(self):
        """Test that setting actor to None works."""
        with set_current_actor(None):
            assert get_current_actor() is None
