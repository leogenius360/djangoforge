"""
Lockout service -- account lockout management using LoginAttempt model.

Supports progressive lockout: each successive lockout doubles duration
up to ``PROGRESSIVE_LOCKOUT_MAX_MINUTES``.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from apps.authn.exceptions import AccountLockedError
from apps.authn.models import LoginAttempt, LoginAttemptResult
from apps.authn.settings import authn_settings

if TYPE_CHECKING:
    from django.http import HttpRequest

logger = logging.getLogger(__name__)


class LockoutService:
    """Account lockout management using ``LoginAttempt`` model.

    Lockout state is stored on ``Principal`` (via ``principal.lock_account()``),
    making it durable across restarts and cache clears.
    """

    @staticmethod
    def check_lockout(principal: object) -> None:
        """Check if principal is currently locked out.

        Raises:
            AccountLockedError: If the account is locked.
        """
        if getattr(principal, "is_locked", False):
            principal = getattr(principal, "principal", None)
            locked_until = getattr(principal, "locked_until", None) if principal else None
            raise AccountLockedError(
                locked_until=locked_until,
                detail=f"Account {getattr(principal, 'email', '?')} is locked",
            )

    @staticmethod
    def record_failed_attempt(
        *,
        principal: object | None,
        identifier: str,
        request: HttpRequest,
        reason: str,
        auth_method: str = "",
    ) -> None:
        """Record a failed login attempt and lock the account if threshold reached.

        If the failure count reaches ``MAX_FAILED_ATTEMPTS``, the account is
        locked via ``Principal.lock_account()`` with progressive duration.
        """
        ip_address = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]

        result = LoginAttemptResult.INVALID_CREDENTIALS
        if reason == "account_locked":
            result = LoginAttemptResult.ACCOUNT_LOCKED
        elif reason == "account_disabled":
            result = LoginAttemptResult.ACCOUNT_DISABLED

        LoginAttempt.objects.create(
            principal=principal,
            identifier=identifier,
            result=result,
            auth_method=auth_method,
            ip_address=ip_address,
            user_agent=user_agent,
            failure_reason=reason,
        )

        if principal is None:
            return

        # Check if we should lock the account
        failure_count = LoginAttempt.objects.failure_count(
            principal, window_minutes=authn_settings.LOCKOUT_DURATION_MINUTES
        )

        if failure_count >= authn_settings.MAX_FAILED_ATTEMPTS:
            duration = LockoutService.get_lockout_duration(principal)
            _lock_user_account(principal, duration, reason="Too many failed login attempts")

            # Also record the lockout event
            LoginAttempt.objects.create(
                principal=principal,
                identifier=identifier,
                result=LoginAttemptResult.ACCOUNT_LOCKED,
                auth_method=auth_method,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason=f"Account locked for {duration}",
            )

            from apps.authn.audit import authn_audit

            principal = getattr(principal, "principal", None)
            locked_until = getattr(principal, "locked_until", None) if principal else None
            authn_audit(
                event_type="ACCOUNT_LOCKED",
                principal=principal,
                locked_until=str(locked_until) if locked_until else None,
                attempt_count=failure_count,
            )

            logger.warning(
                "Account locked: principal=%s, failures=%d, duration=%s",
                getattr(principal, "pk", "?"),
                failure_count,
                duration,
            )

    @staticmethod
    def record_success(
        *,
        principal: object,
        request: HttpRequest,
        auth_method: str = "",
        identifier: str = "",
    ) -> None:
        """Record a successful login attempt."""
        LoginAttempt.objects.create(
            principal=principal,
            identifier=identifier or getattr(principal, "email", ""),
            result=LoginAttemptResult.SUCCESS,
            auth_method=auth_method,
            ip_address=_get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        )

    @staticmethod
    def get_lockout_duration(principal: object) -> timedelta:
        """Calculate lockout duration using progressive lockout.

        Base duration is ``LOCKOUT_DURATION_MINUTES``.  Each previous lockout
        in the last 24 hours doubles the duration, capped at
        ``PROGRESSIVE_LOCKOUT_MAX_MINUTES``.
        """
        base_minutes = authn_settings.LOCKOUT_DURATION_MINUTES

        if not authn_settings.PROGRESSIVE_LOCKOUT:
            return timedelta(minutes=base_minutes)

        recent_lockouts = LoginAttempt.objects.recent_lockouts(principal, window_hours=24).count()

        multiplier = 2**recent_lockouts
        duration_minutes = min(
            base_minutes * multiplier,
            authn_settings.PROGRESSIVE_LOCKOUT_MAX_MINUTES,
        )
        return timedelta(minutes=duration_minutes)

    @staticmethod
    def clear_lockout(principal: object) -> None:
        """Manually clear a lockout (admin action)."""
        principal = getattr(principal, "principal", None)
        if principal is None:
            return

        if hasattr(principal, "unlock"):
            principal.unlock()
        elif hasattr(principal, "unlock_account"):
            principal.unlock_account()

        from apps.authn.audit import authn_audit

        authn_audit(event_type="ACCOUNT_UNLOCKED", principal=principal)
        logger.info("Account unlocked: principal=%s", getattr(principal, "pk", "?"))


def _lock_user_account(principal: object, duration: timedelta, reason: str) -> None:
    """Lock a principal account via Principal."""
    if hasattr(principal, "lock_account"):
        principal.lock_account(duration=duration, reason=reason)
    elif hasattr(principal, "principal") and principal.principal:
        principal.principal.lock_account(duration=duration, reason=reason)


def _get_client_ip(request: HttpRequest) -> str | None:
    """Extract client IP from request."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
