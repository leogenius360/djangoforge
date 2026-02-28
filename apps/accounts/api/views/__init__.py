"""
Views for the accounts app.

Exposes CRUD views for the Principal root model and all concrete
principal subtypes.  No re-exports from authn or sessions apps.
"""

from __future__ import annotations

from .agent import AgentAccountDetailView, AgentAccountListCreateView
from .api_client import APIClientDetailView, APIClientListCreateView
from .principal import PrincipalDetailView, PrincipalListCreateView
from .service_account import ServiceAccountDetailView, ServiceAccountListCreateView
from .user import UserAccountDetailView, UserAccountListView

__all__ = [
    # Principal (root model)
    "PrincipalListCreateView",
    "PrincipalDetailView",
    # User
    "UserAccountListView",
    "UserAccountDetailView",
    # Service account
    "ServiceAccountListCreateView",
    "ServiceAccountDetailView",
    # API client
    "APIClientListCreateView",
    "APIClientDetailView",
    # Agent
    "AgentAccountListCreateView",
    "AgentAccountDetailView",
]
