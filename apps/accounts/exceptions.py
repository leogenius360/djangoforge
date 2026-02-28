"""
Account-specific exceptions.

All exceptions inherit from ``AccountError`` so callers can catch them
uniformly or individually.
"""

from __future__ import annotations


class AccountError(Exception):
    """Base exception for the accounts app."""


class AccountDisabledError(AccountError):
    """Raised when operating on a disabled account."""


class AccountLockedError(AccountError):
    """Raised when operating on a locked account."""


class AccountSuspendedError(AccountError):
    """Raised when operating on a suspended account."""


class PrincipalNotFoundError(AccountError):
    """Raised when a principal cannot be resolved."""


class PrincipalTypeMismatchError(AccountError):
    """Raised when principal kind does not match expected concrete type."""


class SecurityStampMismatchError(AccountError):
    """Raised when a session's security stamp does not match the principal's."""


class ProvisioningError(AccountError):
    """Raised when atomic provisioning of principal + concrete account fails."""


class UsernameConflictError(AccountError):
    """Raised when a requested username is already taken."""

    def __init__(self, message: str = "Username is already in use.", *, username: str = ""):
        self.username = username
        super().__init__(message)


class InvalidUsernameError(AccountError):
    """Raised when a username fails validation (format, reserved words, length)."""


__all__ = [
    "AccountError",
    "AccountDisabledError",
    "AccountLockedError",
    "AccountSuspendedError",
    "PrincipalNotFoundError",
    "PrincipalTypeMismatchError",
    "SecurityStampMismatchError",
    "ProvisioningError",
    "UsernameConflictError",
    "InvalidUsernameError",
]
