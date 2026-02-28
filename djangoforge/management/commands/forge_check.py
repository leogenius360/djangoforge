"""
``forge_check`` management command.

Runs all Forge-specific checks beyond what ``manage.py check`` provides:

* OpenAPI completeness (operationId, tags, responses, auth)
* Security configuration
* Observability (correlation ID middleware, structured logging)
* Outbox correctness (events enabled → table exists)
"""

from __future__ import annotations

from typing import Any

from django.core.checks import run_checks
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run DjangoForge enterprise checks (OpenAPI, security, observability, events)."

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING("Running Forge checks…"))

        errors = run_checks(tags=["forge"])
        if not errors:
            self.stdout.write(self.style.SUCCESS("All Forge checks passed."))
            return

        for err in errors:
            if err.is_serious():
                self.stderr.write(self.style.ERROR(str(err)))
            else:
                self.stdout.write(self.style.WARNING(str(err)))
