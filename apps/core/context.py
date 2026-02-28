from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from typing import TYPE_CHECKING

from apps.core.config import get_system_principal_id

if TYPE_CHECKING:
    from collections.abc import Iterator

    from apps.accounts.models import Principal


_current_actor: ContextVar[Principal | None] = ContextVar("core_current_actor", default=None)


def get_current_actor() -> Principal | None:
    """
    Return the current actor (Principal) from async-safe context storage.

    This is safe for both WSGI (threaded) and ASGI (async) environments.
    """
    return _current_actor.get()


def require_actor(explicit_actor: Principal | None = None) -> Principal:
    """
    Resolve a non-null actor for *user-driven* operations.

    Resolution order:
      1) explicit_actor argument
      2) current context actor (set_current_actor)

    Does NOT fall back to a configured system actor.

    Raises:
        ValueError: if no actor can be resolved.
    """
    actor = explicit_actor or get_current_actor()
    if actor is None:
        raise ValueError(
            "An actor (Principal) is required for this operation. "
            "Provide `actor=...` or set one via set_current_actor(). "
            "For automated flows, use require_system_actor()."
        )
    return actor


def get_system_actor() -> Principal | None:
    """
    Resolve the configured system Principal for automated flows.

    Returns:
        Principal | None: The system actor if configured and resolvable; otherwise None.
    """
    system_id = get_system_principal_id()
    if not system_id:
        return None
    return _get_system_actor_cached(system_id)


def require_system_actor() -> Principal:
    """
    Resolve the configured system Principal for automated flows.

    Raises:
        ValueError: if CORE_SYSTEM_PRINCIPAL_ID is missing or does not resolve.
    """
    actor = get_system_actor()
    if actor is None:
        raise ValueError(
            "A system actor (Principal) is required for this automated operation. "
            "Configure settings.CORE_SYSTEM_PRINCIPAL_ID to a valid Principal PK."
        )
    return actor


@lru_cache(maxsize=32)
def _get_system_actor_cached(system_id: str):
    """
    Internal cached lookup for the system actor.

    Args:
        system_id: Principal PK as string.

    Returns:
        Principal | None: Principal if found; otherwise None.
    """
    # Local import to avoid import cycles.
    from apps.accounts.models import Principal

    try:
        return Principal.objects.get(pk=system_id)
    except Principal.DoesNotExist:
        return None


def clear_system_actor_cache() -> None:
    """
    Clear cached system actor lookup.

    Useful for tests that change CORE_SYSTEM_PRINCIPAL_ID or the Principal row.
    """
    _get_system_actor_cached.cache_clear()


@contextmanager
def set_current_actor(actor: Principal | None) -> Iterator[None]:
    """
    Context manager to set the current actor for the duration of a block.

    This is safe for both WSGI and ASGI environments.

    Example:
        with set_current_actor(request.user):
            obj.save()
    """
    token = _current_actor.set(actor)
    try:
        yield
    finally:
        _current_actor.reset(token)


__all__ = [
    "get_current_actor",
    "set_current_actor",
    "require_actor",
    "get_system_actor",
    "require_system_actor",
    "clear_system_actor_cache",
]
