"""
JWT access token service.

Issues and verifies short-lived JWT access tokens backed by ``AuthSession``.

Design
------
- Every access token contains a ``sid`` (session UUID) claim that ties it to
  a live ``AuthSession`` row.  On verification the session is loaded from the
  database and validated, giving instant revocation when a session is
  disabled/revoked/expired.

- The security stamp (``sec``) is embedded in the token payload and compared
  against ``Principal.security_stamp`` at verification time.  Bumping the
  stamp (e.g. on password-change, lock, suspend) invalidates all outstanding
  access tokens for that principal without a DB write per token.

- Raw tokens are never stored.  The ``ACCESS_JTI`` credential kind in
  ``SessionCredential`` is available for deny-listing if needed in future.

Token payload
-------------
::

    {
        "sub":  "<principal-uuid>",         # principal pk
        "sid":  "<session-uuid>",           # AuthSession pk
        "sec":  <int>,                      # principal.security_stamp at issue
        "iat":  <unix-timestamp>,
        "exp":  <unix-timestamp>,
        "typ":  "access"
    }
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import jwt as pyjwt

from apps.authn.exceptions import TokenExpiredError, TokenInvalidError

logger = logging.getLogger(__name__)


def _signing_key() -> str:
    """Return the secret used for signing/verifying JWT tokens."""
    from django.conf import settings

    return settings.SECRET_KEY


def _algorithm() -> str:
    from apps.authn.settings import authn_settings

    return authn_settings.JWT_ALGORITHM


def _access_ttl_seconds() -> int:
    from apps.authn.settings import authn_settings

    return authn_settings.ACCESS_TOKEN_LIFETIME_SECONDS


class JWTService:
    """Issue and verify JWT access tokens backed by ``AuthSession``."""

    @staticmethod
    def issue_access_token(session: object) -> str:
        """Issue a signed JWT access token for an existing ``AuthSession``.

        Parameters
        ----------
        session:
            An ``AuthSession`` instance that has already been persisted.

        Returns
        -------
        str
            Compact JWT string (header.payload.signature).
        """
        now = datetime.now(tz=UTC)
        ttl = _access_ttl_seconds()
        exp = datetime.fromtimestamp(now.timestamp() + ttl, tz=UTC)

        payload = {
            "sub": str(getattr(session, "principal_id", "")),
            "sid": str(getattr(session, "pk", "")),
            "sec": getattr(session, "security_stamp_at_issue", 0),
            "iat": now,
            "exp": exp,
            "typ": "access",
        }

        token = pyjwt.encode(payload, _signing_key(), algorithm=_algorithm())

        logger.debug(
            "Issued JWT access token for session=%s principal=%s exp=%s",
            getattr(session, "pk", "?"),
            getattr(session, "principal_id", "?"),
            exp.isoformat(),
        )

        return token

    @staticmethod
    def verify_access_token(raw_token: str) -> dict:
        """Verify a JWT access token and return the decoded payload.

        Validates signature, expiry, and ``typ == "access"``.  Does NOT load
        the session from the database — call ``JWTService.authenticate()`` for
        a full authentication that also checks session validity.

        Parameters
        ----------
        raw_token:
            Compact JWT string from the ``Authorization: Bearer <token>`` header.

        Returns
        -------
        dict
            Decoded JWT payload.

        Raises
        ------
        TokenExpiredError
            Token has passed its ``exp`` timestamp.
        TokenInvalidError
            Signature invalid, malformed token, wrong type, or any other issue.
        """
        try:
            payload = pyjwt.decode(
                raw_token,
                _signing_key(),
                algorithms=[_algorithm()],
                options={"require": ["exp", "iat", "sub", "sid", "typ"]},
            )
        except pyjwt.ExpiredSignatureError as exc:
            raise TokenExpiredError("Access token has expired") from exc
        except pyjwt.InvalidTokenError as exc:
            raise TokenInvalidError(f"Invalid access token: {exc}") from exc

        if payload.get("typ") != "access":
            raise TokenInvalidError("Token type is not 'access'")

        return payload

    @staticmethod
    def authenticate(raw_token: str) -> tuple[object, object]:
        """Full authentication: verify JWT + load + validate the backing ``AuthSession``.

        Parameters
        ----------
        raw_token:
            Compact JWT string.

        Returns
        -------
        tuple
            ``(principal, session)`` — both Django model instances.

        Raises
        ------
        TokenExpiredError, TokenInvalidError
            From :meth:`verify_access_token`.
        rest_framework.exceptions.AuthenticationFailed
            Session not found, not valid, or principal mismatch.
        """
        from rest_framework.exceptions import AuthenticationFailed

        from apps.sessions.models import AuthSession

        payload = JWTService.verify_access_token(raw_token)

        sid = payload.get("sid", "")
        sec = payload.get("sec", -1)

        # Load session with principal in single query
        try:
            session = AuthSession.objects.select_related("principal").filter(pk=uuid.UUID(sid)).get()
        except (AuthSession.DoesNotExist, ValueError, AttributeError):
            raise AuthenticationFailed("Session not found") from None

        # Validate session (checks status, expiry, principal.can_authenticate, security_stamp)
        if not session.is_valid:
            raise AuthenticationFailed("Session is not valid or has been revoked")

        # Double-check security stamp matches payload (defence-in-depth)
        principal = session.principal
        if principal.security_stamp != sec:
            raise AuthenticationFailed("Security stamp mismatch — token has been invalidated")

        return principal, session
