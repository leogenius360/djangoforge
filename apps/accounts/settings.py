"""
Accounts configuration and settings access.

Follows the same hardened ``BaseSettings`` pattern used by the auditing app:

- Fully typed settings interface (IDE autocomplete + mypy-friendly)
- Runtime type validation (fail fast on misconfiguration)
- Immutable settings object at runtime (prevents accidental mutation)
- Efficient attribute access (values are set as real attributes)
- Automatic reload on ``setting_changed`` signal (test-friendly)

Supported configuration style
------------------------------
Namespaced dict in Django settings::

    ACCOUNTS = {
        "USERNAME_CASE_INSENSITIVE": True,
        "DEFAULT_LOCK_DURATION_MINUTES": 30,
        "API_REQUIRE_STAFF": True,
        ...
    }

For IDE autocomplete, import the TypedDict::

    from apps.accounts.types import AccountsNamespaceSettings

    ACCOUNTS: AccountsNamespaceSettings = {...}

Compliance alignment
--------------------
- ISO 27001 A.9  -- Access control configuration
- SOC 2 CC6      -- Logical access defaults
- NIST 800-63B   -- Identity proofing and lifecycle
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

from django.test.signals import setting_changed

from apps.core.settings import BaseSettings


class AccountsSettings(BaseSettings):
    """Accounts app settings with typed defaults.

    All settings are overridable via ``settings.ACCOUNTS`` dict.
    Unknown keys raise ``ImproperlyConfigured`` when ``strict_namespace`` is True.
    """

    settings_key: ClassVar[str] = "ACCOUNTS"
    strict_namespace: ClassVar[bool] = True

    # -----------------------------------------------------------------------
    # Principal kinds extensibility
    # -----------------------------------------------------------------------
    # Additional principal kinds beyond the built-in enum values.
    # Each entry: {"value": "custom_kind", "label": "Custom Kind"}
    PRINCIPAL_KINDS: list[dict[str, str]] = []

    # -----------------------------------------------------------------------
    # Username
    # -----------------------------------------------------------------------
    USERNAME_MIN_LENGTH: int = 3
    USERNAME_MAX_LENGTH: int = 150
    USERNAME_CASE_INSENSITIVE: bool = True
    USERNAME_RESERVED_WORDS: list[str] = []
    AUTO_GENERATE_SERVICE_USERNAME: bool = True

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------
    DEFAULT_LOCK_DURATION_MINUTES: int = 30
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5

    # -----------------------------------------------------------------------
    # Security stamp rotation
    # -----------------------------------------------------------------------
    SECURITY_STAMP_ROTATION_ON_PASSWORD_CHANGE: bool = True
    SECURITY_STAMP_ROTATION_ON_EMAIL_CHANGE: bool = True

    # -----------------------------------------------------------------------
    # Registration / identity
    # -----------------------------------------------------------------------
    REQUIRE_EMAIL_VERIFICATION: bool = False
    ALLOW_MULTIPLE_SESSIONS: bool = True
    DISPLAY_NAME_MAX_LENGTH: int = 150
    PHONE_REQUIRED: bool = False

    # -----------------------------------------------------------------------
    # Service accounts
    # -----------------------------------------------------------------------
    SERVICE_ACCOUNT_MAX_SCOPES: int = 100

    # -----------------------------------------------------------------------
    # API clients
    # -----------------------------------------------------------------------
    API_CLIENT_SECRET_MIN_LENGTH: int = 32

    # -----------------------------------------------------------------------
    # Agents
    # -----------------------------------------------------------------------
    AGENT_REQUIRE_OWNER: bool = True

    # -----------------------------------------------------------------------
    # API access control
    # -----------------------------------------------------------------------
    API_REQUIRE_STAFF: bool = False
    API_PAGE_SIZE: int = 20

    # -----------------------------------------------------------------------
    # Caching
    # -----------------------------------------------------------------------
    ENABLE_PRINCIPAL_CACHE: bool = False
    PRINCIPAL_CACHE_TTL: int = 300  # seconds

    # -----------------------------------------------------------------------
    # Password hashing for service credentials
    # -----------------------------------------------------------------------
    CLIENT_SECRET_HASHER: str = "default"

    # -----------------------------------------------------------------------
    # Metadata limits
    # -----------------------------------------------------------------------
    MAX_METADATA_SIZE_BYTES: int = 65536  # 64 KB
    MAX_TAGS_COUNT: int = 50

    # -----------------------------------------------------------------------
    # Feature flags
    # -----------------------------------------------------------------------
    ENABLE_AGENT_ACCOUNTS: bool = True
    ENABLE_API_CLIENTS: bool = True
    ENABLE_SERVICE_ACCOUNTS: bool = True

    # -----------------------------------------------------------------------
    # Audit integration (optional, delegates to auditing app if available)
    # -----------------------------------------------------------------------
    AUDIT_PRINCIPAL_CHANGES: bool = True
    AUDIT_BACKEND: str = ""

    # -----------------------------------------------------------------------
    # Custom validators (dotted import paths)
    # -----------------------------------------------------------------------
    PRINCIPAL_VALIDATORS: list[str] = []
    USER_ACCOUNT_VALIDATORS: list[str] = []

    def validate(self) -> tuple[bool, list[str]]:
        """Validate accounts config values semantically."""
        errors: list[str] = []

        if self.USERNAME_MIN_LENGTH < 1:
            errors.append("USERNAME_MIN_LENGTH must be >= 1")

        if self.USERNAME_MAX_LENGTH < self.USERNAME_MIN_LENGTH:
            errors.append("USERNAME_MAX_LENGTH must be >= USERNAME_MIN_LENGTH")

        if self.USERNAME_MAX_LENGTH > 255:
            errors.append("USERNAME_MAX_LENGTH must be <= 255")

        if self.DEFAULT_LOCK_DURATION_MINUTES < 1:
            errors.append("DEFAULT_LOCK_DURATION_MINUTES must be >= 1")

        if self.MAX_FAILED_LOGIN_ATTEMPTS < 1:
            errors.append("MAX_FAILED_LOGIN_ATTEMPTS must be >= 1")

        if self.API_PAGE_SIZE < 1 or self.API_PAGE_SIZE > 1000:
            errors.append("API_PAGE_SIZE must be between 1 and 1000")

        if self.API_CLIENT_SECRET_MIN_LENGTH < 16:
            errors.append("API_CLIENT_SECRET_MIN_LENGTH must be >= 16")

        if self.PRINCIPAL_CACHE_TTL < 0:
            errors.append("PRINCIPAL_CACHE_TTL must be >= 0")

        if self.MAX_METADATA_SIZE_BYTES < 0:
            errors.append("MAX_METADATA_SIZE_BYTES must be >= 0")

        if self.MAX_TAGS_COUNT < 0:
            errors.append("MAX_TAGS_COUNT must be >= 0")

        for kind in self.PRINCIPAL_KINDS:
            if not isinstance(kind, dict) or "value" not in kind or "label" not in kind:
                errors.append(f"Invalid PRINCIPAL_KINDS entry: {kind!r}. Must have 'value' and 'label' keys.")

        return len(errors) == 0, errors


accounts_settings: Final[AccountsSettings] = AccountsSettings()


def _on_setting_changed(sender: object, setting: str, **_: Any) -> None:
    if accounts_settings.is_related_setting(setting):
        accounts_settings.reload()


setting_changed.connect(_on_setting_changed)


def get_accounts_config(key: str, default: Any = None) -> Any:
    """
    Get accounts configuration value.

    Parameters
    ----------
    key : str
        Configuration key (without prefix).
    default : Any
        Default value if not found.

    Returns
    -------
    Any
        Configuration value.
    """
    return accounts_settings.get(key.upper(), default)


def validate_accounts_config() -> tuple[bool, list[str]]:
    """
    Validate accounts configuration.

    Returns
    -------
    tuple[bool, list[str]]
        (is_valid, list_of_errors)
    """
    return accounts_settings.validate()
