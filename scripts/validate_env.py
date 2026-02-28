#!/usr/bin/env python
"""
Validate environment configuration before deployment.
"""

import os
import sys
from pathlib import Path


def check_env_var(var_name, required=True):
    """Check if environment variable is set."""
    value = os.getenv(var_name)
    if not value:
        if required:
            print(f"✗ Missing required: {var_name}")
            return False
        else:
            print(f"⚠ Optional not set: {var_name}")
    else:
        # Mask sensitive values
        if any(secret in var_name.lower() for secret in ["password", "secret", "key"]):
            display = value[:4] + "****" if len(value) > 4 else "****"
        else:
            display = value
        print(f"✓ {var_name} = {display}")
    return True


def validate_database_url(db_url):
    """Validate database URL format."""
    if not db_url:
        return False

    required_parts = ["postgres://", "@", "/", ":"]
    if all(part in db_url for part in required_parts):
        return True

    print("⚠ DATABASE_URL format may be incorrect")
    return True  # Warning only


def main():
    """Main validation function."""
    print("=" * 50)
    print("Environment Configuration Validation")
    print("=" * 50)

    # Load .env file if exists
    env_file = Path(".env")
    if env_file.exists():
        from dotenv import load_dotenv

        load_dotenv()
        print(f"\n→ Loaded from: {env_file.absolute()}\n")
    else:
        print("\n⚠ No .env file found\n")

    all_valid = True

    # Required variables
    print("\n[Required Variables]")
    all_valid &= check_env_var("DJANGO_SETTINGS_MODULE")
    all_valid &= check_env_var("SECRET_KEY")
    all_valid &= check_env_var("DATABASE_URL")

    # Validate database URL
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        validate_database_url(db_url)

    # Optional variables
    print("\n[Optional Variables]")
    check_env_var("DEBUG", required=False)
    check_env_var("ALLOWED_HOSTS", required=False)
    check_env_var("CORS_ALLOWED_ORIGINS", required=False)

    # Environment-specific checks
    env_module = os.getenv("DJANGO_SETTINGS_MODULE", "")
    if "production" in env_module:
        print("\n[Production Checks]")
        debug = os.getenv("DEBUG", "False")
        if debug.lower() in ("true", "1", "yes"):
            print("✗ DEBUG should be False in production")
            all_valid = False
        else:
            print("✓ DEBUG is False")

        if not os.getenv("ALLOWED_HOSTS"):
            print("⚠ ALLOWED_HOSTS not set (will use default)")

    print("\n" + "=" * 50)
    if all_valid:
        print("✓ Environment configuration is valid")
        print("=" * 50)
        sys.exit(0)
    else:
        print("✗ Environment configuration has errors")
        print("=" * 50)
        sys.exit(1)


if __name__ == "__main__":
    main()
