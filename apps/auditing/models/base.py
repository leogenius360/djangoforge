"""
Abstract base model for audit events.

``BaseEvent`` is an abstract Django model that provides the full event-sourcing
infrastructure: generic-FK subject, tamper-evident chain hashing, snapshot
compression, delta storage, and undo/redo pointers.

Inheritance
-----------
Concrete subclasses must supply actor-related and outbox fields (see
``event.py``).  The only expected concrete subclass is ``Event``.

Immutability contract
---------------------
After creation the core event fields (event classification, state, chain)
are immutable.  ``save()`` enforces this: a full save (no ``update_fields``)
is forbidden; ``update_fields`` must contain only names from ``MUTABLE_FIELDS``.

Version field semantics
-----------------------
``BaseEvent.version`` records the audited aggregate's version number at the
time this event was created.  It is **not** an optimistic-locking counter for
the Event row itself.  Therefore ``save()`` completely bypasses
``ModelOperationsMixin._save_with_optimistic_lock()`` and the automatic version
increment logic.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone as tz

from apps.auditing.enums import CompressionAlgorithm, EventType
from apps.auditing.exceptions import ImmutabilityError
from apps.auditing.models.managers import EventManager

if TYPE_CHECKING:
    from collections.abc import Iterable


class BaseEvent(models.Model):
    """
    Abstract audit event.

    Extend the concrete ``Event`` model — do not use this class directly.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # ------------------------------------------------------------------
    # Generic relation: the audited aggregate
    # ------------------------------------------------------------------
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=255)
    content_object = GenericForeignKey("content_type", "object_id")

    # ------------------------------------------------------------------
    # Event classification
    # ------------------------------------------------------------------
    event_type = models.CharField(max_length=20, choices=EventType.choices, db_index=True)
    # Per-object sequence number (incremented by AuditService, NOT by the
    # Django optimistic-lock machinery).
    version = models.PositiveIntegerField(default=1)

    # ------------------------------------------------------------------
    # State storage
    # ------------------------------------------------------------------
    # Only one of snapshot / snapshot_compressed will be non-null at a time.
    snapshot = models.JSONField(null=True, blank=True)
    snapshot_compressed = models.BinaryField(null=True, blank=True)
    # Compact change map: {field_name: new_value} for changed fields only.
    # Use get_diff() to reconstruct the full {"old": v, "new": v} form.
    delta = models.JSONField(null=True, blank=True)

    # ------------------------------------------------------------------
    # Tamper-evident chain
    # ------------------------------------------------------------------
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    checksum = models.CharField(max_length=128, blank=True, default="", db_index=True)
    parent_checksum = models.CharField(max_length=128, blank=True, default="")

    # ------------------------------------------------------------------
    # Compression metadata
    # ------------------------------------------------------------------
    compression_algorithm = models.CharField(max_length=20, choices=CompressionAlgorithm.choices, blank=True)
    original_size = models.PositiveIntegerField(null=True, blank=True)
    compressed_size = models.PositiveIntegerField(null=True, blank=True)

    # ------------------------------------------------------------------
    # Timestamps (standalone — not using TimestampMixin to stay simple)
    # ------------------------------------------------------------------
    # Use default=tz.now instead of auto_now_add so the service layer
    # can pre-set this before INSERT and compute checksums deterministically.
    created_at = models.DateTimeField(default=tz.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ------------------------------------------------------------------
    # Soft-delete (via deleted_at — does not use CoreStatus)
    # ------------------------------------------------------------------
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # ------------------------------------------------------------------
    # Context & annotation
    # ------------------------------------------------------------------
    context = models.JSONField(default=dict, blank=True)
    comment = models.TextField(blank=True, default="")

    # ------------------------------------------------------------------
    # Undo/Redo pointer
    # ------------------------------------------------------------------
    target_event = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="compensating_events",
    )

    # ------------------------------------------------------------------
    # Manager
    # ------------------------------------------------------------------
    objects = EventManager()

    # ------------------------------------------------------------------
    # Immutability declarations
    # ------------------------------------------------------------------
    # Fields that can NEVER change after the event row is created.
    IMMUTABLE_FIELDS = frozenset(
        {
            "content_type",
            "content_type_id",
            "object_id",
            "event_type",
            "version",
            "snapshot",
            "snapshot_compressed",
            "delta",
            "checksum",
            "parent_checksum",
            "parent",
            "parent_id",
            "target_event",
            "target_event_id",
            "created_at",
        }
    )

    # Fields that ARE allowed to be updated post-creation.
    MUTABLE_FIELDS = frozenset({"context", "comment", "updated_at", "deleted_at"})

    class Meta:
        abstract = True
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"], name="{class}_ct_oid_idx"),
            models.Index(fields=["content_type", "object_id", "version"], name="{class}_ct_oid_v_idx"),
            models.Index(fields=["event_type", "created_at"], name="{class}_et_cat_idx"),
            models.Index(fields=["checksum", "parent_checksum"], name="{class}_checksum_chain_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id", "version"],
                name="{class}_unique_aggregate_version",
            ),
            # snapshot or snapshot_compressed must be mutually exclusive
            models.CheckConstraint(
                condition=(models.Q(snapshot__isnull=True) | models.Q(snapshot_compressed__isnull=True)),
                name="{class}_snapshot_exclusive",
            ),
        ]

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return (
            f"<{self.event_type.upper()} "
            f"{self.__class__.__name__} "
            f"ct={self.content_type.name} "
            f"oid={self.object_id} "
            f"v{self.version}>"
        )

    def __repr__(self) -> str:
        return self.__str__()

    # ------------------------------------------------------------------
    # save() — critical: bypasses ModelOperationsMixin for updates
    # ------------------------------------------------------------------

    def save(
        self,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        """
        Save the event, enforcing immutability constraints.

        INSERT (new event)
        ~~~~~~~~~~~~~~~~~~
        Delegates to ``models.Model.save()`` directly with ``force_insert=True``
        to bypass ``ModelOperationsMixin``'s optimistic-lock increment.

        UPDATE (modifying mutable fields)
        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        ``update_fields`` is mandatory.  Raises ``ImmutabilityError`` if any
        field in ``update_fields`` is not in ``MUTABLE_FIELDS``.  Always
        includes ``updated_at`` in the SQL UPDATE.
        """
        is_new = (not self.pk) or self._state.adding or force_insert

        if is_new:
            return super().save(
                force_insert=True,
                force_update=False,
                using=using,
                update_fields=None,
            )

        # UPDATE: strict immutability gate.
        self._check_immutability(update_fields)

        # Always stamp updated_at on partial updates.
        attempted: set[str] = set(update_fields)
        attempted.add("updated_at")

        return super().save(
            force_insert=False,
            force_update=force_update,
            using=using,
            update_fields=attempted,
        )

    def delete(self, using: str | None = None, keep_parents: bool = False) -> tuple[int, dict[str, int]]:
        """Soft-delete by setting ``deleted_at``."""
        self.deleted_at = tz.now()
        self.save(update_fields=["deleted_at"])
        return 1, {self._meta.label: 1}

    def hard_delete(self, using: str | None = None, keep_parents: bool = False) -> tuple[int, dict[str, int]]:
        """Physically delete the row — intended for GDPR purge routines only."""
        return super().delete(using=using, keep_parents=keep_parents)

    def _check_immutability(self, update_fields: Iterable[str] | None) -> None:
        """Raise ImmutabilityError if any field in ``update_fields`` is immutable."""
        # UPDATE: strict immutability gate.
        if update_fields is None:
            raise ImmutabilityError(
                forbidden_fields=frozenset({"<all fields> — full save without update_fields is forbidden"}),
                allowed_fields=self.__class__.MUTABLE_FIELDS,
            )

        attempted: frozenset[str] = frozenset(update_fields)
        forbidden = attempted & self.__class__.IMMUTABLE_FIELDS
        if forbidden:
            raise ImmutabilityError(
                forbidden_fields=forbidden,
                allowed_fields=self.__class__.MUTABLE_FIELDS,
            )

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------

    def get_snapshot(self) -> dict[str, Any] | None:
        """Return the decompressed snapshot dict, or ``None`` if absent."""
        if self.snapshot_compressed is not None and self.compression_algorithm:
            from apps.auditing.utils.compression import CompressionService

            svc = CompressionService(algorithm=self.compression_algorithm)
            return svc.decompress(bytes(self.snapshot_compressed))
        return self.snapshot

    def set_snapshot(self, payload: dict[str, Any]) -> None:
        """
        Store ``payload`` as the snapshot, compressing if configured.

        Sets the appropriate fields and clears the complementary storage
        (i.e., clears ``snapshot`` when using compressed storage and vice-versa).
        """
        from apps.auditing.utils.compression import CompressionService

        svc = CompressionService()
        if svc.should_compress(payload):
            result = svc.compress(payload)
            self.snapshot = None
            self.snapshot_compressed = result.compressed_data
            self.compression_algorithm = result.algorithm
            self.original_size = result.original_size
            self.compressed_size = result.compressed_size
        else:
            self.snapshot = payload
            self.snapshot_compressed = None
            self.compression_algorithm = ""
            self.original_size = None
            self.compressed_size = None

    # ------------------------------------------------------------------
    # Snapshot reconstruction
    # ------------------------------------------------------------------

    def reconstruct_snapshot(self) -> dict[str, Any] | None:
        """
        Return the model state/snapshot at this event's version.

        First attempts to use the stored snapshot.  Falls back to replaying
        all deltas forward from the nearest preceding full snapshot.
        """
        snapshot = self.get_snapshot()
        if snapshot is not None:
            return snapshot
        return self._reconstruct_from_deltas()

    def _reconstruct_from_deltas(self) -> dict[str, Any] | None:
        """
        Replay changes from the closest preceding full snapshot to reach
        the state at ``self.version``.
        """
        ancestors: list[BaseEvent] = list(
            cast("EventManager", self.__class__.objects)
            .with_deleted()
            .filter(
                content_type_id=self.content_type_id,
                object_id=self.object_id,
                version__lte=self.version,
            )
            .order_by("version")
            .only(
                "version",
                "snapshot",
                "snapshot_compressed",
                "compression_algorithm",
                "delta",
            )
        )

        if not ancestors:
            return None

        # Walk backward to find the most recent full snapshot.
        base_state: dict[str, Any] | None = None
        base_index = 0
        for i, event in enumerate(reversed(ancestors)):
            snap = event.get_snapshot()
            if snap is not None:
                base_state = snap
                base_index = len(ancestors) - i  # index of first event to apply
                break

        if base_state is None:
            return None  # no snapshot to start from

        # Apply changes forward from base_index to reach self.version.
        for event in ancestors[base_index:]:
            if event.delta:
                base_state.update(event.delta)

        return base_state

    # ------------------------------------------------------------------
    # Integrity
    # ------------------------------------------------------------------

    def _integrity_payload(self) -> dict[str, Any]:
        """
        Return the dict of fields committed into the checksum hash.

        All fields here are immutable after creation, ensuring the checksum
        is stable and tamper-evident.
        """
        return {
            "content_type_id": self.content_type_id,
            "object_id": self.object_id,
            "event_type": self.event_type,
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "delta": self.delta,
            "has_snapshot": self.snapshot is not None or self.snapshot_compressed is not None,
        }

    def compute_checksum(self, *, parent_checksum: str = "") -> str:
        """Compute and return the checksum for this event (does not persist)."""
        from apps.auditing.utils.integrity import IntegrityService

        svc = IntegrityService()
        return svc.hash_event_payload(self._integrity_payload(), parent_checksum=parent_checksum).digest

    def verify_integrity(self, *, raise_on_mismatch: bool = False) -> bool:
        """
        Verify this event's checksum against a re-computed value.

        Returns True if the checksum is valid (or integrity is disabled).
        """
        from apps.auditing.utils.integrity import IntegrityService

        svc = IntegrityService()
        return svc.verify_event_chain(
            payload=self._integrity_payload(),
            current_checksum=self.checksum,
            parent_checksum=self.parent_checksum,
            raise_on_mismatch=raise_on_mismatch,
        )

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------

    @property
    def is_undone(self) -> bool:
        """
        True if this event has been reversed by a compensating UNDO event
        that has not itself been re-applied by a subsequent REDO event.
        """
        for undo_event in self.children.filter(event_type=EventType.UNDO):
            if not undo_event.children.filter(event_type=EventType.REDO).exists():
                return True
        return False

    def can_undo(self) -> bool:
        """Return True if this event may be reversed via an UNDO operation."""
        if self.event_type not in EventType.undoable_types():
            return False
        return not self.is_undone

    def can_redo(self) -> bool:
        """Return True if this event has been undone and may be re-applied via a REDO operation."""
        return self.is_undone

    def assert_can_undo(self) -> None:
        """Raise ``UndoNotAllowedError`` if this event cannot be undone."""
        if not self.can_undo():
            from apps.auditing.exceptions import UndoNotAllowedError

            if self.event_type not in EventType.undoable_types():
                reason = f"event type {self.event_type!r} is not undoable"
            else:
                reason = "event has already been undone"
            raise UndoNotAllowedError(
                f"Event {self.pk} (type={self.event_type!r}, v{self.version}) cannot be undone: {reason}."
            )

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self) -> Any:
        """Return all events for the same aggregate, ordered by version ascending."""
        return (
            cast("EventManager", self.__class__.objects)
            .with_deleted()
            .filter(
                content_type_id=self.content_type_id,
                object_id=self.object_id,
            )
            .order_by("version")
        )

    def get_diff(self) -> dict[str, Any]:
        """
        Compute the full field-level diff between this event's snapshot and its parent's.

        Returns ``{field: {"old": old_value, "new": new_value}}`` for every field that
        changed.  Returns an empty dict when there is no parent snapshot to compare to.

        The stored :attr:`delta` field contains only the compact ``{field: new_value}``
        form; this method reconstructs the full diff on demand by loading the parent
        snapshot.
        """
        if not self.parent_id:
            return {}
        parent_snapshot: dict[str, Any] = {}
        if self.parent_id:
            try:
                parent = self.__class__.objects.with_deleted().get(pk=self.parent_id)
                parent_snapshot = parent.get_snapshot() or {}
            except self.__class__.DoesNotExist:
                pass
        current_snapshot = self.get_snapshot() or {}
        diff: dict[str, Any] = {}
        all_keys = set(parent_snapshot) | set(current_snapshot)
        for key in all_keys:
            old_val = parent_snapshot.get(key)
            new_val = current_snapshot.get(key)
            if old_val != new_val:
                diff[key] = {"old": old_val, "new": new_val}
        return diff

    def get_previous_version(self) -> BaseEvent | None:
        """Return the event with version = self.version - 1 for the same aggregate, or None."""
        if self.version <= 1:
            return None
        return self.__class__.objects.filter(
            content_type_id=self.content_type_id,
            object_id=self.object_id,
            version=self.version - 1,
        ).first()

    def get_next_version(self) -> BaseEvent | None:
        """Return the event with version = self.version + 1 for the same aggregate, or None."""
        return self.__class__.objects.filter(
            content_type_id=self.content_type_id,
            object_id=self.object_id,
            version=self.version + 1,
        ).first()
