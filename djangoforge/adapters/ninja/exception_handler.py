"""
Ninja exception handler that emits :class:`~djangoforge.api.contracts.ProblemDetail`.
"""

from __future__ import annotations

from typing import Any

from django.http import JsonResponse

from djangoforge.api.contracts import ProblemDetail
from djangoforge.middleware.correlation import get_correlation_id


def forge_ninja_exception_handler(request: Any, exc: Exception) -> JsonResponse:
    """Return a ``ProblemDetail`` JSON response for unhandled exceptions.

    Wire this into Ninja via::

        api = NinjaAPI(exception_handlers=[(Exception, forge_ninja_exception_handler)])
    """
    status_code = getattr(exc, "status_code", 500)
    problem = ProblemDetail(
        title=type(exc).__name__,
        status=status_code,
        detail=str(exc),
        correlation_id=get_correlation_id(),
    )
    return JsonResponse(
        {
            "type": problem.type,
            "title": problem.title,
            "status": problem.status,
            "detail": problem.detail,
            "errors": problem.errors,
            "correlation_id": problem.correlation_id,
        },
        status=status_code,
    )
