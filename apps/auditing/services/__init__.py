"""
High-level audit service functions.

These are the primary entry points for creating and querying audit events:

* :func:`should_audit_model`    — check whether a model is audited
* :func:`serialize_model_state` — snapshot a model instance to a JSON dict
* :func:`create_audit_entry`    — write a new ``Event`` row (public API)
* :func:`get_object_history`    — retrieve all events for an object
* :func:`get_version`           — retrieve the state snapshot at a version
* :func:`undo_change`           — create an UNDO event and restore state
* :func:`redo_change`           — create a REDO event and re-apply state

Outbox / backend dispatch
-------------------------
After a new ``Event`` row is committed to the database,
:func:`_dispatch_event` is scheduled via ``transaction.on_commit`` to
forward the event to optional secondary backends (file, Redis, Kafka).
This ensures the primary DB write and the backend dispatch are decoupled
while preserving at-least-once delivery semantics.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.utils import timezone

if TYPE_CHECKING:
    from django.db import models

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


def should_audit_model(model_class: type[models.Model]) -> bool:
    """Return True if ``model_class`` is registered for auditing and globally enabled."""
    from apps.auditing.registry import audit_registry

    return audit_registry.should_audit_model(model_class)


def serialize_model_state(
    instance: models.Model,
    *,
    track_fields: list[str] | None = None,
    exclude_fields: list[str] | None = None,
) -> dict[str, Any]:
    """
    Return a JSON-serialisable snapshot of ``instance``.

    When the instance is registered with the audit registry, the per-model
    ``track_fields`` and ``exclude_fields`` configuration is automatically
    applied unless you pass explicit overrides.

    The result always contains a ``"pk"`` key with the string-encoded
    primary-key value.
    """
    from apps.auditing.registry import audit_registry
    from apps.auditing.settings import audit_settings
    from apps.auditing.utils.serialization import model_to_dict

    config = audit_registry.get_config(type(instance))

    resolved_track: list[str] | None = track_fields
    resolved_exclude: list[str] | None = exclude_fields

    if config is not None:
        if resolved_track is None and config.track_fields:
            resolved_track = list(config.track_fields)
        if resolved_exclude is None:
            resolved_exclude = list(config.exclude_fields | set(audit_settings.GLOBAL_EXCLUDE_FIELDS))
        else:
            resolved_exclude = list(set(resolved_exclude) | set(audit_settings.GLOBAL_EXCLUDE_FIELDS))
    else:
        if resolved_exclude is None:
            resolved_exclude = list(audit_settings.GLOBAL_EXCLUDE_FIELDS)

    state = model_to_dict(instance, track_fields=resolved_track, exclude_fields=resolved_exclude)
    if "pk" not in state:
        state["pk"] = str(instance.pk)
    return state


def create_audit_entry(
    instance: models.Model,
    event_type: str,
    state: dict[str, Any],
    *,
    actor: Any = None,
    pre_state: dict[str, Any] | None = None,
    comment: str = "",
) -> Any:
    """
    Create and persist a new ``Event`` for ``instance``.

    The version number is set to ``max(existing_version) + 1``.  The most
    recent existing event is linked as ``parent`` to maintain the chain.

    Parameters
    ----------
    instance:
        The audited model instance.
    event_type:
        An :class:`~apps.auditing.enums.EventType` value (string).
    state:
        JSON-serialisable snapshot of ``instance`` at this point in time.
    actor:
        Optional user who performed the change.  Falls back to the current
        audit context actor if omitted.
    pre_state:
        The model state *before* the change, used to compute the delta for
        UPDATE events.  Pass ``None`` for CREATE / DELETE.
    comment:
        Optional human-readable annotation attached to the event.
    """
    from django.contrib.contenttypes.models import ContentType
    from django.db import transaction

    from apps.auditing.context import (
        get_current_actor,
        get_current_ip_address,
        get_current_request_id,
        get_current_session,
        get_current_user_agent,
    )
    from apps.auditing.models.event import Event
    from apps.auditing.settings import audit_settings
    from apps.auditing.utils.serialization import compute_delta as _compute_delta

    if actor is None:
        actor = get_current_actor()

    session = get_current_session()
    ip_address = get_current_ip_address()
    user_agent = get_current_user_agent()
    request_id = get_current_request_id()

    content_type = ContentType.objects.get_for_model(instance.__class__)
    object_id = str(instance.pk)

    # ------------------------------------------------------------------
    # Version + parent (SELECT FOR UPDATE prevents race conditions)
    # ------------------------------------------------------------------
    with transaction.atomic():
        try:
            last_event = (
                Event.objects.with_deleted()
                .filter(content_type=content_type, object_id=object_id)
                .select_for_update()
                .order_by("-version")
                .first()
            )
        except Exception:
            # select_for_update may fail outside a transaction context.
            last_event = (
                Event.objects.with_deleted()
                .filter(content_type=content_type, object_id=object_id)
                .order_by("-version")
                .first()
            )

        version = (last_event.version + 1) if last_event else 1
        parent = last_event
        parent_checksum = last_event.checksum if last_event else ""

        # ------------------------------------------------------------------
        # Changes computation (compact {field: new_value} format)
        # ------------------------------------------------------------------
        delta: dict[str, Any] | None = None
        if audit_settings.TRACK_DELTAS and pre_state is not None and state is not None:
            delta = _compute_delta(pre_state, state) or None

        # ------------------------------------------------------------------
        # Context metadata
        # ------------------------------------------------------------------
        context: dict[str, Any] = {}
        if session:
            context["session"] = session
        if ip_address:
            context["ip_address"] = ip_address
        if user_agent:
            context["user_agent"] = user_agent
        if request_id:
            context["request_id"] = request_id

        # ------------------------------------------------------------------
        # Backends pending for outbox dispatch
        # ------------------------------------------------------------------
        backends_pending = list(audit_settings.BACKENDS)

        # ------------------------------------------------------------------
        # Pre-set created_at so checksum includes the real timestamp
        # ------------------------------------------------------------------
        now = timezone.now()

        _config = None
        try:
            from apps.auditing.registry import audit_registry

            _config = audit_registry.get_config(instance.__class__)
        except Exception:
            pass

        _should_take_snapshot = _decide_snapshot(event_type, version, _config, audit_settings)

        event = Event(
            content_type=content_type,
            object_id=object_id,
            event_type=event_type,
            version=version,
            parent=parent,
            parent_checksum=parent_checksum,
            delta=delta,
            actor=actor,
            context=context,
            comment=comment,
            backends_pending=backends_pending,
            created_at=now,
        )

        _persist_event(
            event,
            state=state if _should_take_snapshot else None,
            parent_checksum=parent_checksum,
            audit_settings=audit_settings,
        )

    # ------------------------------------------------------------------
    # Dispatch to secondary backends after transaction commits
    # ------------------------------------------------------------------
    if backends_pending:
        event_pk = event.pk

        def _on_commit() -> None:
            _dispatch_event(event_pk)

        try:  # noqa: SIM105
            transaction.on_commit(_on_commit)
        except Exception:
            # Not inside a transaction (e.g. in tests with autocommit).
            pass

    return event


def get_object_history(
    model_class: type[models.Model],
    pk: Any,
) -> list[Any]:
    """
    Return all ``Event`` records for the given object, ordered by version.
    """
    from django.contrib.contenttypes.models import ContentType

    from apps.auditing.models.event import Event

    content_type = ContentType.objects.get_for_model(model_class)
    return list(Event.objects.filter(content_type=content_type, object_id=str(pk)).order_by("version"))


def get_version(
    model_class: type[models.Model],
    pk: Any,
    version_number: int,
) -> dict[str, Any] | None:
    """
    Return the state snapshot recorded at ``version_number`` for the given object.

    Returns ``None`` when no event with that version exists.
    """
    from django.contrib.contenttypes.models import ContentType

    from apps.auditing.models.event import Event

    content_type = ContentType.objects.get_for_model(model_class)
    event = Event.objects.filter(
        content_type=content_type,
        object_id=str(pk),
        version=version_number,
    ).first()
    if event is None:
        return None
    return event.reconstruct_snapshot()


def undo_change(audit_entry: Any) -> Any:
    """
    Reverse a previously recorded change.

    1. Asserts the event can be undone.
    2. Restores the model instance to the state from the predecessor event.
    3. Creates and returns a new ``UNDO`` event.

    Raises :exc:`~apps.auditing.exceptions.UndoNotAllowedError` when the
    event cannot be undone.
    """
    from apps.auditing.enums import EventType
    from apps.auditing.models.event import Event

    audit_entry.assert_can_undo()

    restore_state: dict[str, Any] | None = None
    if audit_entry.parent_id:
        parent_event = Event.objects.with_deleted().filter(pk=audit_entry.parent_id).first()
        if parent_event:
            restore_state = parent_event.get_snapshot()

    if restore_state is not None:
        _restore_model_state(audit_entry, restore_state)

    next_version = _get_next_version(audit_entry.content_type_id, audit_entry.object_id)

    return _build_and_save_event(
        content_type=audit_entry.content_type,
        object_id=audit_entry.object_id,
        event_type=EventType.UNDO,
        state=restore_state,
        version=next_version,
        parent=audit_entry,
        parent_checksum=audit_entry.checksum,
    )


def redo_change(audit_entry: Any) -> Any:
    """
    Re-apply a previously undone change.

    1. Asserts the event has been undone.
    2. Restores the model instance to the state recorded in ``audit_entry``.
    3. Creates and returns a new ``REDO`` event.

    Raises :exc:`ValueError` when the event has not been undone.
    """
    from apps.auditing.enums import EventType

    if not audit_entry.is_undone:
        raise ValueError("Cannot redo an event that has not been undone.")

    undo_event = None
    for candidate in audit_entry.children.filter(event_type=EventType.UNDO):
        if not candidate.children.filter(event_type=EventType.REDO).exists():
            undo_event = candidate
            break

    if undo_event is None:
        raise ValueError("No eligible UNDO event found for this audit entry.")

    restore_state = audit_entry.get_snapshot()
    if restore_state is not None:
        _restore_model_state(audit_entry, restore_state)

    next_version = _get_next_version(audit_entry.content_type_id, audit_entry.object_id)

    return _build_and_save_event(
        content_type=audit_entry.content_type,
        object_id=audit_entry.object_id,
        event_type=EventType.REDO,
        state=restore_state,
        version=next_version,
        parent=undo_event,
        parent_checksum=undo_event.checksum,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_next_version(content_type_id: int, object_id: str) -> int:
    """Return the next version number for an object's audit chain."""
    from apps.auditing.models.event import Event

    last_event = (
        Event.objects.with_deleted()
        .filter(
            content_type_id=content_type_id,
            object_id=object_id,
        )
        .order_by("-version")
        .first()
    )
    return (last_event.version + 1) if last_event else 1


