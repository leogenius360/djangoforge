"""
Built-in broker backends for the event bus.
"""

from __future__ import annotations

import logging
from typing import Any

from djangoforge.events.bus import BrokerBackend

logger = logging.getLogger("djangoforge.events.backends")


class LogBrokerBackend(BrokerBackend):
    """Default backend — logs events instead of publishing to a real broker.

    Useful for development and testing.
    """

    def publish(self, event_type: str, event_id: str, payload: dict[str, Any]) -> None:
        logger.info("EVENT PUBLISHED: %s [%s] %s", event_type, event_id, payload)
