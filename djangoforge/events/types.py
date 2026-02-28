"""
Domain event data structure (CloudEvents-ish envelope).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class DomainEvent:
    """Immutable description of something that happened in the domain.

    Loosely follows the `CloudEvents <https://cloudevents.io/>`_ specification.
    """

    event_type: str
    source: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    version: str = "v1"
    correlation_id: str = ""
    tenant: str = ""
    aggregate_id: str = ""
    aggregate_type: str = ""
