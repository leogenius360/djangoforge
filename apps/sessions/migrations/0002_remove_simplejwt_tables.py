"""
Remove orphaned simplejwt token_blacklist tables and migration history.

When djangorestframework-simplejwt was installed with ``token_blacklist``,
it created two tables:
- ``token_blacklist_outstandingtoken``
- ``token_blacklist_blacklistedtoken``

This migration:
1. Drops those tables if they exist (``DROP TABLE IF EXISTS``).
2. Deletes the ``django_migrations`` rows for the ``token_blacklist`` app
   so Django no longer considers them "applied" and doesn't warn about
   missing apps.

Safe to run multiple times (idempotent).
"""

from __future__ import annotations

from django.db import migrations


def drop_simplejwt_tables(apps, schema_editor):
    """Drop token_blacklist tables and clean up migration history."""
    with schema_editor.connection.cursor() as cursor:
        # Drop tables (order matters: child before parent)
        cursor.execute("DROP TABLE IF EXISTS token_blacklist_blacklistedtoken")
        cursor.execute("DROP TABLE IF EXISTS token_blacklist_outstandingtoken")

        # Remove migration history so Django doesn't warn about missing app
        cursor.execute("DELETE FROM django_migrations WHERE app = 'token_blacklist'")


def noop(apps, schema_editor):
    pass  # Migration is not reversible (tables are deleted)


class Migration(migrations.Migration):
    dependencies = [
        ("user_sessions", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(drop_simplejwt_tables, reverse_code=noop),
    ]
