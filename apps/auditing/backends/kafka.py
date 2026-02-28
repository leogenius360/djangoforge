"""
Kafka audit dispatch backend.

Produces ``Event`` records as JSON messages to a Kafka topic.  This backend
is **write-only**: ``read()``, ``query()``, ``get_history()`` and
``get_version()`` are not supported (raise ``NotImplementedError``) because
audit reconstruction is handled by the primary Event model in the database.

Configuration via ``AUDITING["BACKEND_OPTIONS"]["kafka"]``::

    AUDITING = {
        "BACKENDS": ["kafka"],
        "BACKEND_OPTIONS": {
            "kafka": {
                "bootstrap_servers": "localhost:9092",
                "topic": "audit.events",
                "producer_config": {},   # extra confluent-kafka config dict
            },
        },
    }

Requires ``confluent-kafka`` (preferred) or ``kafka-python`` as a fallback.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from apps.auditing.backends.base import AuditBackend, AuditBackendError, AuditBackendUnavailableError

logger = logging.getLogger(__name__)


class KafkaAuditBackend(AuditBackend):
    """
    Kafka producer dispatch backend.

    Each event is produced synchronously (flush=True) to ensure delivery
    before marking the event as dispatched in the outbox.
    """

    name = "kafka"

    def __init__(
        self,
        *,
        bootstrap_servers: str | None = None,
        topic: str | None = None,
        producer_config: dict[str, Any] | None = None,
        **_extra: Any,
    ) -> None:
        from apps.auditing.settings import audit_settings

        opts: dict[str, Any] = audit_settings.BACKEND_OPTIONS.get("kafka", {}) or {}
        self._bootstrap_servers = bootstrap_servers or opts.get("bootstrap_servers", "localhost:9092")
        self._topic = topic or opts.get("topic", "audit.events")
        extra_config = producer_config or opts.get("producer_config", {}) or {}
        self.producer: Any = None
        self._connect(extra_config)

    # ------------------------------------------------------------------
    # AuditBackend interface
    # ------------------------------------------------------------------

    def dispatch(self, event_data: dict[str, Any]) -> None:
        """Produce ``event_data`` as a JSON message to the configured Kafka topic."""
        if self.producer is None:
            raise AuditBackendUnavailableError(self.name, "Kafka producer not initialised")

        try:
            message = json.dumps(event_data, default=str, ensure_ascii=False).encode("utf-8")
            key = str(event_data.get("id", uuid.uuid4())).encode("utf-8")
            self._produce(key, message)
            self.producer.flush(timeout=5)
        except AuditBackendUnavailableError:
            raise
        except Exception as exc:
            raise AuditBackendError(f"KafkaAuditBackend dispatch failed: {exc}") from exc

    def health_check(self) -> dict[str, Any]:
        """Return health status based on whether the producer is initialised."""
        if self.producer is None:
            return {
                "backend": self.name,
                "status": "unhealthy",
                "available": False,
                "error": "Kafka producer not initialised",
            }
        return {
            "backend": self.name,
            "status": "healthy",
            "available": True,
            "bootstrap_servers": self._bootstrap_servers,
            "topic": self._topic,
        }

    def is_available(self) -> bool:
        return self.producer is not None

    # ------------------------------------------------------------------
    # Unsupported read operations (write-only backend)
    # ------------------------------------------------------------------

    def read(self, entry_id: str) -> dict[str, Any]:
        raise NotImplementedError("KafkaAuditBackend is write-only; use the primary DB Event model to read.")

    def query(self, **_kwargs: Any) -> list[dict[str, Any]]:
        raise NotImplementedError("KafkaAuditBackend is write-only; use the primary DB Event model to query.")

    def get_history(self, content_type_id: int, object_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError("KafkaAuditBackend is write-only; use the primary DB Event model for history.")

    def get_version(self, content_type_id: int, object_id: str, object_version: int) -> dict[str, Any] | None:
        raise NotImplementedError("KafkaAuditBackend is write-only; use the primary DB Event model for versioning.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self, extra_config: dict[str, Any]) -> None:
        """Attempt to initialise a Kafka producer."""
        # Try confluent-kafka first (preferred for production)
        try:
            from confluent_kafka import Producer  # type: ignore[import-untyped]

            config = {
                "bootstrap.servers": self._bootstrap_servers,
                "client.id": "auditing-backend",
                "acks": "all",
                "retries": 3,
                **extra_config,
            }
            self.producer: Producer = Producer(config)
            self._produce = self._confluent_produce
            logger.info(
                "KafkaAuditBackend: connected via confluent-kafka (servers=%s, topic=%s)",
                self._bootstrap_servers,
                self._topic,
            )
            return
        except ImportError:
            pass

        # Fallback to kafka-python
        try:
            from kafka import KafkaProducer  # type: ignore[import-untyped]

            self.producer = KafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                **extra_config,
            )
            self._produce = self._kafkapython_produce
            logger.info(
                "KafkaAuditBackend: connected via kafka-python (servers=%s, topic=%s)",
                self._bootstrap_servers,
                self._topic,
            )
            return
        except ImportError:
            pass

        logger.warning(
            "KafkaAuditBackend: neither 'confluent-kafka' nor 'kafka-python' is installed — backend disabled."
        )

    def _confluent_produce(self, key: bytes, message: bytes) -> None:
        self.producer.produce(self._topic, key=key, value=message)

    def _kafkapython_produce(self, key: bytes, message: bytes) -> None:
        self.producer.send(self._topic, key=key, value=message)
