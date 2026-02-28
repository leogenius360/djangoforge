"""Tests for core monitoring endpoints and configuration helpers."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.core.config import get_default_lock_duration
from apps.core.monitoring import get_client_ip

User = get_user_model()


class TestMonitoringConfig:
    def test_get_default_lock_duration_default(self, settings):
        settings.CORE_DEFAULT_LOCK_DURATION = timedelta(minutes=30)
        assert get_default_lock_duration() == timedelta(minutes=30)

    def test_get_default_lock_duration_override(self, settings):
        settings.CORE_DEFAULT_LOCK_DURATION = timedelta(hours=2)
        assert get_default_lock_duration() == timedelta(hours=2)


class TestGetClientIP:
    def test_remote_addr_fallback(self):
        request = RequestFactory().get("/", REMOTE_ADDR="9.9.9.9")
        assert get_client_ip(request) == "9.9.9.9"

    def test_remote_addr_preferred_over_xff(self):
        """REMOTE_ADDR is preferred over X-Forwarded-For to prevent IP spoofing."""
        request = RequestFactory().get(
            "/",
            HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8",
            REMOTE_ADDR="9.9.9.9",
        )
        assert get_client_ip(request) == "9.9.9.9"

    def test_xff_fallback_when_no_remote_addr(self):
        """X-Forwarded-For is used as fallback when REMOTE_ADDR is not available."""
        request = RequestFactory().get(
            "/",
            HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8",
        )
        # Clear REMOTE_ADDR (RequestFactory sets it by default)
        request.META.pop("REMOTE_ADDR", None)
        assert get_client_ip(request) == "1.2.3.4"


@pytest.mark.django_db
class TestPrometheusMetricsViewSecurity:
    def test_metrics_denied_by_ip_whitelist(self, settings):
        settings.METRICS_ALLOWED_IPS = ["127.0.0.1"]
        settings.METRICS_REQUIRE_AUTH = False

        client = Client()
        url = reverse("prometheus-metrics")
        response = client.get(url, REMOTE_ADDR="10.0.0.1")

        assert response.status_code == 403

    def test_metrics_allowed_for_whitelisted_ip(self, settings):
        settings.METRICS_ALLOWED_IPS = ["127.0.0.1"]
        settings.METRICS_REQUIRE_AUTH = False

        client = Client()
        url = reverse("prometheus-metrics")
        response = client.get(url, REMOTE_ADDR="127.0.0.1")

        # If prometheus-client isn't installed this is 501, otherwise 200.
        assert response.status_code in {200, 501}

    def test_metrics_denied_when_auth_required(self, settings):
        settings.METRICS_ALLOWED_IPS = []
        settings.METRICS_REQUIRE_AUTH = True

        client = Client()
        url = reverse("prometheus-metrics")
        response = client.get(url, REMOTE_ADDR="127.0.0.1")

        assert response.status_code == 403

    def test_metrics_allows_admin_when_auth_required(self, settings):
        settings.METRICS_ALLOWED_IPS = []
        settings.METRICS_REQUIRE_AUTH = True

        admin = User.objects.create_superuser("core-metrics-admin", "AdminPass123!", email="admin-metrics@example.com")

        client = Client()
        client.force_login(admin)

        url = reverse("prometheus-metrics")
        response = client.get(url, REMOTE_ADDR="127.0.0.1")

        assert response.status_code in {200, 501}
