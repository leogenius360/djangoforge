"""
Serializers for the accounts app.

Includes serializers for the Principal root model and all concrete
principal subtypes (user, service account, API client, agent).
"""

from __future__ import annotations

from .agent import AgentAccountCreateSerializer, AgentAccountSerializer
from .api_client import APIClientCreateSerializer, APIClientSerializer
from .principal import PrincipalCreateSerializer, PrincipalPublicSerializer, PrincipalSerializer
from .service_account import ServiceAccountCreateSerializer, ServiceAccountSerializer
from .user import UserAccountCreateSerializer, UserAccountPublicSerializer, UserAccountSerializer

__all__ = [
    # Principal (root model)
    "PrincipalSerializer",
    "PrincipalCreateSerializer",
    "PrincipalPublicSerializer",
    # User
    "UserAccountSerializer",
    "UserAccountCreateSerializer",
    "UserAccountPublicSerializer",
    # Service account
    "ServiceAccountSerializer",
    "ServiceAccountCreateSerializer",
    # API client
    "APIClientSerializer",
    "APIClientCreateSerializer",
    # Agent
    "AgentAccountSerializer",
    "AgentAccountCreateSerializer",
]
