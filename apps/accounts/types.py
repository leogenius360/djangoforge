"""apps.accounts.types

Type definitions for accounts configuration.

This module contains ONLY type definitions with no Django dependencies,
making it safe to import in Django settings files without circular imports.

Usage in settings::

    from apps.accounts.types import AccountsNamespaceSettings

    ACCOUNTS: AccountsNamespaceSettings = {
        "USERNAME_CASE_INSENSITIVE": True,
        "DEFAULT_LOCK_DURATION_MINUTES": 30,
        ...
    }
"""

from __future__ import annotations

from typing import TypedDict

__all__ = [
    "AccountsNamespaceSettings",
]


class AccountsNamespaceSettings(TypedDict, total=False):
    """Shape of the optional ``settings.ACCOUNTS`` dict.

    Safe to import in Django settings files (no Django dependencies).
    """

    # Principal kinds extensibility
    PRINCIPAL_KINDS: list[dict[str, str]]

    # Username
    USERNAME_MIN_LENGTH: int
    USERNAME_MAX_LENGTH: int
    USERNAME_CASE_INSENSITIVE: bool
    USERNAME_RESERVED_WORDS: list[str]
    AUTO_GENERATE_SERVICE_USERNAME: bool

    # Lifecycle
    DEFAULT_LOCK_DURATION_MINUTES: int
    MAX_FAILED_LOGIN_ATTEMPTS: int

    # Security stamp rotation
    SECURITY_STAMP_ROTATION_ON_PASSWORD_CHANGE: bool
    SECURITY_STAMP_ROTATION_ON_EMAIL_CHANGE: bool

    # Registration / identity
    REQUIRE_EMAIL_VERIFICATION: bool
    ALLOW_MULTIPLE_SESSIONS: bool
    DISPLAY_NAME_MAX_LENGTH: int
    PHONE_REQUIRED: bool

    # Service accounts
    SERVICE_ACCOUNT_MAX_SCOPES: int

    # API clients
    API_CLIENT_SECRET_MIN_LENGTH: int

    # Agents
    AGENT_REQUIRE_OWNER: bool

    # API access control
    API_REQUIRE_STAFF: bool
    API_PAGE_SIZE: int

    # Caching
    ENABLE_PRINCIPAL_CACHE: bool
    PRINCIPAL_CACHE_TTL: int

    # Password hashing for service credentials
    CLIENT_SECRET_HASHER: str

    # Metadata limits
    MAX_METADATA_SIZE_BYTES: int
    MAX_TAGS_COUNT: int

    # Feature flags
    ENABLE_AGENT_ACCOUNTS: bool
    ENABLE_API_CLIENTS: bool
    ENABLE_SERVICE_ACCOUNTS: bool

    # Audit integration (optional)
    AUDIT_PRINCIPAL_CHANGES: bool
    AUDIT_BACKEND: str

    # Custom validators (dotted import paths)
    PRINCIPAL_VALIDATORS: list[str]
    USER_ACCOUNT_VALIDATORS: list[str]
