"""
Pagination utilities for the DjangoForge API layer.

Provides ``PageNumberPagination`` that works with pure Django views.
"""

from __future__ import annotations

from typing import Any

from django.core.paginator import EmptyPage, Paginator
from django.http import HttpRequest


class PageNumberPagination:
    """
    Simple page-number pagination compatible with the DRF convention.

    Reads ``?page=N`` and ``?page_size=N`` from query parameters.
    """

    page_size: int = 20
    page_size_query_param: str = "page_size"
    page_query_param: str = "page"
    max_page_size: int = 100

    def paginate_queryset(self, queryset: Any, request: HttpRequest) -> list:
        """Return a single page of results."""
        page_size = self._get_page_size(request)
        page_number = request.GET.get(self.page_query_param, 1)

        paginator = Paginator(queryset, page_size)

        try:
            page_number = int(page_number)
        except (TypeError, ValueError):
            page_number = 1

        try:
            self.page = paginator.page(page_number)
        except EmptyPage:
            self.page = paginator.page(paginator.num_pages)

        self.request = request
        self.paginator = paginator
        return list(self.page.object_list)

    def get_paginated_response_data(self, data: list) -> dict:
        """Return a dict with pagination metadata wrapping the results."""
        return {
            "count": self.paginator.count,
            "num_pages": self.paginator.num_pages,
            "page": self.page.number,
            "results": data,
        }

    def _get_page_size(self, request: HttpRequest) -> int:
        if self.page_size_query_param:
            try:
                size = int(request.GET.get(self.page_size_query_param, self.page_size))
                return min(size, self.max_page_size)
            except (TypeError, ValueError):
                pass
        return self.page_size
