"""
Root conftest for pytest configuration.
"""

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def configure_audit_for_tests(db):
    """
    Reload auditing settings before each test so that any override_settings
    decorator takes full effect.
    """
    from apps.auditing.settings import audit_settings

    audit_settings.reload()


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before each test to prevent rate limit accumulation."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def configure_system_actor_for_tests(db, settings):
    """Ensure automated flows have a Principal actor in tests.

    We create a lightweight API client Principal and wire it into
    ``CORE_SYSTEM_PRINCIPAL_ID``.

    Bootstrap note: Principal has ``ACTOR_REQUIRED = True``, so the very
    first principal must be created via Django's base ``Model.save()`` to
    bypass actor enforcement.  Once it exists, it acts as its own creator
    for subsequent operations.
    """
    from django.db import models as django_models

    from apps.accounts.enums import PrincipalKind
    from apps.accounts.models import APIClient, Principal
    from apps.core.context import set_current_actor

    # Bootstrap: get or create the system principal
    try:
        principal = Principal.objects.with_deleted().get(
            username="system-test-api-client",
            kind=PrincipalKind.API_CLIENT,
        )
    except Principal.DoesNotExist:
        principal = Principal(
            username="system-test-api-client",
            kind=PrincipalKind.API_CLIENT,
            display_name="test-system-api-client",
            is_active=True,
        )
        # Direct save to bypass actor enforcement during bootstrap
        django_models.Model.save(principal, force_insert=True)

    settings.CORE_SYSTEM_PRINCIPAL_ID = str(principal.pk)

    # Use the system principal as actor for creating dependent objects
    # AND as ambient actor for all test code (Principal has ACTOR_REQUIRED=True).
    with set_current_actor(principal):
        APIClient.objects.get_or_create(
            client_id="test-system-api-client",
            defaults={"principal": principal, "client_secret": ""},
        )
        yield
