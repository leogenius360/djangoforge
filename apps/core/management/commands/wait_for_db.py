"""
Django management command to wait for database to be available.

Uses exponential backoff for retry logic to avoid overwhelming the database
during startup scenarios.
"""

import time

from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import OperationalError


class Command(BaseCommand):
    """Django command to wait for database with exponential backoff."""

    help = "Wait for database to be available"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--max-retries",
            type=int,
            default=30,
            help="Maximum number of retry attempts (default: 30)",
        )
        parser.add_argument(
            "--initial-wait",
            type=float,
            default=1.0,
            help="Initial wait time in seconds (default: 1.0)",
        )
        parser.add_argument(
            "--max-wait",
            type=float,
            default=30.0,
            help="Maximum wait time between retries in seconds (default: 30.0)",
        )

    def handle(self, *args, **options):
        """Handle the command with exponential backoff."""
        self.stdout.write("Waiting for database...")
        max_retries = options["max_retries"]
        wait_time = options["initial_wait"]
        max_wait = options["max_wait"]
        retry_count = 0
        connected = False

        while not connected and retry_count < max_retries:
            try:
                connection = connections["default"]
                connection.cursor()
                connected = True
            except OperationalError as exc:
                retry_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Database unavailable, waiting {wait_time:.1f}s... "
                        f"(attempt {retry_count}/{max_retries}): {exc}"
                    )
                )
                time.sleep(wait_time)
                # Exponential backoff: double wait time, cap at max_wait
                wait_time = min(wait_time * 2, max_wait)

        if connected:
            self.stdout.write(self.style.SUCCESS(f"Database available! (after {retry_count} attempts)"))
        else:
            self.stdout.write(self.style.ERROR(f"Database unavailable after {max_retries} attempts"))
            raise OperationalError("Could not connect to database")
