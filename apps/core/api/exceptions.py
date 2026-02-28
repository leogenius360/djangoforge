"""
API exceptions for the DjangoForge API layer.

Provides exception classes that mirror the DRF exception hierarchy so that
existing view code only needs an import change.
"""

from __future__ import annotations


class APIException(Exception):
    """Base class for all API exceptions."""

    status_code: int = 500
    default_detail: str = "A server error occurred."

    def __init__(self, detail: str | None = None, status_code: int | None = None):
        self.detail = detail or self.default_detail
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.detail)


class ValidationError(APIException):
    """Raised when request data fails validation."""

    status_code = 400
    default_detail = "Invalid input."

    def __init__(self, detail: str | dict | list | None = None, status_code: int | None = None):
        if detail is None:
            detail = self.default_detail
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        Exception.__init__(self, str(detail))


class AuthenticationFailed(APIException):
    """Raised when authentication fails."""

    status_code = 401
    default_detail = "Incorrect authentication credentials."


class NotAuthenticated(APIException):
    """Raised when an unauthenticated request is made to a protected endpoint."""

    status_code = 401
    default_detail = "Authentication credentials were not provided."


class PermissionDenied(APIException):
    """Raised when the user does not have permission."""

    status_code = 403
    default_detail = "You do not have permission to perform this action."


class NotFound(APIException):
    """Raised when the requested resource does not exist."""

    status_code = 404
    default_detail = "Not found."


class MethodNotAllowed(APIException):
    """Raised when the HTTP method is not allowed."""

    status_code = 405
    default_detail = "Method not allowed."


class Throttled(APIException):
    """Raised when the request is throttled."""

    status_code = 429
    default_detail = "Request was throttled."

    def __init__(self, wait: int | None = None, detail: str | None = None):
        self.wait = wait
        super().__init__(detail)
