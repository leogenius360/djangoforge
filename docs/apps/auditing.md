# `apps/auditing` — Immutable Audit Trail

Append-only audit log using event sourcing.  Provides tamper-evident,
versioned history for any Django model with optional secondary dispatch to
file, Redis, or Kafka backends via a transactional outbox pattern.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      apps/auditing                            │
│                                                               │
│  models/                                                      │
│    base.py    BaseEvent (immutable core fields)               │
│    event.py   Event (actor + outbox fields)                   │
│    mixins.py  AuditableModelMixin (auto-audit on save/delete) │
│    managers.py  EventManager / EventQuerySet                  │
│                                                               │
│  services/__init__.py                                         │
│    create_audit_entry()   ◄─── primary write API             │
│    serialize_model_state()                                    │
│    get_object_history()                                       │
│    get_version()                                              │
│    undo_change() / redo_change()                              │
│                                                               │
│  registry.py   AuditRegistry + AuditModelConfig               │
│  context.py    contextvars (actor, session, ip, user_agent)   │
│  middleware.py AuditingMiddleware (populates context)         │
│                                                               │
│  backends/                                                    │
│    base.py        AuditBackend interface                      │
│    file.py        JSON-lines file sink                        │
│    redis.py       Redis pub/sub sink                          │
│    kafka.py       Kafka topic sink                            │
│    coordinator.py Multi-backend coordinator                   │
│    factory.py     get_configured_backends()                   │
│                                                               │
│  utils/                                                       │
│    serialization.py  model_to_dict, compute_delta            │
│    integrity.py      IntegrityService (chained checksums)     │
│    compression.py    Compression helpers (zlib / lz4)         │
│                                                               │
│  api/                                                         │
│    views/events.py  EventListView, ObjectHistoryView, ...     │
│    urls.py          /api/audit/                               │
│                                                               │
│  enums.py     EventType                                       │
│  exceptions.py  UndoNotAllowedError, ...                      │
└──────────────────────────────────────────────────────────────┘

Event chain for a single object:
  v1 (CREATE) ─► v2 (UPDATE) ─► v3 (UPDATE) ─► v4 (DELETE)
  checksum₁       checksum₂      checksum₃      checksum₄
  (includes       (includes      (includes      (includes
  parent=""       parent=v1      parent=v2      parent=v3
  hash)           hash)          hash)          hash)
```

---

## Core Concepts

### Immutability

Core event fields (`event_type`, `state`, `delta`, `checksum`, `actor`,
`content_type`, `object_id`, `version`, `parent`, `context`) are **immutable
after creation**.  Only outbox-tracking fields (`backends_pending`,
`backends_dispatched`, `backends_failed`) are mutable.

### Versioning

Each audited object has an independent `version` sequence starting at 1.
Events for the same object are chained via the `parent` FK.

### Tamper-evident chains

When `INTEGRITY_ENABLED=True`, each event's checksum is computed from its
immutable payload plus the parent's checksum.  This creates a hash chain
where any modification to a historical event is detectable.

### Transactional outbox

After the `Event` row commits to the database, backend dispatch runs via
`transaction.on_commit`.  The outbox fields track dispatch status per backend,
enabling at-least-once delivery semantics.

---

## Models

### `BaseEvent`

Abstract base with all immutable core fields.

| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDField(pk)` | |
| `content_type` | `FK → ContentType` | The audited model type |
| `object_id` | `CharField(255)` | Audited object PK (string-encoded) |
| `event_type` | `CharField(20)` | `create` / `update` / `delete` / `undo` / `redo` / `custom` |
| `version` | `PositiveIntegerField` | Per-object sequence number |
| `parent` | `FK → self(null)` | Previous event in the chain |
| `parent_checksum` | `CharField(64)` | Checksum of parent (for chain validation) |
| `state` | `JSONField(null)` | Full snapshot at this version (or compressed) |
| `snapshot` | `BinaryField(null)` | Compressed snapshot bytes (when compression enabled) |
| `snapshot_compressed` | `BooleanField` | Whether snapshot is compressed |
| `compression_algorithm` | `CharField` | `zlib` / `lz4` / `""` |
| `delta` | `JSONField(null)` | `{field: new_value}` for UPDATE events |
| `checksum` | `CharField(64)` | Integrity hash (SHA-256 of payload + parent) |
| `context` | `JSONField(dict)` | Request metadata (ip_address, user_agent, request_id) |
| `comment` | `TextField` | Human-readable annotation |
| `created_at` | `DateTimeField` | Immutable event timestamp |

### `Event`

Extends `BaseEvent` with actor attribution and outbox fields.

**Table:** `auditing_event`

