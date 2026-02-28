"""
Core app views.
"""

from datetime import UTC, datetime

from django.conf import settings

from apps.core.api import status
from apps.core.api.base import ForgeAPIView as APIView
from apps.core.api.base import Response
from apps.core.api.decorators import extend_schema
from apps.core.api.permissions import AllowAny
from apps.core.health import HealthChecker


def _can_show_operational_details(request) -> bool:
    """Return True if this request is allowed to see verbose operational details."""
    if settings.DEBUG:
        return True
    user = getattr(request, "user", None)
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False))


class HealthCheckView(APIView):
    """
    Comprehensive health check endpoint for monitoring and load balancers.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Health Check",
        description="Returns comprehensive health status including database, cache, and system info.",
        responses={200: {"description": "Application is healthy"}},
    )
    def get(self, request):
        """
        Check application health including database, cache, and system metrics.
        """
        show_details = _can_show_operational_details(request)

        health_status = {
            "status": "healthy",
            "timestamp": datetime.now(UTC).isoformat(),
            "database": "unknown",
            "cache": "unknown",
        }

        # Check database connection
        db_ok, db_error = HealthChecker.check_database()
        if db_ok:
            health_status["database"] = "connected"
        else:
            health_status["database"] = "error"
            if show_details:
                health_status["database_error"] = db_error
            health_status["status"] = "unhealthy"

        # Check cache connection
        cache_ok, cache_error = HealthChecker.check_cache("health_check")
        if cache_ok:
            health_status["cache"] = "connected"
        else:
            health_status["cache"] = "error"
            if show_details:
                health_status["cache_error"] = cache_error
            health_status["status"] = "unhealthy"

        status_code = (
            status.HTTP_200_OK if health_status["status"] == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
        )

        return Response(health_status, status=status_code)


class LivenessProbeView(APIView):
    """
    Kubernetes liveness probe endpoint.
    Returns 200 if application is alive and running.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Liveness Probe",
        description="Kubernetes liveness probe - checks if application is alive.",
        responses={200: {"description": "Application is alive"}},
    )
    def get(self, request):
        """Simple liveness check - always returns OK if app is running."""
        return Response({"status": "alive"}, status=status.HTTP_200_OK)


class ReadinessProbeView(APIView):
    """
    Kubernetes readiness probe endpoint.
    Returns 200 if application is ready to serve traffic.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Readiness Probe",
        description="Kubernetes readiness probe - checks if application can serve traffic.",
        responses={200: {"description": "Application is ready"}},
    )
    def get(self, request):
        """
        Check if application is ready to serve traffic.
        Verifies database and cache connectivity.
        """
        is_ready = True

        # Check database
        db_ok, _ = HealthChecker.check_database()
        if not db_ok:
            is_ready = False

        # Check cache
        cache_ok, _ = HealthChecker.check_cache("readiness_check")
        if not cache_ok:
            is_ready = False

        if is_ready:
            return Response({"status": "ready"}, status=status.HTTP_200_OK)
        return Response({"status": "not_ready"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class StartupProbeView(APIView):
    """
    Kubernetes startup probe endpoint.
    Returns 200 when application has fully started.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Startup Probe",
        description="Kubernetes startup probe - checks if application has completed startup.",
        responses={200: {"description": "Application has started"}},
    )
    def get(self, request):
        """
        Check if application has completed startup.
        Verifies all critical services are available.
        """
        startup_complete = True

        # Check database
        db_ok, _ = HealthChecker.check_database()
        if not db_ok:
            startup_complete = False

        # Check cache
        cache_ok, _ = HealthChecker.check_cache("startup_check")
        if not cache_ok:
            startup_complete = False

        if startup_complete:
            return Response({"status": "started"}, status=status.HTTP_200_OK)
        return Response({"status": "starting"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
