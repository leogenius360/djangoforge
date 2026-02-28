"""
URL configuration for sessions app.

Provides endpoints for session management.
"""

from django.urls import path

from .views import SessionListView, SessionTerminateView

app_name = "sessions"

urlpatterns = [
    # ===== SESSION MANAGEMENT =====
    path("", SessionListView.as_view(), name="session-list"),
    path("all/", SessionListView.as_view(), name="session-terminate-all"),  # DELETE to terminate all others
    path("<uuid:session_id>/", SessionTerminateView.as_view(), name="session-terminate"),
]
