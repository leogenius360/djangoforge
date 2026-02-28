"""
Signal handlers for the accounts app.

Kept minimal by design: all domain logic lives in model methods and the
service layer.  The only signal we handle is ``user_logged_in`` to replace
Django's built-in ``update_last_login`` with one that satisfies
``Principal.ACTOR_REQUIRED = True``.

Wired up in ``AccountsConfig.ready()``.
"""

from __future__ import annotations


def update_last_login(sender, user, **kwargs) -> None:  # noqa: ARG001
    """
    Replacement for Django's built-in ``update_last_login``.

    Delegates to ``Principal.record_last_login()`` so the logic lives
    on the model, not in the signal handler.
    """
    user.record_last_login()
