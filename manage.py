#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys


def main():
    """Run administrative tasks."""
    # Use centralized settings selection utility
    from config.settings_selector import get_settings_module

    # Set the appropriate settings module (defaults to dev for manage.py)
    # The utility handles all cases including package-only "config.settings"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", get_settings_module(default_env="dev"))

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
