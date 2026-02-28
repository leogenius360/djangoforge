"""
Health check utilities for monitoring and operational readiness.

Provides reusable health check functions for database, cache, and system components.
"""

from django.core.cache import cache
from django.db import connection


class HealthChecker:
    """Centralized health checking for application components."""

    @staticmethod
    def check_database() -> tuple[bool, str | None]:
        """
        Check database connectivity.

        Returns
        -------
        tuple[bool, str | None]
            (is_healthy, error_detail). error_detail is None if healthy.
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            return True, None
        except Exception as exc:  # pragma: no cover - backend-specific
            return False, str(exc)

    @staticmethod
    def check_cache(test_key: str = "health_check") -> tuple[bool, str | None]:
        """
        Check cache connectivity and basic operations.

        Parameters
        ----------
        test_key : str
            Key to use for testing cache operations (default: "health_check").

        Returns
        -------
        tuple[bool, str | None]
            (is_healthy, error_detail). error_detail is None if healthy.
        """
        try:
            cache.set(test_key, "ok", 10)
            if cache.get(test_key) == "ok":
                return True, None
            return False, "unable to retrieve test value"
        except Exception as exc:  # pragma: no cover - backend-specific
            return False, str(exc)


__all__ = ["HealthChecker"]
