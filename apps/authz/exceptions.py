"""Authorization-specific exceptions."""

from __future__ import annotations


class AuthzError(Exception):
    """Base exception for the authz app."""


class PermissionNotFoundError(AuthzError):
    """Raised when a permission cannot be found."""


class RoleNotFoundError(AuthzError):
    """Raised when a role cannot be found."""


class RoleHierarchyCycleError(AuthzError):
    """Raised when a role hierarchy change would create a cycle."""


class InvalidAssignmentError(AuthzError):
    """Raised when a role assignment is invalid (e.g. scope mismatch)."""


class PolicyEvaluationError(AuthzError):
    """Raised when ABAC policy evaluation fails."""


class DSLSyntaxError(AuthzError):
    """Raised when a DSL expression has syntax errors."""


class DSLEvaluationError(AuthzError):
    """Raised when DSL expression evaluation fails at runtime."""


class PermissionDeniedError(AuthzError):
    """Raised when an authorization check fails."""
