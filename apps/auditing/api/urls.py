"""URL patterns for the auditing API."""

from django.urls import path

from apps.auditing.api.views.events import (
    EventDetailView,
    EventListView,
    ObjectHistoryView,
    ObjectVersionView,
)

app_name = "auditing"

urlpatterns = [
    path("events/", EventListView.as_view(), name="event-list"),
    path("events/<uuid:pk>/", EventDetailView.as_view(), name="event-detail"),
    path("history/", ObjectHistoryView.as_view(), name="object-history"),
    path("version/", ObjectVersionView.as_view(), name="object-version"),
]