def _persist_event(
    event: Any,
    *,
    state: dict[str, Any] | None,
    parent_checksum: str,
    audit_settings: Any,
) -> None:
    """Apply snapshot, compute integrity checksum, and INSERT the event row."""
    from django.db import models as _models

    if state is not None:
        event.set_snapshot(state)
    else:
        event.snapshot = None
        event.snapshot_compressed = None
        event.compression_algorithm = ""

    if audit_settings.INTEGRITY_ENABLED:
        from apps.auditing.utils.integrity import IntegrityService

        event.checksum = (
            IntegrityService()
            .hash_event_payload(
                event._integrity_payload(),
                parent_checksum=parent_checksum,
            )
            .digest
        )

    _models.Model.save(event, force_insert=True)


def _decide_snapshot(
    event_type: str,
    version: int,
    config: Any,
    settings: Any,
) -> bool:
    """Return True if a full snapshot should be stored for this event."""
    from apps.auditing.enums import EventType

    if event_type == EventType.CREATE:
        return (
            config.effective_snapshot_on_create(settings.SNAPSHOT_ON_CREATE) if config else settings.SNAPSHOT_ON_CREATE
        )
    if event_type in EventType.deletion_types():
        return (
            config.effective_snapshot_on_delete(settings.SNAPSHOT_ON_DELETE) if config else settings.SNAPSHOT_ON_DELETE
        )

    interval = config.effective_snapshot_interval(settings.SNAPSHOT_INTERVAL) if config else settings.SNAPSHOT_INTERVAL
    if interval == 0:
        return True
    return version % interval == 0


