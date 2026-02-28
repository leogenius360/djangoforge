"""
Tests for Forge middleware.
"""

from django.http import HttpResponse
from django.test import RequestFactory

from djangoforge.middleware.correlation import CorrelationIdMiddleware
from djangoforge.middleware.security_headers import SecurityHeadersMiddleware


class TestCorrelationIdMiddleware:
    def _make_middleware(self, response=None):
        def get_response(request):
            return response or HttpResponse("ok")

        return CorrelationIdMiddleware(get_response)

    def test_generates_correlation_id(self):
        mw = self._make_middleware()
        request = RequestFactory().get("/")
        response = mw(request)
        cid = response["X-Correlation-Id"]
        assert cid
        assert len(cid) == 32  # uuid4 hex

    def test_preserves_incoming_id(self):
        mw = self._make_middleware()
        request = RequestFactory().get("/", HTTP_X_CORRELATION_ID="existing-cid")
        response = mw(request)
        assert response["X-Correlation-Id"] == "existing-cid"


class TestSecurityHeadersMiddleware:
    def _make_middleware(self, response=None):
        def get_response(request):
            return response or HttpResponse("ok")

        return SecurityHeadersMiddleware(get_response)

    def test_adds_security_headers(self):
        mw = self._make_middleware()
        request = RequestFactory().get("/")
        response = mw(request)
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["X-Frame-Options"] == "DENY"
        assert response["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert response["X-XSS-Protection"] == "1; mode=block"
