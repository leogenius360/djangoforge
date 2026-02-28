"""
Settings package initialization.

Automatically loads the correct settings module based on DJANGO_SETTINGS_MODULE
or falls back to environment-based detection using the centralized selector utility.
"""

from config.settings_selector import get_settings_module

# Determine which settings module to use
# This handles all cases: explicit DJANGO_SETTINGS_MODULE, env vars, and defaults
module_path = get_settings_module(default_env="development")
module_name = module_path.split(".")[-1]

# Import the appropriate module
if module_name == "dev":
    from .dev import *  # noqa: F401, F403
elif module_name == "prod":
    from .prod import *  # noqa: F401, F403
elif module_name == "staging":
    from .staging import *  # noqa: F401, F403
