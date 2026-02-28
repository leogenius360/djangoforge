"""
Model state serialisation utilities.

Provides ``model_to_dict()`` for producing a stable, audit-safe JSON-serialisable
snapshot of a Django model instance, and ``compute_delta()`` for computing the
field-level diff between two such snapshots.

Design choices
--------------
* Only concrete, non-relation fields (and FK ``{field}_id`` values) are included.
* Many-to-many and reverse-relation fields are skipped (too expensive and
  rarely needed for compliance audit trails).
* Non-serialisable Python types (UUID, datetime, Decimal …) are converted to
  their canonical string representation.
* FK fields are serialised as the raw integer or UUID value (``actor_id`` not
  ``actor``), keeping snapshots lightweight and FK-reference-safe.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.db import models


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def model_to_dict(
    instance: models.Model,
    *,
    track_fields: list[str] | None = None,
    exclude_fields: list[str] | None = None,
) -> dict[str, Any]:
    """
    Serialise a model instance to an audit-safe, JSON-serialisable dict.

    Parameters
    ----------
    instance:
        The Django model instance to serialise.
    track_fields:
        Whitelist of logical field names to include.  ``None`` / empty = all fields.
    exclude_fields:
        Blacklist of field names to exclude.
    """
    _exclude = set(exclude_fields or [])
    _track = set(track_fields) if track_fields else None
    result: dict[str, Any] = {}

    for f in instance._meta.get_fields():
        # Skip reverse relations, M2M, and auto-created (reverse-FK etc.)
        if f.auto_created:
            continue
        if f.many_to_many:
            continue
        if f.one_to_many:
            continue

        # For ForeignKey / OneToOneField use the attname (e.g. "actor_id")
        attname: str = getattr(f, "attname", f.name)
        name: str = f.name  # logical name used for filtering

        # Apply exclude
        if name in _exclude or attname in _exclude:
            continue

        # Apply whitelist
        if _track and name not in _track and attname not in _track:
            continue

        value = getattr(instance, attname, None)
        result[attname] = _serialize_value(value)

    return result


def compute_delta(
    previous: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Compute the field-level diff between two state snapshots.

    Returns a compact dict mapping changed field names to their **new** values only:
    ``{field_name: new_value}``.  Use :meth:`~apps.auditing.models.BaseEvent.get_diff`
    on the stored event to reconstruct the full ``{"from": …, "to": …}`` form.

    Returns an empty dict when ``previous`` is ``None`` (CREATE events have no
    prior state to diff against).

    Example::

        compute_delta({"status": "active"}, {"status": "inactive"})
        # → {"status": "inactive"}
    """
    if not previous or not current:
        return {}

    changes: dict[str, Any] = {}
    all_keys = set(previous) | set(current)

    for key in all_keys:
        old_val = previous.get(key)
        new_val = current.get(key)
        if old_val != new_val:
            changes[key] = new_val

    return changes


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _serialize_value(value: Any) -> Any:  # noqa: PLR0911
    """Convert a Python value to a JSON-serialisable form."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        # Binary fields are not included in snapshots by default.
        return None
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    # Fallback: str() cast for anything else (enum members, custom types …)
    return str(value)
