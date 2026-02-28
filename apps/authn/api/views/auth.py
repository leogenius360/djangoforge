"""
Authentication views (login, MFA login, logout).

Thin wrappers around ``AuthenticationService``. All business logic
lives in the service layer.
"""

from __future__ import annotations

from apps.authn.services import AuthenticationService
from apps.core.api import status
from apps.core.api.base import ForgeAPIView as APIView
from apps.core.api.base import Response
from apps.core.api.decorators import OpenApiResponse, extend_schema
from apps.core.api.permissions import AllowAny, IsAuthenticated

from ..serializers import LoginSerializer, LogoutSerializer, MFALoginSerializer


class LoginView(APIView):
    """Password-based login.

    Returns JWT access + opaque refresh tokens alongside session metadata.
    """

    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = AuthenticationService.authenticate_with_password(
            request=request,
            identifier=serializer.validated_data["identifier"],
            password=serializer.validated_data["password"],
        )

        return Response(
            {
                "access_token": result.access_token,
                "refresh_token": result.refresh_token,
                "token_type": "Bearer",
                "expires_in": result.expires_in,
                "principal_id": str(getattr(result.principal, "pk", "")),
                "session_id": str(getattr(result.session, "pk", "")),
                "auth_method": result.auth_method,
            },
            status=status.HTTP_200_OK,
        )


class MFALoginView(APIView):
    """Complete MFA verification during login."""

    permission_classes = [AllowAny]
    serializer_class = MFALoginSerializer

    def post(self, request):
        serializer = MFALoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = AuthenticationService.complete_mfa_authentication(
            request=request,
            mfa_token=serializer.validated_data["mfa_token"],
            mfa_code=serializer.validated_data["code"],
        )

        return Response(
            {
                "access_token": result.access_token,
                "refresh_token": result.refresh_token,
                "token_type": "Bearer",
                "expires_in": result.expires_in,
                "principal_id": str(getattr(result.principal, "pk", "")),
                "session_id": str(getattr(result.session, "pk", "")),
                "auth_method": result.auth_method,
                "mfa_method": result.mfa_method,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    """Logout user (single session or all sessions)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=LogoutSerializer,
        responses={200: OpenApiResponse(description="Logged out successfully.")},
    )
    def post(self, request):
        all_sessions = request.data.get("all_sessions", False)

        # Try to resolve the current session
        session = getattr(request, "auth_session", None)

        AuthenticationService.logout(
            request=request,
            principal=request.user,
            session=session,
            all_sessions=all_sessions,
        )

        return Response(
            {"detail": "Logged out successfully."},
            status=status.HTTP_200_OK,
        )
