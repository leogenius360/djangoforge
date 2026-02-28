"""
Filter backends for the accounts app.

Provides query-parameter filters for principal status and kind, usable
on any viewset that resolves to a model with a ``principal`` FK.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.core.api.filters import BaseFilterBackend

if TYPE_CHECKING:
    from django.http import HttpRequest as Request
    from django.views import View as APIView


class PrincipalStatusFilter(BaseFilterBackend):
    """Filter queryset by principal status (``?status=active|disabled|suspended|locked|deleted``)."""

    _STATUS_FILTERS: dict[str, dict] = {
        "active": {
            "principal__disabled_at__isnull": True,
            "principal__suspended_at__isnull": True,
            "principal__deleted_at__isnull": True,
        },
        "disabled": {"principal__disabled_at__isnull": False},
        "suspended": {"principal__suspended_at__isnull": False},
        "deleted": {"principal__deleted_at__isnull": False},
    }

    def filter_queryset(self, request: Request, queryset, view: APIView):
        status = request.query_params.get("status")
        if not status:
            return queryset
        filters = self._STATUS_FILTERS.get(status)
        if filters:
            queryset = queryset.filter(**filters)
        return queryset


class PrincipalKindFilter(BaseFilterBackend):
    """Filter queryset by principal kind (``?kind=user``)."""

    def filter_queryset(self, request: Request, queryset, view: APIView):
        kind = request.query_params.get("kind")
        if kind:
            queryset = queryset.filter(principal__kind=kind)
        return queryset