# ---------------------------------------------------------------------------
# Backend dispatch (runs after transaction commit)
# ---------------------------------------------------------------------------


def _dispatch_event(event_pk: int) -> None:
    """
    Forward the event to all configured secondary backends.

    Called asynchronously via ``transaction.on_commit``.
    Updates ``backends_pending``, ``backends_dispatched``, and
    ``backends_failed`` on the event row.

    Uses ``select_for_update`` inside ``transaction.atomic`` to prevent
    concurrent dispatchers from overwriting each other's changes.
    """
    from django.db import transaction
    from django.utils import timezone as tz

    from apps.auditing.backends.factory import get_configured_backends
    from apps.auditing.models.event import Event

    backends = get_configured_backends()
    if not backends:
        return

    try:
        with transaction.atomic():
            try:
                event = Event.objects.select_for_update().get(pk=event_pk)
            except Event.DoesNotExist:
                return

            event_data = backends[0].serialize_event(event)
            pending = list(event.backends_pending or [])
            dispatched: dict[str, Any] = dict(event.backends_dispatched or {})
            failed: dict[str, Any] = dict(event.backends_failed or {})

            for backend in backends:
                if backend.name not in pending:
                    continue
                try:
                    backend.dispatch(event_data)
                    pending.remove(backend.name)
                    dispatched[backend.name] = tz.now().isoformat()
                    failed.pop(backend.name, None)
                except Exception as exc:
                    logger.error("Backend dispatch failed (%s): %s", backend.name, exc)
                    prev = failed.get(backend.name, {"attempts": 0})
                    failed[backend.name] = {
                        "error": str(exc),
                        "attempts": prev.get("attempts", 0) + 1,
                    }

            event.backends_pending = pending
            event.backends_dispatched = dispatched
            event.backends_failed = failed
            event.save(update_fields=["backends_pending", "backends_dispatched", "backends_failed"])
    except Exception as exc:
        logger.error("Failed to dispatch Event pk=%s: %s", event_pk, exc)


