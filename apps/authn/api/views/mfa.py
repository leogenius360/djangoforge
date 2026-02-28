"""
MFA management views.

Thin wrappers around ``MFAService``. All business logic
lives in the service layer.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.services import MFAService

from ..serializers import (
    BackupCodesRegenerateSerializer,
    MFAActivateResponseSerializer,
    MFADisableResponseSerializer,
    MFADisableSerializer,
    MFASetupResponseSerializer,
    MFAStatusSerializer,
    MFAVerifySetupSerializer,
)


class MFAStatusView(APIView):
    """Get MFA status for the authenticated user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MFAStatusSerializer)
    def get(self, request):
        mfa_status = MFAService.get_status(request.user)
        return Response(mfa_status, status=status.HTTP_200_OK)


class MFASetupView(APIView):
    """Setup MFA for user account.

    GET: Begin TOTP setup (returns secret + provisioning URI).
    POST: Verify first code and activate TOTP.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=MFASetupResponseSerializer)
    def get(self, request):
        setup_data = MFAService.setup_totp(request.user)
        return Response(
            {
                "secret": setup_data["secret"],
                "provisioning_uri": setup_data["provisioning_uri"],
                "credential_id": setup_data["credential_id"],
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(request=MFAVerifySetupSerializer, responses=MFAActivateResponseSerializer)
    def post(self, request):
        serializer = MFAVerifySetupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = MFAService.activate_totp(request.user, serializer.validated_data["code"])

        from apps.authn.audit import authn_audit

        authn_audit(event_type="MFA_ENABLED", principal=request.user)

        return Response(
            {
                "detail": "MFA enabled successfully.",
                "backup_codes": result["backup_codes"],
            },
            status=status.HTTP_200_OK,
        )


class MFADisableView(APIView):
    """Disable MFA for user account."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=MFADisableSerializer, responses=MFADisableResponseSerializer)
    def post(self, request):
        serializer = MFADisableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        count = MFAService.disable_mfa(request.user, serializer.validated_data["code"])

        from apps.authn.audit import authn_audit

        authn_audit(event_type="MFA_DISABLED", principal=request.user)

        return Response(
            {
                "detail": "MFA disabled successfully.",
                "credentials_revoked": count,
            },
            status=status.HTTP_200_OK,
        )


class BackupCodesRegenerateView(APIView):
    """Regenerate MFA backup codes."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=BackupCodesRegenerateSerializer)
    def post(self, request):
        codes = MFAService.regenerate_backup_codes(request.user)

        return Response(
            {
                "backup_codes": codes,
                "detail": "Backup codes regenerated. Previous codes are invalidated.",
            },
            status=status.HTTP_200_OK,
        )
