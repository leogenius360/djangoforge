"""
Password management views.

Thin wrappers around ``PasswordService``. All business logic
lives in the service layer.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

from apps.authn.services import PasswordService
from apps.core.api import status
from apps.core.api.base import ForgeAPIView as APIView
from apps.core.api.base import Response
from apps.core.api.permissions import AllowAny, IsAuthenticated

from ..serializers import (
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
)

User = get_user_model()


class PasswordChangeView(APIView):
    """Change password for authenticated principal."""

    permission_classes = [IsAuthenticated]
    serializer_class = PasswordChangeSerializer

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        PasswordService.change_password(
            principal=request.user,
            current_password=serializer.validated_data["current_password"],
            new_password=serializer.validated_data["new_password"],
        )

        return Response(
            {"detail": "Password changed successfully."},
            status=status.HTTP_200_OK,
        )


class PasswordResetRequestView(APIView):
    """Request a password reset (unauthenticated)."""

    permission_classes = [AllowAny]
    serializer_class = PasswordResetRequestSerializer

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]

        # Always return success to prevent principal enumeration
        success_msg = "If the email exists, a password reset link has been sent."

        principal = User.objects.filter(email__iexact=email).first()
        if principal is not None:
            PasswordService.request_password_reset(principal=principal, delivery_target=email)
            # The caller is responsible for sending the token via email.
            # In production, delegate to a notification service.

        return Response({"detail": success_msg}, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    """Confirm a password reset with token (unauthenticated)."""

    permission_classes = [AllowAny]
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        PasswordService.confirm_password_reset(
            raw_token=serializer.validated_data["token"],
            new_password=serializer.validated_data["new_password"],
        )

        return Response(
            {"detail": "Password has been reset successfully."},
            status=status.HTTP_200_OK,
        )
