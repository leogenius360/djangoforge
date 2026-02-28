"""Permission check API view."""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authz.api.serializers.check import (
    CheckPermissionRequestSerializer,
    CheckPermissionResponseSerializer,
)
from apps.authz.services import AuthorizationChecker


class CheckPermissionView(APIView):
    """
    POST /api/authz/check/

    Check whether the current user has permission to perform an action on a
    resource.

    Request body::

        {
            "action": "read",
            "resource_type": "accounts.principal",
            "resource_id": "<uuid>",
            "environment": {}
        }
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=CheckPermissionRequestSerializer,
        responses=CheckPermissionResponseSerializer,
    )
    def post(self, request):
        serializer = CheckPermissionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Resolve content type
        try:
            app_label, model = data["resource_type"].split(".")
        except ValueError:
            return Response(
                {"resource_type": "Must be in 'app_label.model' format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ct = ContentType.objects.get(app_label=app_label, model=model)
        except ContentType.DoesNotExist:
            return Response(
                {"resource_type": f"Content type {data['resource_type']!r} not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        model_class = ct.model_class()
        if model_class is None:
            return Response(
                {"resource_type": "Cannot resolve model class."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            resource = model_class.objects.get(pk=data["resource_id"])
        except model_class.DoesNotExist:
            return Response(
                {"resource_id": "Resource not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        checker = AuthorizationChecker()
        decision = checker.check(
            principal=request.user,
            action=data["action"],
            resource=resource,
            environment=data.get("environment"),
        )

        resp = CheckPermissionResponseSerializer(
            {
                "allowed": decision.allowed,
                "reason": decision.reason,
                "evaluation_time_ms": decision.evaluation_time_ms,
            }
        )
        return Response(resp.data)
