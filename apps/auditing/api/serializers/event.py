"""
Serializers for the auditing REST API.

``EventListSerializer`` — compact representation for paginated list views.
``EventDetailSerializer`` — full representation including snapshot.
"""

from __future__ import annotations

from apps.auditing.models.event import Event
from apps.core.api import serializers


class EventListSerializer(serializers.ModelSerializer):
    """Compact event serializer for list views (no snapshot)."""

    content_type_label = serializers.SerializerMethodField()
    ip_address = serializers.CharField(read_only=True, allow_null=True)
    user_agent = serializers.CharField(read_only=True, allow_null=True)
    request_id = serializers.CharField(read_only=True, allow_null=True)
    is_undone = serializers.BooleanField(read_only=True)

    class Meta:
        model = Event
        fields = [
            "id",
            "event_type",
            "content_type",
            "content_type_label",
            "object_id",
            "version",
            "actor",
            "comment",
            "checksum",
            "delta",
            "created_at",
            "is_undone",
            "ip_address",
            "user_agent",
            "request_id",
        ]
        read_only_fields = fields

    def get_content_type_label(self, obj: Event) -> str:
        """Return ``app_label.model`` string for the audited model."""
        ct = obj.content_type
        return f"{ct.app_label}.{ct.model}"


class EventDetailSerializer(EventListSerializer):
    """Full event serializer including the decompressed snapshot."""

    snapshot = serializers.SerializerMethodField()

    class Meta(EventListSerializer.Meta):
        fields = EventListSerializer.Meta.fields + ["snapshot", "parent", "parent_checksum"]
        read_only_fields = fields

    def get_snapshot(self, obj: Event) -> dict | None:
        """Return the decompressed snapshot dict (or None if not stored)."""
        return obj.get_snapshot()
