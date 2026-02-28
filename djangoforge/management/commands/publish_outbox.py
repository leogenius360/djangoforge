"""
``publish_outbox`` management command.

Publishes pending outbox events via the configured broker backend.
Can be run as a cron job, Celery beat task, or one-off management command.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from djangoforge.events.bus import EventBus
from djangoforge.settings import forge_settings


class Command(BaseCommand):
    help = "Publish pending outbox events to the configured broker."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--batch-size",
            type=int,
            default=forge_settings.EVENTS_MAX_PUBLISH_BATCH,
            help="Max events to publish per run.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        bus = EventBus()
        published = bus.publish_pending(batch_size=options["batch_size"])
        self.stdout.write(self.style.SUCCESS(f"Published {published} outbox event(s)."))
