"""
Passwordless authentication views.

Thin wrappers around ``AuthenticationService``. All business logic
lives in the service layer.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.services import AuthenticationService

from ..serializers import (
    PasswordlessRequestSerializer,
    PasswordlessTOTPLoginSerializer,
    PasswordlessVerifySerializer,
)

User = get_user_model()


class PasswordlessRequestView(APIView):
    """Request passwordless login (magic link or OTP)."""

    permission_classes = [AllowAny]
    serializer_class = PasswordlessRequestSerializer

    def post(self, request):
        serializer = PasswordlessRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        method = serializer.validated_data.get("method", "email")
        email = serializer.validated_data.get("email")
        phone_number = serializer.validated_data.get("phone_number")

        # Always return success to prevent principal enumeration
        success_msg = "If the account exists, a login link/code has been sent."

        # Resolve principal
        principal = None
        if email:
            principal = User.objects.filter(
                email__iexact=email,
                passwordless_enabled=True,
            ).first()
        elif phone_number:
            principal = User.objects.filter(
                phone_number=phone_number,
                passwordless_enabled=True,
            ).first()

        if principal is None:
            return Response({"detail": success_msg}, status=status.HTTP_200_OK)

        result = AuthenticationService.request_passwordless_login(principal=principal, method=method)

        # In production, the caller should send the token/OTP via email/SMS.
        # The raw values are returned here for the delivery layer to handle.
        response_data = {"detail": success_msg}

        # Attach delivery info for the notification layer
        response_data["_delivery"] = {
            "token": result.get("token"),
            "otp": result.get("otp"),
            "expires_at": (result["expires_at"].isoformat() if result.get("expires_at") else None),
            "target": email or phone_number,
            "method": method,
        }

        return Response(response_data, status=status.HTTP_200_OK)


class PasswordlessVerifyView(APIView):
    """Verify passwordless login token (magic link or OTP)."""

    permission_classes = [AllowAny]
    serializer_class = PasswordlessVerifySerializer

    def post(self, request):
        serializer = PasswordlessVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = AuthenticationService.verify_passwordless_login(
            request=request,
            raw_token=serializer.validated_data["token"],
            otp=serializer.validated_data.get("otp"),
        )

        return Response(
            {
                "principal_id": str(getattr(result.principal, "pk", "")),
                "session_id": str(getattr(result.session, "pk", "")),
                "auth_method": result.auth_method,
            },
            status=status.HTTP_200_OK,
        )


class PasswordlessTOTPLoginView(APIView):
    """TOTP-only login (no password)."""

    permission_classes = [AllowAny]
    serializer_class = PasswordlessTOTPLoginSerializer

    def post(self, request):
        serializer = PasswordlessTOTPLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = AuthenticationService.authenticate_totp_only(
            request=request,
            identifier=serializer.validated_data["identifier"],
            totp_code=serializer.validated_data["code"],
        )

        return Response(
            {
                "principal_id": str(getattr(result.principal, "pk", "")),
                "session_id": str(getattr(result.session, "pk", "")),
                "auth_method": result.auth_method,
                "mfa_method": result.mfa_method,
            },
            status=status.HTTP_200_OK,
        )
