"""
Verification views (email and phone).

Thin wrappers around ``VerificationService``. All business logic
lives in the service layer.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.services import VerificationService

from ..serializers import (
    EmailVerificationConfirmSerializer,
    PhoneVerificationConfirmSerializer,
)


class EmailVerificationRequestView(APIView):
    """Request email verification for authenticated user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={200: OpenApiResponse(description="Verification email sent.")},
    )
    def post(self, request):
        VerificationService.request_email_verification(principal=request.user)

        # The caller is responsible for sending the verification email.

        return Response(
            {"detail": "Verification email has been sent."},
            status=status.HTTP_200_OK,
        )


class EmailVerificationConfirmView(APIView):
    """Confirm email verification with token."""

    permission_classes = [AllowAny]
    serializer_class = EmailVerificationConfirmSerializer

    def post(self, request):
        serializer = EmailVerificationConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        VerificationService.confirm_email_verification(raw_token=serializer.validated_data["token"])

        return Response(
            {"detail": "Email verified successfully."},
            status=status.HTTP_200_OK,
        )


class PhoneVerificationRequestView(APIView):
    """Request phone verification for authenticated user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={200: OpenApiResponse(description="Verification OTP sent.")},
    )
    def post(self, request):
        VerificationService.request_phone_verification(principal=request.user)

        # The caller is responsible for sending the OTP via SMS.

        return Response(
            {"detail": "Verification OTP has been sent."},
            status=status.HTTP_200_OK,
        )


class PhoneVerificationConfirmView(APIView):
    """Confirm phone verification with OTP."""

    permission_classes = [IsAuthenticated]
    serializer_class = PhoneVerificationConfirmSerializer

    def post(self, request):
        serializer = PhoneVerificationConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        VerificationService.confirm_phone_verification(
            principal=request.user,
            otp=serializer.validated_data["otp"],
        )

        return Response(
            {"detail": "Phone number verified successfully."},
            status=status.HTTP_200_OK,
        )