def _restore_model_state(audit_entry: Any, state: dict[str, Any]) -> None:
    """
    Apply ``state`` to the persisted model instance identified by ``audit_entry``.

    Skips unknown fields and the primary key.
    """
    model_class = audit_entry.content_type.model_class()
    if model_class is None:
        return

    try:
        instance = model_class._default_manager.get(pk=audit_entry.object_id)
    except model_class.DoesNotExist:
        return

    pk_attname = instance._meta.pk.attname
    concrete_attnames = {
        getattr(f, "attname", f.name)
        for f in instance._meta.get_fields()
        if not getattr(f, "auto_created", False)
        and not getattr(f, "many_to_many", False)
        and not getattr(f, "one_to_many", False)
    }

    update_fields: list[str] = []
    for field_name, value in state.items():
        if field_name in ("pk", pk_attname):
            continue
        if field_name not in concrete_attnames:
            continue
        try:
            setattr(instance, field_name, value)
            update_fields.append(field_name)
        except (AttributeError, ValueError, TypeError):
            pass

    if update_fields:
        instance.save(update_fields=update_fields)


def _build_and_save_event(
    *,
    content_type: Any,
    object_id: str,
    event_type: str,
    state: dict[str, Any] | None,
    version: int,
    parent: Any,
    parent_checksum: str,
    actor: Any = None,
    comment: str = "",
) -> Any:
    """Build and INSERT an Event row with checksum and snapshot, returning it."""
    from apps.auditing.context import get_current_actor
    from apps.auditing.models.event import Event
    from apps.auditing.settings import audit_settings

    if actor is None:
        actor = get_current_actor()

    now = timezone.now()
    event = Event(
        content_type=content_type,
        object_id=object_id,
        event_type=event_type,
        version=version,
        parent=parent,
        parent_checksum=parent_checksum,
        actor=actor,
        comment=comment,
        created_at=now,
    )

    _persist_event(event, state=state, parent_checksum=parent_checksum, audit_settings=audit_settings)
    return event
