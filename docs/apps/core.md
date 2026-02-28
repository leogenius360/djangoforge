# `apps/core` — Shared Infrastructure

The `core` app provides the foundational building blocks used by every other app in the project:
base models with composable mixins, bulk-safe querysets, async-safe actor context, health-check
utilities, cryptographic helpers, and cross-cutting middleware.  No business logic lives here;
`core` is purely plumbing.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                      apps/core                       │
│                                                       │
│  models/                                              │
│    mixins.py ──► TimestampMixin                       │
│                  SoftDeleteMixin                      │
│                  BaseActorMixin                       │
│                  LifecycleMixin                       │
│                  ModelOperationsMixin  ◄─ single      │
│                                           save/delete │
│    __init__.py ─► BaseModel                           │
│                   SoftDeleteModel                     │
│                   SoftDeleteActorModel                │
│                   ActorModel                          │
│                   LifecycleModel                      │
│                   EnterpriseModel                     │
│    querysets.py ─► BaseQuerySet                       │
│                    SoftDeleteQuerySetMixin            │
│                    BulkConsistencyQuerySetMixin       │
│    managers.py ─► BaseManager / SoftDeleteManager     │
│                                                       │
│  context.py ──► get/set current actor (contextvars)   │
│  health.py  ──► HealthChecker (db + cache probes)     │
│  security/  ──► crypto helpers (tokens, fingerprint)  │
│  middleware.py ► ActorTrackingMiddleware              │
│  exceptions.py ► OptimisticLockError                  │
│                  LifecycleStateError                   │
│  api/views.py ─► /health/, /live/, /ready/, /startup/ │
└─────────────────────────────────────────────────────┘
```

---

## Base Model Hierarchy

All project models should inherit from one of the concrete base classes below.
Never mix in `TimestampMixin` directly on a project model — use the provided
base classes.

| Class | Inherits from | When to use |
|---|---|---|
| `BaseModel` | `ModelOperationsMixin + TimestampMixin` | Lightweight models, no soft-delete needed |
| `ActorModel` | `BaseModel + BaseActorMixin` | Need `created_by`/`updated_by`, no soft-delete |
| `SoftDeleteModel` | `BaseModel + SoftDeleteMixin` | Soft-delete, no actor fields |
| `SoftDeleteActorModel` | `SoftDeleteModel + BaseActorMixin` | Soft-delete + actor attribution |
| `LifecycleModel` | `SoftDeleteModel + LifecycleMixin` | Lifecycle state machine + soft-delete |
| `EnterpriseModel` | `SoftDeleteActorModel + LifecycleMixin` | Full-featured: timestamps + actor + lifecycle + soft-delete |

### Fields provided by each mixin

#### `TimestampMixin`
| Field | Type | Notes |
|---|---|---|
| `created_at` | `DateTimeField(auto_now_add)` | Set once on INSERT |
| `updated_at` | `DateTimeField(auto_now)` | Updated on every save |

#### `SoftDeleteMixin`
| Field | Type | Notes |
|---|---|---|
| `deleted_at` | `DateTimeField(null)` | Set when soft-deleted |

#### `BaseActorMixin`
| Field | Type | Notes |
|---|---|---|
| `created_by` | `FK → Principal(null)` | Actor who created the row |
| `updated_by` | `FK → Principal(null)` | Actor who last updated the row |

#### `LifecycleMixin`
| Field | Type | Notes |
|---|---|---|
| `is_active` | `BooleanField(default=True)` | Public visibility flag |
| `disabled_at` | `DateTimeField(null)` | When admin-disabled |
| `disabled_by` | `FK → Principal(null)` | Who disabled it |
| `disabled_reason` | `CharField(255)` | Reason for disabling |
| `locked_at` | `DateTimeField(null)` | When security-locked |
| `locked_until` | `DateTimeField(null)` | Expiry of temporary lock |
| `locked_by` | `FK → Principal(null)` | Who/what locked it |
| `locked_reason` | `CharField(255)` | Reason for lock |
| `suspended_at` | `DateTimeField(null)` | When policy-suspended |
| `suspended_by` | `FK → Principal(null)` | Who suspended it |
| `suspended_reason` | `CharField(255)` | Reason for suspension |
| `expires_at` | `DateTimeField(null)` | When the entity expires |

#### `BaseModel` fields (always present)
| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDField(primary_key)` | Auto-generated UUID4 |
| `version` | `PositiveIntegerField(default=1)` | Optimistic locking counter |

