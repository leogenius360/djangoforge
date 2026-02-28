"""
Token management views.

Provides:
- ``TokenRefreshView``  — exchange an opaque refresh token for a new JWT access token
- ``TokenVerifyView``   — verify a JWT access token is valid (cheap, no DB hit)

These endpoints replace the ``rest_framework_simplejwt`` token URLs previously
mounted at ``/api/auth/token/*``.  They are now served from the authn app at
``/api/authn/token/refresh/`` and ``/api/authn/token/verify/``.
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import logging

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.exceptions import TokenExpiredError, TokenInvalidError
from apps.authn.services.jwt import JWTService
from apps.sessions.enums import SessionCredentialKind

from ..serializers import (
    TokenRefreshResponseSerializer,
    TokenRefreshSerializer,
    TokenVerifyResponseSerializer,
    TokenVerifySerializer,
)

logger = logging.getLogger(__name__)


def _pepper() -> bytes:
    p = getattr(settings, "SESSION_TOKEN_PEPPER", "") or settings.SECRET_KEY
    return p.encode("utf-8")


def _token_hmac(raw: str) -> str:
    return _hmac.new(_pepper(), raw.encode("utf-8"), hashlib.sha256).hexdigest()


class TokenRefreshView(APIView):
    """
    Refresh an access token.

    Accepts an opaque ``refresh_token`` previously issued at login.
    Validates it against the ``SessionCredential`` table (HMAC lookup),
    checks the backing ``AuthSession`` is still valid, and issues a fresh
    JWT access token.  The refresh token itself is rotation-based — the old
    credential is revoked and a new one is issued.

    Request body::

        { "refresh_token": "<opaque-refresh-token>" }

    Response::

        {
            "access_token": "<jwt>",
            "refresh_token": "<new-opaque-refresh-token>",
            "token_type": "Bearer",
            "expires_in": <seconds>
        }
    """

    permission_classes = [AllowAny]

    @extend_schema(request=TokenRefreshSerializer, responses=TokenRefreshResponseSerializer)
    def post(self, request):
        from apps.sessions.models.credentials import SessionCredential

        raw_token = request.data.get("refresh_token", "").strip()
        if not raw_token:
            return Response({"detail": "refresh_token is required."}, status=status.HTTP_400_BAD_REQUEST)

        token_hash = _token_hmac(raw_token)

        # Look up the credential
        credential = (
            SessionCredential.objects.select_related("session__principal")
            .filter(
                kind=SessionCredentialKind.REFRESH_TOKEN,
                handle_hash=token_hash,
                is_revoked=False,
                deleted_at__isnull=True,
            )
            .first()
        )

        if credential is None:
            logger.warning("TokenRefreshView: refresh token not found or already revoked")
            return Response({"detail": "Invalid or expired refresh token."}, status=status.HTTP_401_UNAUTHORIZED)

        session = credential.session

        # Validate underlying session
        if not session.is_valid:
            logger.warning("TokenRefreshView: session %s is not valid", session.pk)
            return Response({"detail": "Session is no longer valid."}, status=status.HTTP_401_UNAUTHORIZED)

        # Rotate: revoke old credential, issue new one
        from django.utils import timezone

        now = timezone.now()
        old_expires_at = credential.expires_at

        # Revoke old
        credential.is_revoked = True
        credential.revoked_at = now
        credential.save(update_fields=["is_revoked", "revoked_at"])

        # Issue new refresh token
        import secrets
        import uuid

        new_raw = secrets.token_urlsafe(48)
        new_family_id = credential.family_id or uuid.uuid4()
        session.credentials.create(
            kind=SessionCredentialKind.REFRESH_TOKEN,
            handle_hash=_token_hmac(new_raw),
            expires_at=old_expires_at,
            family_id=new_family_id,
            parent_id=credential.pk,
        )

        # Issue new access token
        access_token = JWTService.issue_access_token(session)

        from apps.authn.settings import authn_settings

        return Response(
            {
                "access_token": access_token,
                "refresh_token": new_raw,
                "token_type": "Bearer",
                "expires_in": authn_settings.ACCESS_TOKEN_LIFETIME_SECONDS,
            },
            status=status.HTTP_200_OK,
        )


class TokenVerifyView(APIView):
    """
    Verify a JWT access token.

    Performs signature and expiry validation only (no DB lookup).
    Returns 200 for valid tokens; 401 for invalid/expired ones.

    Request body::

        { "token": "<jwt>" }
    """

    permission_classes = [AllowAny]

    @extend_schema(request=TokenVerifySerializer, responses=TokenVerifyResponseSerializer)
    def post(self, request):
        raw_token = request.data.get("token", "").strip()
        if not raw_token:
            return Response({"detail": "token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = JWTService.verify_access_token(raw_token)
        except TokenExpiredError:
            return Response({"detail": "Token has expired."}, status=status.HTTP_401_UNAUTHORIZED)
        except TokenInvalidError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

        return Response(
            {
                "sub": payload.get("sub"),
                "sid": payload.get("sid"),
                "exp": payload.get("exp"),
                "valid": True,
            },
            status=status.HTTP_200_OK,
        )
