"""
Tests for Forge DRF adapter.
"""

from django.test import RequestFactory
from rest_framework.exceptions import NotFound, ValidationError

from djangoforge.adapters.drf.authentication import ForgeAuthentication
from djangoforge.adapters.drf.exception_handler import forge_exception_handler


class TestForgeAuthentication:
    def test_authenticate_from_headers(self):
        auth = ForgeAuthentication()
        request = RequestFactory().get("/", HTTP_X_USER_ID="u-1", HTTP_X_EMAIL="a@b.com")
        # DRF wraps Django request, simulate by passing the raw request
        from rest_framework.request import Request

        drf_request = Request(request)
        result = auth.authenticate(drf_request)
        assert result is not None
        user, _ = result
        assert user.is_authenticated
        assert user.pk == "u-1"

    def test_returns_none_without_headers(self):
        auth = ForgeAuthentication()
        request = RequestFactory().get("/")
        from rest_framework.request import Request

        drf_request = Request(request)
        assert auth.authenticate(drf_request) is None


class TestForgeExceptionHandler:
    def test_not_found(self):
        exc = NotFound("missing")
        response = forge_exception_handler(exc, {})
        assert response is not None
        assert response.status_code == 404
        assert response.data["status"] == 404
        assert response.data["type"] == "about:blank"

    def test_validation_error(self):
        exc = ValidationError({"field": ["required"]})
        response = forge_exception_handler(exc, {})
        assert response is not None
        assert response.status_code == 400
