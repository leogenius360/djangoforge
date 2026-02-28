"""
API URL configuration.
"""

from django.urls import include, path

from apps.core.api.views import (
    HealthCheckView,
    LivenessProbeView,
    ReadinessProbeView,
    StartupProbeView,
)
from apps.core.monitoring import SystemMetricsView

urlpatterns = [
    # Health check endpoints
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("health/live/", LivenessProbeView.as_view(), name="liveness-probe"),
    path("health/ready/", ReadinessProbeView.as_view(), name="readiness-probe"),
    path("health/startup/", StartupProbeView.as_view(), name="startup-probe"),
    # Monitoring endpoints
    path("metrics/", SystemMetricsView.as_view(), name="system-metrics"),
    # Authentication endpoints (authn app)
    path("auth/", include("apps.authn.api.urls")),
    # Session management endpoints (sessions app)
    path("sessions/", include("apps.sessions.api.urls")),
    # Accounts endpoints (profile, verification, principals)
    path("accounts/", include("apps.accounts.api.urls")),
    # Authorization endpoints (authz app)
    path("authz/", include("apps.authz.api.urls")),
    # Audit log endpoints (auditing app)
    path("audit/", include("apps.auditing.api.urls")),
]
