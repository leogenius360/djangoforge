#!/usr/bin/env python
"""
Smoke tests to verify the Django application is working correctly.

Run this after deployment to verify basic functionality.
"""

import os
import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set Django settings module if not set
if not os.environ.get("DJANGO_SETTINGS_MODULE"):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import django  # noqa: E402

django.setup()


def test_database_connection():
    """Test database connectivity."""
    print("\n[Database]")
    try:
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            assert result == (1,), "Database query failed"
        print("✓ Database connection successful")
        return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False


def test_migrations():
    """Check if all migrations are applied."""
    print("\n[Migrations]")
    try:
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("showmigrations", "--plan", stdout=out, no_color=True)
        output = out.getvalue()

        if "[X]" in output and "[ ]" not in output:
            print("✓ All migrations applied")
            return True
        elif "[ ]" in output:
            print("⚠ Some migrations not applied")
            # Show which apps have pending migrations
            for line in output.split("\n"):
                if "[ ]" in line:
                    print(f"  Pending: {line.strip()}")
            return False
        else:
            print("✓ No migrations found")
            return True
    except Exception as e:
        print(f"✗ Migration check failed: {e}")
        return False


def test_models_can_query():
    """Test that we can query basic models."""
    print("\n[Models]")
    try:
        from apps.accounts.models import UserAccount

        # Just check we can query, don't fail if no users exist
        count = UserAccount.objects.count()
        print(f"✓ UserAccount model queryable ({count} users)")

        from apps.sessions.models import AuthSession

        count = AuthSession.objects.count()
        print(f"✓ AuthSession model queryable ({count} sessions)")

        from apps.auditing.models import AuditEntry

        count = AuditEntry.objects.count()
        print(f"✓ AuditEntry model queryable ({count} entries)")

        return True
    except Exception as e:
        print(f"✗ Model query failed: {e}")
        return False


def test_cache():
    """Test cache connectivity."""
    print("\n[Cache]")
    try:
        from django.core.cache import cache

        test_key = "smoke_test_key"
        test_value = "smoke_test_value"

        cache.set(test_key, test_value, 10)
        retrieved = cache.get(test_key)

        if retrieved == test_value:
            print("✓ Cache working")
            cache.delete(test_key)
            return True
        else:
            print("✗ Cache not working correctly")
            return False
    except Exception as e:
        print(f"✗ Cache test failed: {e}")
        return False


def test_urls_loaded():
    """Test that URLs are loaded correctly."""
    print("\n[URL Configuration]")
    try:
        from django.urls import get_resolver

        resolver = get_resolver()
        url_patterns = resolver.url_patterns

        if len(url_patterns) > 0:
            print(f"✓ URL configuration loaded ({len(url_patterns)} patterns)")
            return True
        else:
            print("✗ No URL patterns found")
            return False
    except Exception as e:
        print(f"✗ URL configuration failed: {e}")
        return False


def test_static_files():
    """Test static files configuration."""
    print("\n[Static Files]")
    try:
        from django.conf import settings

        # Check if static files settings are configured
        assert hasattr(settings, "STATIC_URL"), "STATIC_URL not configured"
        assert hasattr(settings, "STATIC_ROOT"), "STATIC_ROOT not configured"

        print(f"✓ STATIC_URL: {settings.STATIC_URL}")
        print(f"✓ STATIC_ROOT: {settings.STATIC_ROOT}")

        return True
    except Exception as e:
        print(f"✗ Static files check failed: {e}")
        return False


def test_installed_apps():
    """Verify all expected apps are installed."""
    print("\n[Installed Apps]")
    try:
        from django.conf import settings

        expected_apps = [
            "apps.accounts",
            "apps.authn",
            "apps.authz",
            "apps.sessions",
            "apps.auditing",
            "apps.core",
            "rest_framework",
            "drf_spectacular",
        ]

        all_present = True
        for app in expected_apps:
            if app in settings.INSTALLED_APPS:
                print(f"✓ {app}")
            else:
                print(f"✗ {app} not installed")
                all_present = False

        return all_present
    except Exception as e:
        print(f"✗ Installed apps check failed: {e}")
        return False


def test_middleware():
    """Verify middleware configuration."""
    print("\n[Middleware]")
    try:
        from django.conf import settings

        expected_middleware = [
            "django.middleware.security.SecurityMiddleware",
            "corsheaders.middleware.CorsMiddleware",
            "apps.core.middleware.ActorTrackingMiddleware",
            "apps.sessions.middleware.SessionTrackingMiddleware",
            "apps.auditing.middleware.AuditingMiddleware",
        ]

        all_present = True
        for mw in expected_middleware:
            if mw in settings.MIDDLEWARE:
                print(f"✓ {mw}")
            else:
                print(f"⚠ {mw} not configured")
                all_present = False

        return all_present
    except Exception as e:
        print(f"✗ Middleware check failed: {e}")
        return False


def test_api_schema():
    """Test OpenAPI schema generation."""
    print("\n[API Schema]")
    try:
        from drf_spectacular.generators import SchemaGenerator

        generator = SchemaGenerator()
        schema = generator.get_schema()

        if schema and "paths" in schema:
            num_paths = len(schema.get("paths", {}))
            print(f"✓ API schema generated ({num_paths} endpoints)")

            # Check for /api/ prefix
            api_paths = [p for p in schema.get("paths", {}) if p.startswith("/api/")]
            print(f"✓ API endpoints using /api/ prefix ({len(api_paths)} endpoints)")

            return True
        else:
            print("✗ Schema generation failed")
            return False
    except Exception as e:
        print(f"✗ Schema generation failed: {e}")
        return False


def main():
    """Run all smoke tests."""
    print("=" * 60)
    print("Django Application Smoke Tests")
    print("=" * 60)

    tests = [
        test_database_connection,
        test_migrations,
        test_models_can_query,
        test_cache,
        test_urls_loaded,
        test_static_files,
        test_installed_apps,
        test_middleware,
        test_api_schema,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")

    if all(results):
        print("✓ All smoke tests passed!")
        print("=" * 60)
        sys.exit(0)
    else:
        print("✗ Some smoke tests failed")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
