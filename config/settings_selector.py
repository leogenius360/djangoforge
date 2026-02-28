"""
Utility for selecting the appropriate Django settings module.

This module provides a centralized way to determine which settings module
should be used based on environment variables and context.
"""

import os

# Valid settings module names
VALID_SETTINGS_MODULES = ["dev", "prod", "staging"]


def get_settings_module(default_env: str = "development") -> str:
    """
    Determine the appropriate Django settings module.

    Priority order:
    1. DJANGO_SETTINGS_MODULE (if set and specific)
    2. DJANGO_ENV or NODE_ENV environment variables
    3. Context-based default (passed as parameter)

    Args:
        default_env: The default environment if no explicit configuration is found.
                    Should be "dev" for manage.py, "prod" for wsgi/asgi.

    Returns:
        The fully qualified settings module path (e.g., "config.settings.prod")

    Note:
        This function also normalizes "config.settings" (package-only) to a specific
        module based on the context.
    """
    # Check if DJANGO_SETTINGS_MODULE is explicitly set
    django_settings = os.environ.get("DJANGO_SETTINGS_MODULE", "")

    # If it's just the package name, treat it as unset and use context default
    if django_settings and django_settings != "config.settings":
        # A specific module is set, use it as-is
        return django_settings

    # Fall back to environment detection or default
    # Priority: DJANGO_ENV > NODE_ENV > default_env parameter
    env = os.environ.get("DJANGO_ENV") or os.environ.get("NODE_ENV") or default_env

    # Map environment names to settings modules
    return _get_module_for_env(env)


def _get_module_for_env(env: str) -> str:
    """
    Map environment name to settings module path.

    Args:
        env: Environment name (e.g., "prod", "dev", "staging")

    Returns:
        The fully qualified settings module path
    """
    if env in ["production", "prod"]:
        return "config.settings.prod"
    elif env in ["staging", "stage"]:
        return "config.settings.staging"
    else:
        # Default to dev for any other value (including "development", "dev", etc.)
        return "config.settings.dev"
