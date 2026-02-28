"""
DRF exception handler that emits :class:`~djangoforge.api.contracts.ProblemDetail`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rest_framework.views import exception_handler as drf_default_handler

from djangoforge.api.contracts import ProblemDetail
from djangoforge.middleware.correlation import get_correlation_id

if TYPE_CHECKING:
    from rest_framework.response import Response


def forge_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Map DRF/Django exceptions to a :class:`ProblemDetail` JSON body."""
    response = drf_default_handler(exc, context)
    if response is None:
        return None

    detail_text = ""
    errors: list[dict[str, Any]] = []

    if isinstance(response.data, dict):
        detail_text = str(response.data.get("detail", ""))
        errors = [{"field": k, "messages": v} for k, v in response.data.items() if k != "detail"]
    elif isinstance(response.data, list):
        errors = [{"messages": response.data}]

    problem = ProblemDetail(
        type="about:blank",
        title=_status_phrase(response.status_code),
        status=response.status_code,
        detail=detail_text,
        errors=errors,
        correlation_id=get_correlation_id(),
    )

    response.data = {
        "type": problem.type,
        "title": problem.title,
        "status": problem.status,
        "detail": problem.detail,
        "errors": problem.errors,
        "correlation_id": problem.correlation_id,
    }
    return response


_PHRASE_MAP = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    429: "Too Many Requests",
    500: "Internal Server Error",
}


def _status_phrase(code: int) -> str:
    """Return the HTTP reason phrase for *code*."""
    return _PHRASE_MAP.get(code, "Error")
