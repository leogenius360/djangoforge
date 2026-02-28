"""
Session lifecycle management services.

Handles session creation, revocation, expiry, and cleanup operations.
"""

from datetime import timedelta

from apps.accounts.models import Principal
from apps.sessions.models import AuthSession


def revoke_session(session: AuthSession, reason: str = "Session revoked", *, actor: Principal | None = None) -> None:
    """
    Revoke a single session.

    Args:
        session: The session to revoke
        reason: Reason for revocation
    """
    session.revoke(reason=reason, revoked_by=actor)


def revoke_all_user_sessions(
    user, except_session=None, reason: str = "All sessions terminated", *, actor: Principal | None = None
) -> int:
    """
    Revoke all sessions for a user.

    Args:
        user: The user whose sessions to revoke
        except_session: Optional session to keep active
        reason: Reason for revocation

    Returns:
        Number of sessions revoked
    """
    return AuthSession.terminate_all_for_principal(user, except_session=except_session, reason=reason, actor=actor)


def logout_session(session: AuthSession, reason: str = "User logged out") -> None:
    """
    Logout a session.

    Args:
        session: The session to logout
        reason: Reason for logout
    """
    session.logout(reason=reason)


def expire_session(session: AuthSession, reason: str = "Session expired") -> None:
    """
    Mark a session as expired.

    Args:
        session: The session to expire
        reason: Reason for expiration
    """
    session.mark_expired(reason=reason)


def cleanup_expired_sessions(older_than_days: int = 30) -> int:
    """
    Clean up (soft delete) terminal sessions older than the specified days.

    Args:
        older_than_days: Age threshold in days

    Returns:
        Number of sessions cleaned up
    """
    return AuthSession.cleanup_expired_sessions(older_than_days=older_than_days)


def extend_session_expiry(session: AuthSession, duration: timedelta) -> None:
    """
    Extend a session's expiry time.

    Args:
        session: The session to extend
        duration: Time delta to extend by
    """
    session.extend_expiry(duration=duration)
