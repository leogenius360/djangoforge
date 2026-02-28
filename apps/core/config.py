from __future__ import annotations

from datetime import timedelta

from django.conf import settings


def get_default_lock_duration() -> timedelta:
    """
    Return the default lock duration for lifecycle locks.

    Setting:
        CORE_DEFAULT_LOCK_DURATION (timedelta), default 30 minutes.
    """
    return getattr(settings, "CORE_DEFAULT_LOCK_DURATION", timedelta(minutes=30))


def get_metrics_allowed_ips() -> list[str]:
    """
    Return the allowlist of IPs allowed to access metrics endpoint.

    Setting:
        METRICS_ALLOWED_IPS (list[str]), default [].

    Note:
        An empty list means no restriction (typically not recommended in production).
    """
    return list(getattr(settings, "METRICS_ALLOWED_IPS", []))


def get_metrics_require_auth() -> bool:
    """
    Return whether the metrics endpoint requires authentication.

    Setting:
        METRICS_REQUIRE_AUTH (bool), default False.
    """
    return bool(getattr(settings, "METRICS_REQUIRE_AUTH", False))


def get_system_principal_id() -> str | None:
    """
    Return the configured system Principal ID used for automated flows.

    Setting:
        CORE_SYSTEM_PRINCIPAL_ID (str/uuid), default None.
    """
    value = getattr(settings, "CORE_SYSTEM_PRINCIPAL_ID", None)
    return str(value) if value else None


def get_enforce_actor() -> bool:
    """
    Return whether actor attribution must be present when actor fields exist.

    Setting:
        CORE_ENFORCE_ACTOR (bool), default False.
    """
    return bool(getattr(settings, "CORE_ENFORCE_ACTOR", False))


__all__ = [
    "get_default_lock_duration",
    "get_metrics_allowed_ips",
    "get_metrics_require_auth",
    "get_enforce_actor",
    "get_system_principal_id",
]
