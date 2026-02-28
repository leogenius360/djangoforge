"""
URL configuration for accounts app.

Provides endpoints for the Principal root model and all concrete subtypes:
- Principal      (list / detail — root authentication entity)
- UserAccount    (list / detail)
- ServiceAccount (list-create / detail)
- APIClient      (list-create / detail)
- AgentAccount   (list-create / detail)

Authentication workflows (login, registration, MFA) belong in the authn app.
Session management belongs in the sessions app.
Profile management belongs in the profiles app.
"""

from django.urls import path

from .views import (
    AgentAccountDetailView,
    AgentAccountListCreateView,
    APIClientDetailView,
    APIClientListCreateView,
    PrincipalDetailView,
    PrincipalListCreateView,
    ServiceAccountDetailView,
    ServiceAccountListCreateView,
    UserAccountDetailView,
    UserAccountListView,
)

app_name = "accounts"

urlpatterns = [
    # ===== PRINCIPALS (root model) =====
    path("", PrincipalListCreateView.as_view(), name="principal-list"),
    path("<uuid:pk>/", PrincipalDetailView.as_view(), name="principal-detail"),
    # ===== USER ACCOUNTS =====
    path("users/", UserAccountListView.as_view(), name="user-list"),
    path("users/<uuid:pk>/", UserAccountDetailView.as_view(), name="user-detail"),
    # ===== SERVICE ACCOUNTS =====
    path("service-accounts/", ServiceAccountListCreateView.as_view(), name="service-account-list"),
    path("service-accounts/<uuid:pk>/", ServiceAccountDetailView.as_view(), name="service-account-detail"),
    # ===== API CLIENTS =====
    path("api-clients/", APIClientListCreateView.as_view(), name="api-client-list"),
    path("api-clients/<uuid:pk>/", APIClientDetailView.as_view(), name="api-client-detail"),
    # ===== AGENTS =====
    path("agents/", AgentAccountListCreateView.as_view(), name="agent-list"),
    path("agents/<uuid:pk>/", AgentAccountDetailView.as_view(), name="agent-detail"),
]