---

## Usage Examples

### Defining a model

```python
# apps/projects/models.py
from apps.core.models import EnterpriseModel
from django.db import models


class Project(EnterpriseModel):
    """A project owned by a user."""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        "accounts.Principal",
        on_delete=models.PROTECT,
        related_name="projects",
    )

    class Meta(EnterpriseModel.Meta):
        db_table = "projects"
        ordering = ["-created_at"]
```

### Creating instances with actor context

```python
from apps.core.context import set_current_actor

# All saves inside this block stamp created_by / updated_by automatically
with set_current_actor(request.user):
    project = Project.objects.create(name="New Project", owner=request.user)
```

### Soft-deleting

```python
# Soft-delete (sets deleted_at, does NOT physically remove)
project.soft_delete(actor=request.user)
# Or simply call delete() — ModelOperationsMixin routes to soft_delete
project.delete()

# Physical delete when needed
project.hard_delete()

# Restore
project.restore(actor=admin_principal)

# Check state
print(project.is_deleted)  # True
```

### Bulk operations (queryset)

```python
# BaseQuerySet keeps updated_at + version consistent on bulk updates
Project.objects.filter(owner=user).update(description="Updated")
# ↑ Also bumps `version` and sets `updated_at` (from BulkConsistencyQuerySetMixin)

# Bulk soft-delete
Project.objects.filter(owner=user).soft_delete()

# Bulk restore
Project.objects.filter(owner=user).deleted().restore()
```

### Active / deleted filtering

```python
# Default manager excludes deleted rows
active_projects = Project.objects.all()  # deleted_at IS NULL

# Include deleted rows
with_deleted = Project.objects.with_deleted()

# Only deleted
deleted = Project.objects.with_deleted().deleted()
```

### Lifecycle transitions (LifecycleMixin)

```python
# Lock an object (temporary, e.g. security enforcement)
project.lock(
    actor=admin,
    reason="Policy violation",
    duration=timedelta(hours=2),
)
print(project.is_locked)    # True
print(project.locked_until) # datetime

# Unlock
project.unlock(actor=admin)

# Suspend (administrative, longer-term)
project.suspend(actor=admin, reason="Under review")
print(project.is_suspended) # True

# Disable (permanent administrative action)
project.disable(actor=admin, reason="Account closed")
print(project.is_disabled)  # True

# Expire check
print(project.is_expired)  # True if expires_at < now
```

### Optimistic locking

```python
from apps.core.exceptions import OptimisticLockError

try:
    # Both threads loaded project at version=3
    project.name = "Thread A"
    project.save()   # succeeds: version → 4
except OptimisticLockError:
    # Thread B's version is stale
    project.refresh_from_db()
    project.name = "Thread B"
    project.save()
```

---

## Context: Actor Tracking

`apps.core.context` provides async-safe (`contextvars`) actor storage.  The
`ActorTrackingMiddleware` populates this automatically from `request.user` on
every request.  Model saves then stamp `created_by`/`updated_by` without
passing actors explicitly.

```python
from apps.core.context import (
    get_current_actor,
    set_current_actor,
    require_actor,
    get_system_actor,
    require_system_actor,
    clear_system_actor_cache,
)

# Read current actor (returns None outside request context)
actor = get_current_actor()

# Require an actor — raises ValueError if none present
actor = require_actor()           # reads from context
actor = require_actor(explicit_actor=some_principal)  # explicit wins

# Set actor for a block (context manager, ASGI-safe)
with set_current_actor(request.user):
    obj.save()

# System actor for automated flows (reads CORE_SYSTEM_PRINCIPAL_ID setting)
system = get_system_actor()       # returns None if not configured
system = require_system_actor()   # raises ValueError if not configured

# Clear cache after test changes
clear_system_actor_cache()
```

### Middleware configuration

```python
# config/settings/base.py
MIDDLEWARE = [
    ...
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.ActorTrackingMiddleware",  # must be after AuthenticationMiddleware
    ...
]
```