| Additional Field | Type | Notes |
|---|---|---|
| `actor` | `FK → Principal(null)` | Who triggered this event |
| `backends_pending` | `JSONField(list)` | Backend names not yet dispatched |
| `backends_dispatched` | `JSONField(dict)` | `{backend: ISO-timestamp}` |
| `backends_failed` | `JSONField(dict)` | `{backend: {error, attempts}}` |

**Convenience properties:**
```python
event.is_fully_dispatched   # backends_pending is empty
event.has_dispatch_failures # backends_failed is not empty
event.ip_address            # context["ip_address"]
event.user_agent            # context["user_agent"]
event.request_id            # context["request_id"]
```

**Instance methods:**
```python
# Get full state snapshot at this version (reconstructs from deltas if needed)
state = event.get_snapshot()      # dict | None

# Reconstruct from deltas since last snapshot
state = event.reconstruct_snapshot()

# Verify this event's integrity (raises IntegrityVerificationError if tampered)
event.verify_integrity()

# Check undo eligibility
event.assert_can_undo()  # raises UndoNotAllowedError if not eligible

# Children events (undo/redo events that reference this one)
children = event.children.all()
```

---

## Enabling Auditing

### Option A: `AuditableModelMixin` (automatic)

```python
from apps.auditing.models.mixins import AuditableModelMixin
from django.db import models


class Project(AuditableModelMixin, models.Model):
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=20)
    owner = models.ForeignKey("accounts.Principal", on_delete=models.PROTECT)

    class Audit:
        track_fields = ["name", "status"]   # empty set = track all fields
        exclude_fields = ["internal_note"]  # always excluded
        snapshot_interval = 5               # full snapshot every 5 versions
```

The mixin automatically emits:
- `create` events when a new instance is saved for the first time
- `update` events on subsequent saves (captures `pre_state` before saving)
- `delete` events before deletion (captures final snapshot)

### Option B: Manual service calls

```python
from apps.auditing.services import (
    create_audit_entry,
    serialize_model_state,
)
from apps.auditing.enums import EventType

# Before the change
pre_state = serialize_model_state(instance)

# Make the change
instance.status = "active"
instance.save()

# After the change
post_state = serialize_model_state(instance)
create_audit_entry(
    instance=instance,
    event_type=EventType.UPDATE,
    state=post_state,
    pre_state=pre_state,  # enables delta computation
    actor=request.user,
    comment="Status changed to active",
)
```

---

## Service API

### `create_audit_entry`

```python
from apps.auditing.services import create_audit_entry
from apps.auditing.enums import EventType

event = create_audit_entry(
    instance=my_object,
    event_type=EventType.CREATE,     # or UPDATE / DELETE / CUSTOM
    state=serialize_model_state(my_object),
    actor=request.user,              # optional; falls back to context actor
    pre_state=None,                  # pass for UPDATE to get delta
    comment="Created by API",
)
print(event.version)   # 1
print(event.checksum)  # SHA-256 hex
```

### `serialize_model_state`

```python
from apps.auditing.services import serialize_model_state

# Uses registry config (track_fields, exclude_fields) automatically
state = serialize_model_state(instance)
# {"pk": "uuid", "name": "Project X", "status": "active", ...}

# Override field selection
state = serialize_model_state(
    instance,
    track_fields=["name", "status"],
    exclude_fields=["internal_note"],
)
```

### `get_object_history`

```python
from apps.auditing.services import get_object_history

history = get_object_history(Project, pk="550e8400-e29b-41d4-a716-446655440000")
# Returns list[Event] ordered by version ASC

for event in history:
    print(f"v{event.version}: {event.event_type} by {event.actor}")
    print(f"  delta: {event.delta}")
```

### `get_version`

```python
from apps.auditing.services import get_version

# Get the state of an object at a specific version
state = get_version(Project, pk="550e8400...", version_number=3)
# Returns dict (reconstructed from snapshots + deltas) or None
```

### `undo_change` / `redo_change`

```python
from apps.auditing.services import undo_change, redo_change

# Get the event you want to undo
event = Event.objects.get(pk="...")

# Undo (creates UNDO event, restores model to previous state)
undo_event = undo_change(event)

# Redo (creates REDO event, re-applies the original state)
redo_event = redo_change(event)
```

---

## Registry

The audit registry maps model classes to their per-model configuration.

```python
from apps.auditing.registry import audit_registry

# Check if a model is audited
if audit_registry.should_audit_model(Project):
    ...

# Get per-model config
config = audit_registry.get_config(Project)
if config:
    print(config.track_fields)
    print(config.exclude_fields)
    print(config.snapshot_interval)

# Manually register a model (done automatically by AuditableModelMixin)
audit_registry.register(
    model_class=Project,
    track_fields={"name", "status"},
    exclude_fields={"internal_note"},
    snapshot_interval=10,
)
```

