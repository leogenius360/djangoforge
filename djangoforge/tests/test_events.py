"""
Tests for the outbox event system.
"""

import pytest

from djangoforge.events.bus import EventBus
from djangoforge.events.models import OutboxEvent
from djangoforge.events.types import DomainEvent


class TestDomainEvent:
    def test_defaults(self):
        ev = DomainEvent(event_type="order.created")
        assert ev.event_type == "order.created"
        assert ev.version == "v1"
        assert ev.event_id  # auto-generated
        assert ev.occurred_at is not None

    def test_custom_fields(self):
        ev = DomainEvent(
            event_type="billing.invoice.created.v1",
            source="billing-service",
            aggregate_id="inv-123",
            aggregate_type="Invoice",
            tenant="acme",
            data={"amount": 100},
        )
        assert ev.source == "billing-service"
        assert ev.data["amount"] == 100


@pytest.mark.django_db
class TestOutboxEvent:
    def test_create_and_query(self):
        row = OutboxEvent.objects.create(
            event_type="test.event",
            event_id="eid-1",
            payload={"hello": "world"},
        )
        assert row.published_at is None
        assert str(row) == "test.event [pending] (eid-1)"

    def test_mark_published(self):
        row = OutboxEvent.objects.create(event_type="test.event", event_id="eid-2")
        row.mark_published()
        row.refresh_from_db()
        assert row.published_at is not None
        assert "published" in str(row)

    def test_pending_manager(self):
        OutboxEvent.objects.create(event_type="a", event_id="e1")
        OutboxEvent.objects.create(event_type="b", event_id="e2")
        published = OutboxEvent.objects.create(event_type="c", event_id="e3")
        published.mark_published()

        pending = list(OutboxEvent.objects.pending())
        assert len(pending) == 2


@pytest.mark.django_db
class TestEventBus:
    def test_emit_creates_outbox_row(self):
        bus = EventBus()
        ev = DomainEvent(event_type="user.registered", data={"user_id": "42"})
        bus.emit(ev)
        assert OutboxEvent.objects.filter(event_id=ev.event_id).exists()

    def test_publish_pending(self):
        bus = EventBus()
        ev = DomainEvent(event_type="order.shipped")
        bus.emit(ev)
        published = bus.publish_pending()
        assert published == 1
        row = OutboxEvent.objects.get(event_id=ev.event_id)
        assert row.published_at is not None
