"""Permission check serializers."""

from __future__ import annotations

from apps.core.api import serializers


class CheckPermissionRequestSerializer(serializers.Serializer):
    """Request body for the permission check endpoint."""

    action = serializers.CharField(max_length=50)
    resource_type = serializers.CharField(
        max_length=100,
        help_text="Content type as 'app_label.model', e.g. 'accounts.principal'",
    )
    resource_id = serializers.UUIDField()
    environment = serializers.JSONField(required=False, default=dict)


class CheckPermissionResponseSerializer(serializers.Serializer):
    """Response body for the permission check endpoint."""

    allowed = serializers.BooleanField()
    reason = serializers.CharField()
    evaluation_time_ms = serializers.FloatField()
