"""
Fixtures for djangoforge tests.

Because the test suite runs with ``--nomigrations``, we need to ensure the
OutboxEvent table is created for DB-level tests.
"""

import contextlib

import pytest
from django.db import connection

from djangoforge.events.models import OutboxEvent


@pytest.fixture(autouse=True, scope="session")
def _ensure_outbox_table(django_db_setup, django_db_blocker):
    """Create the OutboxEvent table if it doesn't exist yet."""
    with (
        django_db_blocker.unblock(),
        connection.schema_editor() as editor,
        contextlib.suppress(Exception),
    ):
        editor.create_model(OutboxEvent)
