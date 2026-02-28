"""
Monitoring and metrics views for Prometheus integration.
"""

import ipaddress

from django.conf import settings
from django.db import connection
from django.http import HttpResponse, HttpResponseForbidden
from django.views import View

from apps.core.api import status
from apps.core.api.base import ForgeAPIView as APIView
from apps.core.api.base import Response
from apps.core.api.decorators import extend_schema
from apps.core.api.permissions import IsAdminUser
from apps.core.config import get_metrics_allowed_ips, get_metrics_require_auth

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


if PROMETHEUS_AVAILABLE:
    # Define metrics
    http_requests_total = Counter(
        "django_http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
    )

    http_request_duration_seconds = Histogram(
        "django_http_request_duration_seconds",
        "HTTP request latency",
        ["method", "endpoint"],
    )

    db_connections = Gauge(
        "django_db_connections",
        "Number of database connections",
        ["state"],
    )

    cache_operations = Counter(
        "django_cache_operations_total",
        "Total cache operations",
        ["operation", "result"],
    )


def get_client_ip(request) -> str:
    """
    Extract client IP address from request.

    Prefers REMOTE_ADDR (set by the web server) over X-Forwarded-For to
    prevent IP spoofing.  X-Forwarded-For is only used as a fallback when
    REMOTE_ADDR is not available.

    Parameters
    ----------
    request
        Django HttpRequest object

    Returns
    -------
    str
        Client IP address
    """
    remote_addr = request.META.get("REMOTE_ADDR", "")
    if remote_addr:
        return remote_addr

    # Fallback: use X-Forwarded-For only when REMOTE_ADDR is unavailable
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    return "unknown"


def _is_ip_allowed(client_ip: str, allowed_ips: list[str]) -> bool:
    """Check if a client IP matches the allowed IPs list (supports CIDR notation)."""
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for entry in allowed_ips:
        try:
            if "/" in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            else:
                if addr == ipaddress.ip_address(entry):
                    return True
        except ValueError:
            continue
    return False


class MetricsView(View):
    """
    Prometheus metrics endpoint with IP whitelist and optional authentication.

    Exposes application metrics in Prometheus format with built-in security controls.

    Security is enforced through:
    1. IP whitelist (configured via CORE_METRICS_ALLOWED_IPS setting)
    2. Optional authentication (configured via CORE_METRICS_REQUIRE_AUTH setting)

    Configuration
    -------------
    Set in Django settings:

        CORE = {
            "METRICS_ALLOWED_IPS": ["127.0.0.1", "10.0.0.0/8"],  # CIDR notation supported
            "METRICS_REQUIRE_AUTH": False,  # Set True to require authentication
        }

    For additional security in production:
    - Use network-level restrictions (firewall, VPC)
    - Deploy on a separate internal port
    - Use reverse proxy authentication (nginx auth_basic)
    """

    def dispatch(self, request, *args, **kwargs):
        """Check IP whitelist and authentication before processing request."""
        # Check IP whitelist
        allowed_ips = get_metrics_allowed_ips()
        if allowed_ips:
            client_ip = get_client_ip(request)
            if not _is_ip_allowed(client_ip, allowed_ips):
                return HttpResponseForbidden("Access denied: IP not whitelisted")

        # Check authentication if required
        if get_metrics_require_auth() and (not request.user.is_authenticated or not request.user.is_staff):
            return HttpResponseForbidden("Access denied: Authentication required")

        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        """Return metrics in Prometheus format."""
        if not PROMETHEUS_AVAILABLE:
            return HttpResponse(
                "Prometheus client not installed",
                status=501,
                content_type="text/plain",
            )

        # Update database connection metrics
        try:
            with connection.cursor() as cursor:
                # PostgreSQL specific query for connection stats
                cursor.execute(
                    """
                    SELECT state, count(*)
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                    GROUP BY state
                """
                )
                for state, count in cursor.fetchall():
                    db_connections.labels(state=state or "unknown").set(count)
        except Exception:
            # If query fails (e.g., not PostgreSQL), skip
            pass

        # Generate metrics
        metrics = generate_latest()
        return HttpResponse(metrics, content_type=CONTENT_TYPE_LATEST)


class SystemMetricsView(APIView):
    """
    System metrics endpoint for monitoring dashboards.
    Returns JSON format metrics.
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="System Metrics",
        description="Returns JSON system/application/database/cache metrics for dashboards.",
        responses={200: {"description": "System metrics"}},
    )
    def get(self, request):
        """Return system metrics in JSON format."""
        import os

        try:
            import psutil
        except ImportError:
            return Response(
                {"detail": "psutil is not installed"},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        try:
            from django.core.cache import cache
        except Exception:
            cache = None

        disk_path = os.path.abspath(os.sep)

        metrics = {
            "system": {
                "cpu_percent": psutil.cpu_percent(interval=None),
                "memory": {
                    "total": psutil.virtual_memory().total,
                    "available": psutil.virtual_memory().available,
                    "percent": psutil.virtual_memory().percent,
                },
                "disk": {
                    "path": disk_path,
                    "total": psutil.disk_usage(disk_path).total,
                    "used": psutil.disk_usage(disk_path).used,
                    "percent": psutil.disk_usage(disk_path).percent,
                },
            },
            "application": {
                "pid": os.getpid(),
                "threads": psutil.Process().num_threads(),
            },
        }

        # Database metrics
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
                db_connections_count = cursor.fetchone()[0]
                metrics["database"] = {
                    "connections": db_connections_count,
                    "backend": connection.settings_dict.get("ENGINE", "unknown"),
                }
        except Exception as e:
            metrics["database"] = {"error": "unavailable"}
            if settings.DEBUG:
                metrics["database"]["detail"] = str(e)

        # Cache metrics
        try:
            if cache is None:
                raise RuntimeError("cache backend unavailable")

            cache.set("metrics_test", "ok", 1)
            cache_working = cache.get("metrics_test") == "ok"
            metrics["cache"] = {
                "status": "healthy" if cache_working else "unhealthy",
                "backend": settings.CACHES["default"]["BACKEND"],
            }
        except Exception as e:
            metrics["cache"] = {"status": "error", "error": "unavailable"}
            if settings.DEBUG:
                metrics["cache"]["detail"] = str(e)

        return Response(metrics, status=status.HTTP_200_OK)