---

## Request Context

`AuditingMiddleware` captures request metadata into contextvars for every request:

```python
from apps.auditing.context import (
    get_current_actor,
    get_current_session,
    get_current_ip_address,
    get_current_user_agent,
    get_current_request_id,
)

# These are set automatically by AuditingMiddleware
actor = get_current_actor()      # authenticated user
session = get_current_session()  # session key
ip = get_current_ip_address()    # client IP
ua = get_current_user_agent()    # browser/client
rid = get_current_request_id()   # correlation ID
```

### Middleware configuration

```python
# config/settings/base.py
MIDDLEWARE = [
    ...
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.auditing.middleware.AuditingMiddleware",  # after AuthenticationMiddleware
    ...
]
```

---

## Integrity Verification

```python
from apps.auditing.utils.integrity import IntegrityService

svc = IntegrityService()

# Verify a single event
try:
    event.verify_integrity()
    print("Event is intact")
except IntegrityVerificationError as e:
    print(f"Tamper detected: {e}")

# Verify all events for an object
events = Event.objects.filter(content_type=ct, object_id=object_id)
for event in events:
    try:
        event.verify_integrity()
    except IntegrityVerificationError:
        alert_security_team(event)

# Compute hash (used internally)
result = svc.hash_event_payload(
    payload=event._integrity_payload(),
    parent_checksum=event.parent_checksum,
)
print(result.digest)  # SHA-256 hex string
```

---

## Backends

Secondary dispatch after the primary DB write.

### File backend

```python
AUDITING = {
    "BACKENDS": ["file"],
    "BACKEND_OPTIONS": {
        "file": {
            "path": "logs/audit",
            "rotate_daily": True,
            "compress": False,
        },
    },
}
```

### Redis backend

```python
AUDITING = {
    "BACKENDS": ["redis"],
    "BACKEND_OPTIONS": {
        "redis": {
            "url": "redis://localhost:6379/0",
            "channel": "audit_events",
        },
    },
}
```

### Kafka backend

```python
AUDITING = {
    "BACKENDS": ["kafka"],
    "BACKEND_OPTIONS": {
        "kafka": {
            "bootstrap_servers": "kafka:9092",
            "topic": "audit-events",
        },
    },
}
```

### Custom backend

```python
from apps.auditing.backends.base import AuditBackend

class MyCustomBackend(AuditBackend):
    name = "my_custom"

    def dispatch(self, event_data: dict) -> None:
        # Forward to your SIEM, data warehouse, etc.
        my_siem_client.ingest(event_data)

    def serialize_event(self, event) -> dict:
        return {
            "id": str(event.pk),
            "type": event.event_type,
            "object": event.object_id,
            "actor": str(event.actor_id),
            "timestamp": event.created_at.isoformat(),
        }
```

---

## API Endpoints

