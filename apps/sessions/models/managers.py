"""
Session manager with issuance + lookup helpers.

Security properties
-------------------
- Raw session handles and refresh tokens are never stored in the DB.
- DB stores only HMAC(token) using a server-side pepper.
- Refresh token rotation is supported via family_id + parent links.

Returned values
---------------
create_session() returns:
    (session, cookie_handle_raw|None, refresh_token_raw|None)

Callers should:
- send cookie_handle_raw as a secure cookie OR store it client-side securely
- store refresh_token_raw as appropriate (e.g. secure storage on mobile)

NOTE: Access tokens are intentionally not modeled here. If you need deny-listing,
store ACCESS_JTI credentials.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.models import BaseManager

from ..enums import SessionChannel, SessionCredentialKind
from .querysets import AuthSessionQuerySet

if TYPE_CHECKING:
    from apps.accounts.models.principal import Principal


def _pepper() -> bytes:
    """
    Return the HMAC pepper for session credential hashing.

    Prefer SESSION_TOKEN_PEPPER. If missing, fall back to SECRET_KEY.
    """
    p = getattr(settings, "SESSION_TOKEN_PEPPER", "") or settings.SECRET_KEY
    return p.encode("utf-8")


def token_hmac(raw: str) -> str:
    """
    Compute HMAC-SHA256 hex digest for a token/handle.

    This is the core security function for session credentials.
    Raw tokens are NEVER stored - only their HMAC digests.

    Parameters
    ----------
    raw:
        Raw token string (never stored in database).

    Returns
    -------
    str
        64-character hex digest of HMAC-SHA256(pepper, raw_token).

    Security
    --------
    Uses SESSION_TOKEN_PEPPER from settings (or SECRET_KEY as fallback).
    Even with database compromise, raw tokens cannot be recovered.
    """
    return hmac.new(_pepper(), raw.encode("utf-8"), hashlib.sha256).hexdigest()


class AuthSessionManager(BaseManager.from_queryset(AuthSessionQuerySet)):
    """Manager for AuthSession with issuance + lookup helpers."""

    def valid(self, now=None):
        """Convenience proxy to AuthSessionQuerySet.valid()."""
        return self.get_queryset().valid(now=now)

    @transaction.atomic
    def create_session(
        self,
        *,
        principal: Principal,
        channel: SessionChannel,
        scopes: list[str] | None = None,
        auth_method: str = "",
        auth_status: str = "",
        mfa_method: str = "",
        user_agent: str = "",
        ip_address: str | None = None,
        device_id: str = "",
        device_fingerprint: str = "",
        is_trusted_device: bool = False,
        absolute_ttl: timedelta | None = timedelta(hours=24),
        idle_ttl: timedelta | None = None,
        issue_cookie_handle: bool = True,
        issue_refresh_token: bool = True,
        refresh_ttl: timedelta | None = timedelta(days=30),
        max_concurrent_sessions: int | None = None,
        metadata: dict | None = None,
    ):
        """
        Create a new session and optionally issue both:
        - cookie session handle (SESSION_HANDLE)
        - refresh token (REFRESH_TOKEN)

        Parameters
        ----------
        principal:
            accounts.Principal owner.
        channel:
            SessionChannel (browser/api/service/agent). Stored in metadata.
        auth_method:
            Authentication method used (password/webauthn/etc). Stored in metadata.
        auth_status:
            Auth status (authenticated/pending_mfa). Stored in metadata.
        mfa_method:
            MFA method used (totp/webauthn/sms/none). Stored in metadata.
        user_agent:
            Browser/client user agent string. Truncated to 500 chars.
        ip_address:
            Client IP address for session tracking.
        device_id:
            Device identifier for multi-device management.
        device_fingerprint:
            Device fingerprint for security/tracking.
        is_trusted_device:
            Whether this device is marked as trusted.
        scopes:
            OAuth/permission scopes for this session.
        absolute_ttl:
            Absolute session TTL (None means no absolute expiry; generally not recommended).
        idle_ttl:
            Idle TTL; if provided sets idle_expires_at. Extend this explicitly in middleware.
        issue_cookie_handle:
            If True, generate and store a SESSION_HANDLE credential.
        issue_refresh_token:
            If True, generate and store a REFRESH_TOKEN credential.
        refresh_ttl:
            Refresh token expiry time (can be longer than session TTL for token-based flows).
        max_concurrent_sessions:
            If provided, revoke oldest sessions beyond this limit.
        metadata:
            Additional metadata to store. Auth fields (channel, auth_method, etc.) are
            automatically added to metadata if provided.

        Returns
        -------
        tuple
            (session, cookie_handle_raw|None, refresh_token_raw|None)

        Note
        ----
        Raw tokens (cookie_handle, refresh_token) are NEVER stored in DB.
        Only HMAC-SHA256 hashes are persisted in SessionCredential.
        Caller must send raw tokens to client (cookie/response body).
        """
        now = timezone.now()

        if not principal.can_authenticate:
            raise ValueError("Principal cannot authenticate (inactive/expired/deleted).")

        if max_concurrent_sessions:
            self._enforce_max_sessions(principal=principal, limit=max_concurrent_sessions)

        expires_at = (now + absolute_ttl) if absolute_ttl else None
        idle_expires_at = (now + idle_ttl) if idle_ttl else None

        # Store auth metadata in session metadata field
        session_metadata = metadata or {}
        if channel:
            session_metadata["channel"] = channel if isinstance(channel, str) else channel.value
        if auth_method:
            session_metadata["auth_method"] = auth_method
        if auth_status:
            session_metadata["auth_status"] = auth_status
        if mfa_method:
            session_metadata["mfa_method"] = mfa_method

        session = self.model.objects.create(
            principal=principal,
            authenticated_at=now if auth_status == "authenticated" else None,
            last_seen_at=now,
            expires_at=expires_at,
            idle_expires_at=idle_expires_at,
            user_agent=(user_agent or "")[:500],
            ip_first=ip_address,
            ip_last=ip_address,
            device_id=(device_id or "")[:128],
            device_fingerprint=(device_fingerprint or "")[:255],
            is_trusted_device=is_trusted_device,
            scopes=scopes or [],
            metadata=session_metadata,
            security_stamp_at_issue=principal.security_stamp,
        )

        cookie_raw = None
        refresh_raw = None

        if issue_cookie_handle:
            cookie_raw = secrets.token_urlsafe(32)
            session.credentials.create(
                kind=SessionCredentialKind.SESSION_HANDLE,
                handle_hash=token_hmac(cookie_raw),
                expires_at=expires_at,
            )

        if issue_refresh_token:
            refresh_raw = secrets.token_urlsafe(48)
            family_id = uuid.uuid4()
            session.credentials.create(
                kind=SessionCredentialKind.REFRESH_TOKEN,
                handle_hash=token_hmac(refresh_raw),
                expires_at=(now + refresh_ttl) if refresh_ttl else None,
                family_id=family_id,
            )

        return session, cookie_raw, refresh_raw

    def _enforce_max_sessions(self, *, principal, limit: int) -> None:
        """
        Revoke oldest ACTIVE sessions beyond the provided limit.

        This is optional policy enforcement; you may prefer user-driven session management instead.
        """
        qs = (
            self.get_queryset()
            .filter(
                principal=principal,
                disabled_at__isnull=True,
                deleted_at__isnull=True,
            )
            .order_by("-created_at")
        )
        keep_ids = list(qs.values_list("id", flat=True)[:limit])
        if not keep_ids:
            return

        now = timezone.now()
        from apps.core.context import require_system_actor

        system_actor = require_system_actor()
        qs.exclude(id__in=keep_ids).update(
            revoked_at=now,
            disabled_at=now,
            disabled_by=system_actor,
            disabled_reason="Max session limit enforced",
            logged_out_at=None,
        )
