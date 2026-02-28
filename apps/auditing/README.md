# Auditing app

The `apps.auditing` package provides an **append-only audit log** for Django model changes using an event-sourcing style `Event` table.

Key properties:

- **Immutable event records**: core event fields cannot be modified after creation.
- **Versioned per-object history**: events form a per-object chain (`version`, `parent`, `checksum`).
- **Tamper-evident integrity**: chained checksums detect historical modification.
- **Optional snapshot + delta storage**: snapshots can be stored periodically; updates store deltas.
- **Transactional outbox**: after the DB transaction commits, events can be dispatched to secondary backends (file/redis/kafka).
- **Request context capture**: middleware records actor + request metadata for each event.

## Architecture at a glance

- Model: `apps.auditing.models.event.Event` (extends `apps.auditing.models.base.BaseEvent`)
- Public API: `apps.auditing.services.create_audit_entry()` and helpers
- Registry/config: `apps.auditing.registry.audit_registry`
- Context: `apps.auditing.context` (contextvars)
- Middleware: `apps.auditing.middleware.AuditingMiddleware`
- Secondary backends: `apps.auditing.backends.*`
- REST API: `apps.auditing.api.*` (staff-only)
- Admin: `apps.auditing.admin.event.EventAdmin` (read-only)

## Enabling auditing

This project includes the app and middleware in `INSTALLED_APPS` / `MIDDLEWARE` by default.
Auditing behavior is controlled via the `AUDITING` Django setting.

Example (typical):

```python
AUDITING = {
    "ENABLED": True,

    # What to audit
    "AUDITED_APPS": ["accounts"],
    "AUDITED_MODELS": {
        # "app_label.ModelName": {...}
        "accounts.UserAccount": {"track_fields": ["email", "status"]},
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
    "SNAPSHOT_INTERVAL": 10,  # 0 = always store snapshot

    # Integrity + compression
    "INTEGRITY_ENABLED": True,
    "INTEGRITY_ALGORITHM": "sha256",
    "COMPRESSION_ENABLED": False,
    "COMPRESSION_ALGORITHM": "zlib",
    "COMPRESSION_THRESHOLD": 10240,

    # Security/compliance controls
    "GLOBAL_EXCLUDE_FIELDS": ["password", "token", "secret", "key"],
    "UNDO_ENABLED": True,
    "MAX_UNDO_DEPTH": 10,
    "RETENTION_DAYS": None,
}
```

Notes:

- The auditing settings loader uses a **strict namespace**: unknown keys raise `ImproperlyConfigured`.
- `GLOBAL_EXCLUDE_FIELDS` is applied to snapshots even when a model is not explicitly registered.

## Auditing models

### Option A: auto-audit with `AuditableModelMixin`

For models that should automatically record audit events on `save()` and `delete()`, inherit from:

- `apps.auditing.models.mixins.AuditableModelMixin`

The mixin registers the model with the audit registry and emits:

- `create` events when a new instance is saved
- `update` events when an existing instance is saved
- `delete` events when an instance is deleted

Per-model customization:

```python
class MyModel(AuditableModelMixin, models.Model):
    name = models.CharField(max_length=100)

    class Audit:
        track_fields = ["name"]
        exclude_fields = ["internal_note"]
        snapshot_interval = 5
```

Implementation details:

- For UPDATE events, the mixin captures `pre_state` **before** saving so deltas are accurate.
- For DELETE events, the mixin captures the snapshot **before** deletion.

### Option B: manual audit events

If you need explicit control (services, commands, unusual side effects), call:

- `apps.auditing.services.create_audit_entry(instance, event_type, state, ...)`

A recommended pattern is:

```python
state = serialize_model_state(instance)
create_audit_entry(instance=instance, event_type=EventType.UPDATE, state=state, comment="...")
```

## Versioning, snapshots, and replay

- Each audited object has an independent `version` sequence.
- `Event.reconstruct_snapshot()` replays deltas forward from the most recent stored snapshot.
- The snapshot strategy is controlled by `SNAPSHOT_ON_CREATE`, `SNAPSHOT_ON_DELETE`, and `SNAPSHOT_INTERVAL`.

## Integrity (tamper-evident chains)

When enabled, a checksum is computed for each event from its immutable payload plus its parent checksum.
This allows you to detect modifications to historical events.

- `Event.verify_integrity()` validates a single event.
- `EventQuerySet.verify_integrity()` validates all events in a queryset.

## Outbox dispatch to secondary backends

After the event row is inserted, `_dispatch_event()` is scheduled via `transaction.on_commit`.
This updates:

- `backends_pending` (list)
- `backends_dispatched` (dict of backend → timestamp)
- `backends_failed` (dict of backend → error/attempts)

Backends are configured via `AUDITING["BACKENDS"]`:

- `file` → JSON-lines file sink
- `redis` / `kafka` → optional integrations (depending on deployment)

Backends implement the `apps.auditing.backends.base.AuditBackend` interface.

## Request context capture

`apps.auditing.middleware.AuditingMiddleware` populates contextvars per request:

- actor (`request.user` if authenticated)
- session (`request.session.session_key` where available)
- ip address
- user agent
- request/correlation id

The service layer reads these values and stores them in the event `context` field.

## REST API (staff-only)

The auditing REST API is read-only and requires staff access.

- `GET /api/audit/events/` — list (filterable)
- `GET /api/audit/events/<uuid:pk>/` — detail
- `GET /api/audit/history/?content_type=app.model&object_id=...` — object history
- `GET /api/audit/version/?content_type=app.model&object_id=...&version=N` — state at version

See `apps.auditing.api.views.events`.

## Django admin (read-only)

The admin registration is intentionally read-only to preserve immutability.
See `apps.auditing.admin.event.EventAdmin`.

## Testing

Auditing has a dedicated test suite under `apps/auditing/tests/`.

Useful entry points:

- Core behavior: `test_core.py`
- End-to-end workflows: `test_integration.py`
- Integrity/compression/backends: `test_integrity.py`, `test_compression.py`, `test_backends.py`

## Security & compliance notes

- Prefer excluding sensitive fields using `GLOBAL_EXCLUDE_FIELDS` and per-model `exclude_fields`.
- Treat audit log access as privileged: API is staff-only and admin is read-only.
- Avoid storing secrets in `comment` or custom `context`.
- Consider a dedicated retention/purge workflow before enabling hard deletion of events.