All endpoints are prefixed with `/api/audit/`.  All endpoints are **staff-only**
and **read-only** to preserve immutability.

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/events/` | Staff | List all audit events (filterable) |
| `GET` | `/events/<uuid>/` | Staff | Get event detail |
| `GET` | `/history/` | Staff | Object history (by content_type + object_id) |
| `GET` | `/version/` | Staff | State at a specific version |

**List events (GET `/api/audit/events/`):**
```
GET /api/audit/events/?actor=<uuid>&event_type=update&page=1
Authorization: Bearer <staff-token>
```
```json
{
  "count": 1532,
  "next": "/api/audit/events/?page=2",
  "results": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "event_type": "update",
      "version": 5,
      "object_id": "550e8400-e29b-41d4-a716-446655440001",
      "content_type": "projects.project",
      "actor": "550e8400-e29b-41d4-a716-446655440002",
      "delta": {"status": "active"},
      "checksum": "abc123...",
      "context": {
        "ip_address": "203.0.113.42",
        "user_agent": "Mozilla/5.0...",
        "request_id": "req_xyz"
      },
      "comment": "",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

**Object history (GET `/api/audit/history/`):**
```
GET /api/audit/history/?content_type=projects.project&object_id=<uuid>
```

**State at version (GET `/api/audit/version/`):**
```
GET /api/audit/version/?content_type=projects.project&object_id=<uuid>&version=3
```
```json
{
  "version": 3,
  "state": {
    "pk": "550e8400-...",
    "name": "Old Project Name",
    "status": "draft"
  }
}
```

---

## Configuration

```python
# config/settings/base.py
AUDITING = {
    "ENABLED": True,

    # What to audit
    "AUDITED_APPS": ["accounts"],           # all models in these apps
    "AUDITED_MODELS": {
        "accounts.UserAccount": {
            "track_fields": ["email", "status"],
        },
    },
    "EXCLUDED_MODELS": ["admin.LogEntry"],

    # Outbox backends
    "BACKENDS": ["file"],
    "BACKEND_OPTIONS": {
        "file": {"path": "logs/audit", "rotate_daily": True, "compress": False},
    },

    # Snapshots / deltas
    "TRACK_DELTAS": True,
    "SNAPSHOT_ON_CREATE": True,
    "SNAPSHOT_ON_DELETE": True,
    "SNAPSHOT_INTERVAL": 10,   # 0 = always store full snapshot

    # Integrity
    "INTEGRITY_ENABLED": True,
    "INTEGRITY_ALGORITHM": "sha256",

    # Compression (for large state snapshots)
    "COMPRESSION_ENABLED": False,
    "COMPRESSION_ALGORITHM": "zlib",
    "COMPRESSION_THRESHOLD": 10240,  # compress snapshots > 10 KB

    # Security/compliance
    "GLOBAL_EXCLUDE_FIELDS": ["password", "token", "secret", "key"],

    # Undo/redo
    "UNDO_ENABLED": True,
    "MAX_UNDO_DEPTH": 10,

    # Retention
    "RETENTION_DAYS": None,  # None = keep forever
}
```

> **Note:** Unknown keys raise `ImproperlyConfigured`.

---

## `EventType` Enum

```python
from apps.auditing.enums import EventType

EventType.CREATE   # "create"
EventType.UPDATE   # "update"
EventType.DELETE   # "delete"
EventType.UNDO     # "undo"
EventType.REDO     # "redo"
EventType.CUSTOM   # "custom"

EventType.deletion_types()  # frozenset of terminal event types
```

---

## Exception Hierarchy

```
AuditingError
├── IntegrityVerificationError  — checksum mismatch (tampering detected)
├── UndoNotAllowedError         — event cannot be undone
└── BackendDispatchError        — secondary backend failed
```

---

## Testing Examples

```python
import pytest
from apps.auditing.services import (
    create_audit_entry,
    serialize_model_state,
    get_object_history,
    get_version,
)
from apps.auditing.enums import EventType
from apps.auditing.models.event import Event


@pytest.mark.django_db
def test_create_audit_entry(project, user_principal):
    state = serialize_model_state(project)
    event = create_audit_entry(
        instance=project,
        event_type=EventType.CREATE,
        state=state,
        actor=user_principal,
        comment="Created via test",
    )
    assert event.version == 1
    assert event.event_type == "create"
    assert event.actor == user_principal
    assert event.checksum != ""


@pytest.mark.django_db
def test_audit_chain(project, user_principal):
    # Create
    state_v1 = serialize_model_state(project)
    create_audit_entry(project, EventType.CREATE, state_v1, actor=user_principal)

    # Update
    pre_state = serialize_model_state(project)
    project.name = "Updated Name"
    project.save()
    post_state = serialize_model_state(project)
    create_audit_entry(project, EventType.UPDATE, post_state,
                       pre_state=pre_state, actor=user_principal)

    # Check history
    history = get_object_history(project.__class__, pk=project.pk)
    assert len(history) == 2
    assert history[0].version == 1
    assert history[1].version == 2
    assert history[1].delta == {"name": "Updated Name"}


@pytest.mark.django_db
def test_get_version(project, user_principal):
    state_v1 = serialize_model_state(project)
    create_audit_entry(project, EventType.CREATE, state_v1, actor=user_principal)

    project.name = "New Name"
    project.save()
    state_v2 = serialize_model_state(project)
    create_audit_entry(project, EventType.UPDATE, state_v2, actor=user_principal)

    # Retrieve state at version 1
    v1_state = get_version(project.__class__, pk=project.pk, version_number=1)
    assert v1_state["name"] == "Original Name"


@pytest.mark.django_db
def test_integrity_verification(project, user_principal):
    state = serialize_model_state(project)
    event = create_audit_entry(project, EventType.CREATE, state, actor=user_principal)

    # Should not raise
    event.verify_integrity()

    # Tamper with checksum
    Event.objects.filter(pk=event.pk).update(checksum="tampered")
    event.refresh_from_db()

    from apps.auditing.exceptions import IntegrityVerificationError
    with pytest.raises(IntegrityVerificationError):
        event.verify_integrity()


@pytest.mark.django_db
def test_auditable_mixin_auto_emit(db):
    """AuditableModelMixin automatically emits CREATE/UPDATE/DELETE events."""
    from apps.auditing.models.mixins import AuditableModelMixin
    from django.db import models

    # Uses a registered model
    from apps.accounts.models import UserAccount
    # (UserAccount triggers auditing if AUDITED_APPS includes "accounts")

    # Verify via get_object_history after a create
    # (actual assertion depends on your audited models config)
    assert True  # Replace with real model fixture
```
