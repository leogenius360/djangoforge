"""
Pagination for the accounts app.

Provides a shared pagination class that respects the ``API_PAGE_SIZE``
setting from ``AccountsSettings``.
"""

from __future__ import annotations

from apps.accounts.settings import accounts_settings
from apps.core.api.pagination import PageNumberPagination


class AccountsPagination(PageNumberPagination):
    """Page-number pagination using configurable page size."""

    page_size_query_param = "page_size"
    max_page_size = 100

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.page_size = accounts_settings.API_PAGE_SIZE
