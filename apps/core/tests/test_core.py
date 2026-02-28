"""
Tests for core app.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.core.api import status

User = get_user_model()


@pytest.mark.django_db
class TestHealthCheckView:
    """Tests for health check endpoint."""

    def test_health_check_success(self):
        """Test health check returns successful response."""
        client = Client()
        url = reverse("health-check")
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
        assert "database" in data
        assert "cache" in data

    def test_health_check_unhealthy_hides_details_by_default(self, settings, monkeypatch):
        """When not DEBUG and not admin, error details should be omitted."""
        settings.DEBUG = False
        from apps.core.api import views as core_views

        monkeypatch.setattr(core_views.HealthChecker, "check_database", lambda: (False, "db down"))
        monkeypatch.setattr(core_views.HealthChecker, "check_cache", lambda _key=None: (False, "cache down"))

        client = Client()
        url = reverse("health-check")
        response = client.get(url)

        data = response.json()
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert data["status"] == "unhealthy"
        assert data["database"] == "error"
        assert data["cache"] == "error"
        assert "database_error" not in data
        assert "cache_error" not in data

    def test_health_check_unhealthy_shows_details_for_admin(self, settings, monkeypatch):
        """When not DEBUG but admin, error details should be included."""
        settings.DEBUG = False
        from apps.core.api import views as core_views

        monkeypatch.setattr(core_views.HealthChecker, "check_database", lambda: (False, "db down"))
        monkeypatch.setattr(core_views.HealthChecker, "check_cache", lambda _key=None: (False, "cache down"))

        client = Client()
        admin = User.objects.create_superuser("core-admin-2", "AdminPass123!", email="admin2@example.com")
        client.force_login(admin)

        url = reverse("health-check")
        response = client.get(url)

        data = response.json()
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert data["status"] == "unhealthy"
        assert data["database_error"] == "db down"
        assert data["cache_error"] == "cache down"


@pytest.mark.django_db
class TestKubernetesProbeViews:
    def test_liveness_probe(self):
        client = Client()
        url = reverse("liveness-probe")
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "alive"}

    def test_readiness_probe_ready(self, monkeypatch):
        from apps.core.api import views as core_views

        monkeypatch.setattr(core_views.HealthChecker, "check_database", lambda: (True, None))
        monkeypatch.setattr(core_views.HealthChecker, "check_cache", lambda _key=None: (True, None))

        client = Client()
        url = reverse("readiness-probe")
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ready"}

    def test_readiness_probe_not_ready(self, monkeypatch):
        from apps.core.api import views as core_views

        monkeypatch.setattr(core_views.HealthChecker, "check_database", lambda: (False, "db down"))
        monkeypatch.setattr(core_views.HealthChecker, "check_cache", lambda _key=None: (True, None))

        client = Client()
        url = reverse("readiness-probe")
        response = client.get(url)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.json() == {"status": "not_ready"}

    def test_startup_probe_started(self, monkeypatch):
        from apps.core.api import views as core_views

        monkeypatch.setattr(core_views.HealthChecker, "check_database", lambda: (True, None))
        monkeypatch.setattr(core_views.HealthChecker, "check_cache", lambda _key=None: (True, None))

        client = Client()
        url = reverse("startup-probe")
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "started"}

    def test_startup_probe_starting(self, monkeypatch):
        from apps.core.api import views as core_views

        monkeypatch.setattr(core_views.HealthChecker, "check_database", lambda: (True, None))
        monkeypatch.setattr(core_views.HealthChecker, "check_cache", lambda _key=None: (False, "cache down"))

        client = Client()
        url = reverse("startup-probe")
        response = client.get(url)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.json() == {"status": "starting"}


@pytest.mark.django_db
class TestSystemMetricsView:
    """Security tests for the system metrics endpoint."""

    def test_system_metrics_requires_admin(self):
        client = Client()
        url = reverse("system-metrics")
        response = client.get(url)
        assert response.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}

    def test_system_metrics_allows_admin(self):
        client = Client()
        admin = User.objects.create_superuser("core-admin-1", "AdminPass123!", email="admin@example.com")
        client.force_login(admin)

        url = reverse("system-metrics")
        response = client.get(url)

        assert response.status_code in {status.HTTP_200_OK, status.HTTP_501_NOT_IMPLEMENTED}
