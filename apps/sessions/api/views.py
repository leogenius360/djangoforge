"""
Session management views.
"""

import logging

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sessions.models import AuthSession

logger = logging.getLogger(__name__)


@extend_schema_view(
    get=extend_schema(
        summary="List active sessions",
        description="Get list of all active sessions.",
    ),
    delete=extend_schema(
        summary="Terminate all other sessions",
        description="Terminate all sessions except current.",
    ),
)
class SessionListView(APIView):
    """List and manage user sessions."""

    permission_classes = [IsAuthenticated]
    serializer_class = None  # No request body needed

    def get(self, request):
        """List all active sessions."""
        user = request.user
        sessions = AuthSession.get_active_for_principal(user)

        # Mark current session
        current_session_id = request.META.get("HTTP_X_SESSION_ID")
        session_data = []

        for session in sessions:
            data = {
                "id": session.id,
                "ip_address": session.ip_address,
                "user_agent": session.user_agent,
                "device_type": session.device_type,
                "device_name": session.device_name,
                "location_city": session.location_city,
                "location_country": session.location_country,
                "created_at": session.created_at,
                "last_activity_at": session.last_activity_at,
                "expires_at": session.expires_at,
                "is_current": str(session.id) == str(current_session_id),
            }
            session_data.append(data)

        return Response(session_data, status=status.HTTP_200_OK)

    def delete(self, request):
        """Terminate all other sessions."""
        user = request.user
        current_session_id = request.META.get("HTTP_X_SESSION_ID")

        other_sessions = (
            AuthSession.objects.for_principal(user)
            .filter(deleted_at__isnull=True, disabled_at__isnull=True)
            .exclude(pk=current_session_id)
        )
        terminated_count = 0
        for session in other_sessions:
            session.revoke(reason="All sessions terminated")
            terminated_count += 1

        logger.info(
            "All other sessions terminated for user: %s (count=%d)",
            user.username,
            terminated_count,
        )

        return Response({"message": f"Terminated {terminated_count} sessions."}, status=status.HTTP_200_OK)


@extend_schema_view(
    delete=extend_schema(
        summary="Terminate specific session",
        description="Terminate a specific session by ID.",
    )
)
class SessionTerminateView(APIView):
    """Terminate a specific session."""

    permission_classes = [IsAuthenticated]
    serializer_class = None  # No request body needed

    def delete(self, request, session_id):
        """Terminate a specific session."""
        user = request.user

        try:
            session = AuthSession.objects.for_principal(user).get(
                id=session_id,
                deleted_at__isnull=True,
                disabled_at__isnull=True,
            )
        except AuthSession.DoesNotExist:
            return Response({"detail": "Session not found."}, status=status.HTTP_404_NOT_FOUND)

        session.revoke(reason="Session terminated")
        logger.info("Session %s terminated for user: %s", session_id, user.username)

        return Response({"message": "Session terminated."}, status=status.HTTP_200_OK)
