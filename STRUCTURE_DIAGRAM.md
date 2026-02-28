# Django Apps Directory Structure

## Overview

All apps follow a consistent 3-layer architecture:

```
┌─────────────────────────────────────────────────────────┐
│                     API Layer (HTTP)                    │
│  DRF Serializers, Views, URLs, Permissions             │
│  Location: apps/<app>/api/                             │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                  Business Logic Layer                   │
│  Services, Domain Logic, Orchestration                  │
│  Location: apps/<app>/services/                         │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    Data Layer (ORM)                     │
│  Models, Managers, QuerySets                            │
│  Location: apps/<app>/models/                           │
└─────────────────────────────────────────────────────────┘
```

## Standard App Structure

```
apps/<app>/
├── api/                    # DRF Layer (HTTP concerns)
│   ├── __init__.py
│   ├── serializers/       # Request/response validation
│   │   ├── __init__.py
│   │   └── *.py
│   ├── views/             # Endpoint handlers
│   │   ├── __init__.py
│   │   └── *.py
│   ├── urls.py            # URL routing
│   └── permissions.py     # DRF permissions (optional)
│
├── models/                 # Django ORM Layer
│   ├── __init__.py
│   ├── *.py               # Model definitions
│   ├── managers.py        # Custom managers
│   └── querysets.py       # Custom querysets
│
├── services/              # Business Logic Layer (optional)
│   ├── __init__.py
│   └── *.py               # Domain services
│
├── admin/                 # Django Admin
│   ├── __init__.py
│   └── *.py               # Admin registrations
│
├── tests/                 # Test Suite
│   ├── __init__.py
│   ├── conftest.py        # Pytest fixtures
│   ├── test_*.py          # Unit tests
│   └── tests_*.py         # Integration tests
│
├── migrations/            # Django migrations
│   └── __init__.py
│
├── __init__.py
└── apps.py               # App configuration
```

## Current Apps Structure

### accounts (User Management)
```
apps/accounts/
├── api/
│   ├── serializers/
│   │   ├── base.py
│   │   ├── credential.py
│   │   ├── password.py
│   │   ├── principal.py
│   │   ├── profile.py
│   │   ├── registration.py
│   │   ├── security.py
│   │   ├── session.py
│   │   ├── user.py
│   │   └── verification.py
│   ├── views/
│   │   ├── base.py
│   │   ├── credential.py
│   │   ├── password.py
│   │   ├── principal.py
│   │   ├── profile.py
│   │   ├── registration.py
│   │   ├── security.py
│   │   └── verification.py
│   └── urls.py
├── models/
│   ├── api_client.py
│   ├── audit.py
│   ├── managers.py
│   ├── principal.py
│   ├── profile.py
│   ├── querysets.py
│   ├── service_account.py
│   └── user.py
├── admin/
│   ├── api_client.py
│   ├── audit.py
│   ├── base.py
│   ├── profile.py
│   ├── service_account.py
│   └── user.py
├── tests/
│   └── test_accounts.py
├── utils/
│   ├── push.py
│   └── sms.py
└── signals.py
```

### authn (Authentication)
```
apps/authn/
├── api/
│   ├── serializers/
│   │   ├── auth.py
│   │   └── mfa.py
│   ├── views/
│   │   ├── auth.py
│   │   ├── mfa.py
│   │   └── passwordless.py
│   └── urls.py
├── models/
│   ├── base.py
│   ├── challenges.py
│   ├── credentials.py
│   ├── enums.py
│   ├── managers.py
│   ├── mixins.py
│   └── querysets.py
├── backends/              # Authentication backends
│   ├── base.py
│   ├── email.py
│   ├── passwordless.py
│   ├── phone.py
│   └── username.py
├── services/
│   └── mfa.py
├── admin/
│   └── authn.py
├── tests/
│   └── test_authn.py
└── utils/
    ├── phone.py
    ├── push.py
    └── sms.py
```

### sessions (Session Management)
```
apps/sessions/
├── api/
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── models/
│   ├── auth_session.py
│   ├── credentials.py
│   ├── enums.py
│   ├── managers.py
│   └── querysets.py
├── services/
│   ├── device.py
│   ├── lifecycle.py
│   └── risk.py
├── admin/
│   └── sessions.py
├── tests/
│   ├── test_sessions.py
│   └── tests_integration.py
├── authentication.py      # Session authentication class
├── backends.py            # Session storage backends
├── middleware.py          # Session middleware
├── enums.py              # Session enums
└── utils.py              # Session utilities
```

