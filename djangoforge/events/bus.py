"""
EventBus — the public API for emitting domain events through the outbox.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.utils.module_loading import import_string

from djangoforge.settings import forge_settings

if TYPE_CHECKING:
    from djangoforge.events.types import DomainEvent

logger = logging.getLogger("djangoforge.events")


class BrokerBackend:
    """Base class for broker adapters (Kafka, Rabbit, SNS, …)."""

    def publish(self, event_type: str, event_id: str, payload: dict[str, Any]) -> None:
        """Publish a single event to the broker."""
        raise NotImplementedError


class EventBus:
    """Writes events to the outbox and (optionally) publishes them immediately."""

    def __init__(self, broker: BrokerBackend | None = None) -> None:
        self._broker = broker

    # ── public API ───────────────────────────────────────────────────

    def emit(self, event: DomainEvent) -> None:
        """Write a :class:`DomainEvent` to the outbox table.

        This should be called *inside* the same ``transaction.atomic()`` that
        mutates domain state so that the event is guaranteed to be recorded.
        """
        if not forge_settings.EVENTS_ENABLED:
            return
        from djangoforge.events.models import OutboxEvent

        OutboxEvent.objects.create(
            event_type=event.event_type,
            event_id=event.event_id,
            source=event.source,
            version=event.version,
            correlation_id=event.correlation_id,
            tenant=event.tenant,
            aggregate_id=event.aggregate_id,
            aggregate_type=event.aggregate_type,
            payload=event.data,
        )
        logger.debug("Outbox event written: %s (%s)", event.event_type, event.event_id)

    def publish_pending(self, batch_size: int | None = None) -> int:
        """Publish pending outbox events via the configured broker.

        Returns the number of events successfully published.
        """
        from djangoforge.events.models import OutboxEvent

        broker = self._broker or _default_broker()
        size = batch_size or forge_settings.EVENTS_MAX_PUBLISH_BATCH
        pending = list(OutboxEvent.objects.pending(batch_size=size))
        published = 0
        for row in pending:
            try:
                broker.publish(
                    event_type=row.event_type,
                    event_id=row.event_id,
                    payload=row.payload,
                )
                row.mark_published()
                published += 1
            except Exception:
                row.attempts += 1
                row.last_error = "publish failed"
                row.save(update_fields=["attempts", "last_error"])
                logger.exception("Failed to publish outbox event %s", row.event_id)
        return published


def _default_broker() -> BrokerBackend:
    klass = import_string(forge_settings.EVENTS_BROKER_BACKEND)
    return klass()
