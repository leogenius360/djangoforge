"""
REST API views for the auditing subsystem.

All views require ``is_staff=True``.

Endpoints
---------
GET  /api/audit/events/                                   — paginated event list
GET  /api/audit/events/<uuid:pk>/                         — single event detail
GET  /api/audit/history/?content_type=app.model&object_id=…  — object history
GET  /api/audit/version/?content_type=app.model&object_id=…&version=N  — state at version N
"""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditing.api.permissions import IsStaffUser
from apps.auditing.api.serializers.event import EventDetailSerializer, EventListSerializer
from apps.auditing.models.event import Event

# ---------------------------------------------------------------------------
# Event list  —  GET /api/audit/events/
# ---------------------------------------------------------------------------


class EventListView(generics.ListAPIView):
    """
    Paginated list of audit events.

    Query parameters
    ----------------
    event_type
        Filter by event type (e.g. ``create``, ``update``, ``delete``).
    content_type
        Filter by audited model in ``app_label.model`` format
        (e.g. ``accounts.user``).
    object_id
        Filter by the PK of the audited instance.
    actor_id
        Filter by the PK of the acting user.
    date_from
        ISO-8601 datetime lower bound for ``created_at``.
    date_to
        ISO-8601 datetime upper bound for ``created_at``.
    """

    permission_classes = [IsStaffUser]
    serializer_class = EventListSerializer

    def get_queryset(self):  # type: ignore[override]
        qs = Event.objects.select_related("content_type", "actor").order_by("-created_at")

        params = self.request.query_params

        event_type = params.get("event_type")
        if event_type:
            qs = qs.filter(event_type=event_type)

        content_type_label = params.get("content_type")
        if content_type_label:
            try:
                app_label, model = content_type_label.lower().split(".", 1)
                ct = ContentType.objects.get_by_natural_key(app_label, model)
                qs = qs.filter(content_type=ct)
            except (ValueError, ContentType.DoesNotExist):
                return qs.none()

        object_id = params.get("object_id")
        if object_id:
            qs = qs.filter(object_id=object_id)

        actor_id = params.get("actor_id")
        if actor_id:
            qs = qs.filter(actor_id=actor_id)

        date_from = params.get("date_from")
        if date_from:
            parsed = parse_datetime(date_from)
            if parsed:
                qs = qs.filter(created_at__gte=parsed)

        date_to = params.get("date_to")
        if date_to:
            parsed = parse_datetime(date_to)
            if parsed:
                qs = qs.filter(created_at__lte=parsed)

        return qs


# ---------------------------------------------------------------------------
# Event detail  —  GET /api/audit/events/<uuid:pk>/
# ---------------------------------------------------------------------------


class EventDetailView(generics.RetrieveAPIView):
    """Single audit event with full snapshot."""

    permission_classes = [IsStaffUser]
    serializer_class = EventDetailSerializer
    queryset = Event.objects.select_related("content_type", "actor", "parent")


# ---------------------------------------------------------------------------
# Object history  —  GET /api/audit/history/
# ---------------------------------------------------------------------------


_CONTENT_TYPE_PARAM = OpenApiParameter(
    "content_type",
    str,
    OpenApiParameter.QUERY,
    required=True,
    description="Audited model in 'app_label.model' format, e.g. 'accounts.principal'.",
)
_OBJECT_ID_PARAM = OpenApiParameter(
    "object_id",
    str,
    OpenApiParameter.QUERY,
    required=True,
    description="Primary key of the audited object.",
)


class ObjectHistoryView(APIView):
    """
    All audit events for a specific object, ordered by version ascending.

    Required query parameters
    -------------------------
    content_type
        Audited model in ``app_label.model`` format.
    object_id
        PK of the audited instance.
    """

    permission_classes = [IsStaffUser]

    @extend_schema(
        parameters=[_CONTENT_TYPE_PARAM, _OBJECT_ID_PARAM],
        responses=EventListSerializer(many=True),
    )
    def get(self, request):
        content_type_label = request.query_params.get("content_type", "")
        object_id = request.query_params.get("object_id", "")

        errors = {}
        if not content_type_label:
            errors["content_type"] = "This parameter is required."
        if not object_id:
            errors["object_id"] = "This parameter is required."
        if errors:
            raise serializers.ValidationError(errors)

        try:
            app_label, model = content_type_label.lower().split(".", 1)
            ct = ContentType.objects.get_by_natural_key(app_label, model)
        except (ValueError, ContentType.DoesNotExist) as exc:
            raise serializers.ValidationError(
                {"content_type": f"Unknown content type: {content_type_label!r}."}
            ) from exc

        events = (
            Event.objects.filter(content_type=ct, object_id=object_id)
            .select_related("content_type", "actor")
            .order_by("version")
        )
        serializer = EventListSerializer(events, many=True)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Object version  —  GET /api/audit/version/
# ---------------------------------------------------------------------------


class ObjectVersionView(APIView):
    """
    Model state snapshot at a specific version number.

    Required query parameters
    -------------------------
    content_type
        Audited model in ``app_label.model`` format.
    object_id
        PK of the audited instance.
    version
        Version number (positive integer).
    """

    permission_classes = [IsStaffUser]

    @extend_schema(
        parameters=[
            _CONTENT_TYPE_PARAM,
            _OBJECT_ID_PARAM,
            OpenApiParameter(
                "version",
                int,
                OpenApiParameter.QUERY,
                required=True,
                description="Version number (positive integer).",
            ),
        ],
        responses=inline_serializer(
            "ObjectVersionResponse",
            fields={
                "version": serializers.IntegerField(),
                "state": serializers.JSONField(),
            },
        ),
    )
    def get(self, request):
        content_type_label = request.query_params.get("content_type", "")
        object_id = request.query_params.get("object_id", "")
        version_str = request.query_params.get("version", "")

        errors = {}
        if not content_type_label:
            errors["content_type"] = "This parameter is required."
        if not object_id:
            errors["object_id"] = "This parameter is required."
        if not version_str:
            errors["version"] = "This parameter is required."
        if errors:
            raise serializers.ValidationError(errors)

        try:
            version = int(version_str)
            if version < 1:
                raise ValueError
        except ValueError as exc:
            raise serializers.ValidationError({"version": "Version must be a positive integer."}) from exc

        try:
            app_label, model = content_type_label.lower().split(".", 1)
            ct = ContentType.objects.get_by_natural_key(app_label, model)
        except (ValueError, ContentType.DoesNotExist) as exc:
            raise serializers.ValidationError(
                {"content_type": f"Unknown content type: {content_type_label!r}."}
            ) from exc

        event = Event.objects.filter(
            content_type=ct,
            object_id=object_id,
            version=version,
        ).first()

        if event is None:
            return Response(
                {"detail": f"No event found for version {version}."},
                status=status.HTTP_404_NOT_FOUND,
            )

        state = event.reconstruct_snapshot()
        if state is None:
            return Response(
                {"detail": "State could not be reconstructed for this version."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({"version": version, "state": state})