---

## Health Checks

`HealthChecker` provides reusable database and cache probes.

```python
from apps.core.health import HealthChecker

# Check database
ok, err = HealthChecker.check_database()
# ok: bool, err: str|None (None when healthy)

# Check cache
ok, err = HealthChecker.check_cache(test_key="health_check")
```

### HTTP Endpoints

The health API is mounted at `/health/` (see `config/urls.py`):

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health/` | None | Full health check (DB + cache) |
| `GET` | `/health/live/` | None | Kubernetes liveness probe |
| `GET` | `/health/ready/` | None | Kubernetes readiness probe |
| `GET` | `/health/startup/` | None | Kubernetes startup probe |

**Response — healthy (200):**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00+00:00",
  "database": "connected",
  "cache": "connected"
}
```

**Response — unhealthy (503):**
```json
{
  "status": "unhealthy",
  "timestamp": "2024-01-15T10:30:00+00:00",
  "database": "error",
  "database_error": "connection refused",
  "cache": "connected"
}
```

> **Note:** `database_error` / `cache_error` keys only appear when `DEBUG=True`
> or the requesting user is an authenticated staff member.

---

## Cryptographic Utilities

`apps.core.security.crypto` provides token generation and fingerprinting helpers.

```python
from apps.core.security.crypto import (
    generate_secure_token,
    generate_fingerprint,
    constant_time_compare,
)

# Generate a URL-safe random token (default 32 bytes → ~43 chars)
token = generate_secure_token()          # "xZ8k-GcJ3R..."
token = generate_secure_token(length=16) # shorter token

# SHA-256 fingerprint of non-sensitive data
checksum = generate_fingerprint("file contents here")
# "1307990e6ba5ca145eb35e99182a9bec46531bc54ddf656a602c780fa0240dee"

# Constant-time string comparison (timing-attack safe)
safe_equal = constant_time_compare(token_a, token_b)
```

> **WARNING:** Never use `generate_fingerprint` for password hashing.
> Use Django's password hashers (`make_password` / `check_password`) instead.

---

## Management Commands

### `wait_for_db`

Waits for the database to be ready before starting the app (useful in Docker
Compose startup sequences).

```bash
python manage.py wait_for_db
# Retries with exponential back-off until the DB accepts connections
```

---

## Exceptions

```
apps.core.exceptions
├── OptimisticLockError   — raised by ModelOperationsMixin when version conflicts
├── LifecycleStateError   — raised when lifecycle fields are incoherent
└── LifecycleTransitionError — raised when a state transition is not allowed
```

```python
from apps.core.exceptions import (
    OptimisticLockError,
    LifecycleStateError,
    LifecycleTransitionError,
)

try:
    instance.save()
except OptimisticLockError:
    # Concurrent modification detected; refresh and retry
    instance.refresh_from_db()
```

---

## Configuration

```python
# config/settings/base.py

# System actor for automated operations (optional)
CORE_SYSTEM_PRINCIPAL_ID = "550e8400-e29b-41d4-a716-446655440000"

# Enforce actor attribution on every model save (optional, default: False)
CORE_ENFORCE_ACTOR = False

# Default lock duration used by LifecycleMixin.lock() when none specified
CORE_DEFAULT_LOCK_DURATION_MINUTES = 30
```

---

## Testing Examples

```python
import pytest
from apps.core.context import set_current_actor
from apps.core.models import SoftDeleteModel
from django.db import models


class SampleModel(SoftDeleteModel):
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "tests"


@pytest.mark.django_db
def test_soft_delete(db, user_principal):
    with set_current_actor(user_principal):
        obj = SampleModel.objects.create(name="test")
        assert not obj.is_deleted

        obj.soft_delete(actor=user_principal)
        obj.refresh_from_db()
        assert obj.is_deleted
        assert obj.deleted_at is not None

        # Default manager excludes it
        assert not SampleModel.objects.filter(pk=obj.pk).exists()
        # with_deleted includes it
        assert SampleModel.objects.with_deleted().filter(pk=obj.pk).exists()


@pytest.mark.django_db
def test_health_check():
    from apps.core.health import HealthChecker
    ok, err = HealthChecker.check_database()
    assert ok is True
    assert err is None
```
