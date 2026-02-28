"""
Admin module for accounts app.

Registers admin interfaces for all account-related models:
Principal, UserAccount, ServiceAccount, APIClient, AgentAccount.
"""

from __future__ import annotations

from .agent import AgentAccountAdmin
from .api_client import APIClientAdmin
from .base import BaseAccountsAdmin, ReadOnlyAdminMixin
from .principal import PrincipalAdmin
from .service_account import ServiceAccountAdmin
from .user import UserAccountAdmin

__all__ = [
    "BaseAccountsAdmin",
    "ReadOnlyAdminMixin",
    "PrincipalAdmin",
    "UserAccountAdmin",
    "ServiceAccountAdmin",
    "APIClientAdmin",
    "AgentAccountAdmin",
]