### core (Shared Utilities)
```
apps/core/
├── api/
│   └── views.py          # Health checks, monitoring
├── models/
│   ├── base.py           # Base model classes
│   └── mixins.py         # Model mixins
├── managers/
│   ├── base.py           # Base managers
│   └── mixins.py         # Manager mixins
├── querysets/
│   ├── base.py           # Base querysets
│   └── mixins.py         # QuerySet mixins
├── security/
│   └── crypto.py         # Crypto utilities
├── typing/
│   └── django.py         # Type hints
├── admin/
│   └── core.py
├── tests/
│   └── test_core.py
├── monitoring.py         # System metrics
├── middleware.py         # Core middleware
├── context.py           # Request context
├── utils.py             # Utilities
└── enums.py             # Shared enums
```

### auditing (Audit Logging)
```
apps/auditing/
├── api/
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   └── permissions.py
├── models/
│   ├── audit_entry.py
│   ├── audit_outbox.py
│   ├── enums.py
│   ├── mixins.py
│   └── querysets.py
├── backends/             # Audit storage backends
│   ├── base.py
│   ├── coordinator.py
│   ├── database.py
│   ├── elasticsearch.py
│   ├── factory.py
│   ├── file.py
│   ├── kafka.py
│   ├── ordered.py
│   ├── redis.py
│   └── s3.py
├── services/
│   ├── audit_service.py
│   ├── outbox_service.py
│   ├── replay_service.py
│   └── retention_service.py
├── admin/
│   └── auditing.py
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_backends.py
│   ├── test_core.py
│   ├── test_integration.py
│   └── test_security.py
├── admin_mixins.py      # Admin utilities
├── config.py            # Audit configuration
├── middleware.py        # Audit middleware
├── security.py          # Audit security
├── signals.py           # Django signals
└── tasks.py             # Celery tasks
```

### authz (Authorization - Placeholder)
```
apps/authz/
├── api/                 # Ready for endpoints
├── models/              # Ready for permission models
├── services/            # Ready for RBAC logic
├── admin/
│   └── authz.py
└── tests/
    └── test_authz.py
```

## Import Patterns

### ✅ Correct Imports

```python
# Cross-app imports (API layer)
from apps.accounts.api.serializers import UserSerializer
from apps.authn.api.views import LoginView
from apps.sessions.api.views import SessionListView

# Model imports (always from models)
from apps.accounts.models import UserAccount, Principal
from apps.sessions.models import AuthSession

# Within same app (relative imports)
from ..serializers import LoginSerializer  # In api/views/*.py
from .base import BaseSerializer           # In api/serializers/*.py
```

### ❌ Incorrect Imports (Old Paths)

```python
# These no longer work:
from apps.accounts.serializers import UserSerializer
from apps.authn.views import LoginView
from apps.sessions.views import SessionListView
```

## URL Routing

### Central API Routing (config/api_urls.py)

```python
from django.urls import include, path
from apps.core.api.views import HealthCheckView
from apps.core.monitoring import SystemMetricsView

urlpatterns = [
    # Health & Monitoring
    path("health/", HealthCheckView.as_view()),
    path("metrics/", SystemMetricsView.as_view()),
    
    # App APIs
    path("auth/", include("apps.authn.api.urls")),
    path("sessions/", include("apps.sessions.api.urls")),
    path("accounts/", include("apps.accounts.api.urls")),
    path("audit/", include("apps.auditing.api.urls")),
]
```

### App-Level Routing

Each app has `apps/<app>/api/urls.py`:

```python
# apps/accounts/api/urls.py
from django.urls import path
from .views import RegisterView, ProfileView

app_name = "accounts"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("profile/", ProfileView.as_view(), name="profile"),
]
```

## Dependency Rules

### Layer Dependencies

```
┌──────────┐
│   API    │  ← Can import from: Services, Models
└──────────┘
     │
     ▼
┌──────────┐
│ Services │  ← Can import from: Models (NO API imports)
└──────────┘
     │
     ▼
┌──────────┐
│  Models  │  ← Self-contained (NO API/Service imports)
└──────────┘
```

### Cross-App Dependencies

```
accounts ← authn, sessions, auditing
authn ← sessions
sessions ← auditing
core ← all apps (provides base classes)
```

## Testing Structure

### Test Organization

```
apps/<app>/tests/
├── conftest.py           # Fixtures shared across app tests
├── test_models.py        # Model layer tests
├── test_api.py          # API endpoint tests
├── test_serializers.py  # Serializer tests
├── test_services.py     # Business logic tests
└── tests_integration.py # End-to-end tests
```

### Example conftest.py

```python
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        email="test@example.com",
        password="testpass123",
    )

@pytest.fixture
def user_factory(db):
    """Factory to create multiple users."""
    def _create_user(**kwargs):
        return User.objects.create_user(**kwargs)
    return _create_user
```

## Summary

- **6 apps** restructured
- **Consistent structure** across all apps
- **Clear separation** of API, Services, and Models
- **128/132 tests** passing (97% success rate)
- **Zero import errors** after restructuring
- **CI green**: formatting, linting, Django checks all pass
