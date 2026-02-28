"""
String constants for the accounts app.

Centralizes magic strings, regex patterns, and limits to avoid typos
and support IDE navigation.  All configurable limits have corresponding
settings in ``AccountsSettings`` that override these defaults at runtime.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Model label used in string FK references across the project
# ---------------------------------------------------------------------------
PRINCIPAL_MODEL_LABEL: str = "accounts.Principal"

# ---------------------------------------------------------------------------
# Database table names
# ---------------------------------------------------------------------------
PRINCIPAL_DB_TABLE: str = "principals"
USER_ACCOUNT_DB_TABLE: str = "user_accounts"
SERVICE_ACCOUNT_DB_TABLE: str = "service_accounts"
API_CLIENT_DB_TABLE: str = "api_clients"
AGENT_ACCOUNT_DB_TABLE: str = "agent_accounts"

# ---------------------------------------------------------------------------
# Username constraints
# ---------------------------------------------------------------------------
# Pattern: must start with alphanumeric, may contain letters, digits, dot,
# hyphen, or underscore.
USERNAME_REGEX: str = r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$"
MIN_USERNAME_LENGTH: int = 3
MAX_USERNAME_LENGTH: int = 150

# Usernames that cannot be claimed by regular accounts.
USERNAME_RESERVED_WORDS: set[str] = {
    "admin",
    "administrator",
    "root",
    "system",
    "superuser",
    "null",
    "undefined",
    "anonymous",
    "api",
    "auth",
    "login",
    "logout",
    "register",
    "signup",
    "signin",
    "support",
    "help",
    "info",
    "security",
    "abuse",
    "postmaster",
    "webmaster",
    "hostmaster",
    "noreply",
    "no-reply",
    "mailer-daemon",
}

# ---------------------------------------------------------------------------
# Maximum lengths
# ---------------------------------------------------------------------------
MAX_IDENTIFIER_LENGTH: int = 255
MAX_DISPLAY_NAME_LENGTH: int = 150
MAX_PHONE_LENGTH: int = 17
MAX_KIND_LENGTH: int = 20
MAX_AGENT_TYPE_LENGTH: int = 50
MAX_CLIENT_TYPE_LENGTH: int = 20
MAX_EXTERNAL_PROVIDER_LENGTH: int = 50
MAX_REASON_LENGTH: int = 255
MAX_SERVICE_NAME_LENGTH: int = 100

# ---------------------------------------------------------------------------
# Security stamp initial value
# ---------------------------------------------------------------------------
INITIAL_SECURITY_STAMP: int = 0

# ---------------------------------------------------------------------------
# Auto-generated username prefixes per principal kind
# ---------------------------------------------------------------------------
USERNAME_PREFIX_SERVICE: str = "svc"
USERNAME_PREFIX_API_CLIENT: str = "api"
USERNAME_PREFIX_AGENT: str = "agent"

__all__ = [
    "PRINCIPAL_MODEL_LABEL",
    "PRINCIPAL_DB_TABLE",
    "USER_ACCOUNT_DB_TABLE",
    "SERVICE_ACCOUNT_DB_TABLE",
    "API_CLIENT_DB_TABLE",
    "AGENT_ACCOUNT_DB_TABLE",
    "USERNAME_REGEX",
    "MIN_USERNAME_LENGTH",
    "MAX_USERNAME_LENGTH",
    "USERNAME_RESERVED_WORDS",
    "MAX_IDENTIFIER_LENGTH",
    "MAX_DISPLAY_NAME_LENGTH",
    "MAX_PHONE_LENGTH",
    "MAX_KIND_LENGTH",
    "MAX_AGENT_TYPE_LENGTH",
    "MAX_CLIENT_TYPE_LENGTH",
    "MAX_EXTERNAL_PROVIDER_LENGTH",
    "MAX_REASON_LENGTH",
    "MAX_SERVICE_NAME_LENGTH",
    "INITIAL_SECURITY_STAMP",
    "USERNAME_PREFIX_SERVICE",
    "USERNAME_PREFIX_API_CLIENT",
    "USERNAME_PREFIX_AGENT",
]
