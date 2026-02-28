"""
Filtering utilities for the DjangoForge API layer.

Provides ``BaseFilterBackend``, ``SearchFilter``, and ``OrderingFilter``
that work with pure Django views.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest
    from django.views import View


class BaseFilterBackend:
    """Base class for filter backends."""

    def filter_queryset(self, request: HttpRequest, queryset: QuerySet, view: View) -> QuerySet:
        return queryset


class SearchFilter(BaseFilterBackend):
    """Simple text search across specified model fields."""

    search_param: str = "search"

    def filter_queryset(self, request: HttpRequest, queryset: QuerySet, view: View) -> QuerySet:
        search_term = request.GET.get(self.search_param, "").strip()
        if not search_term:
            return queryset
        search_fields = getattr(view, "search_fields", None)
        if not search_fields:
            return queryset
        from django.db.models import Q

        q = Q()
        for field in search_fields:
            q |= Q(**{f"{field}__icontains": search_term})
        return queryset.filter(q)


class OrderingFilter(BaseFilterBackend):
    """Order results by query parameter."""

    ordering_param: str = "ordering"

    def filter_queryset(self, request: HttpRequest, queryset: QuerySet, view: View) -> Any:
        ordering = request.GET.get(self.ordering_param, "").strip()
        if not ordering:
            default_ordering = getattr(view, "ordering", None)
            if default_ordering:
                if isinstance(default_ordering, str):
                    default_ordering = [default_ordering]
                return queryset.order_by(*default_ordering)
            return queryset

        allowed = set(getattr(view, "ordering_fields", []) or [])
        fields = []
        for field in ordering.split(","):
            field = field.strip()
            raw = field.lstrip("-")
            if allowed and raw not in allowed:
                continue
            fields.append(field)
        if fields:
            return queryset.order_by(*fields)
        return queryset
