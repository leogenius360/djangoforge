"""Push notification utilities.

This module intentionally keeps push sending pluggable.

Supported backends:
- auto (default): logs in DEBUG, errors in production unless configured
- log: log the message (DEBUG/testing only)
- dotted path: import a callable (to_user, title, body, data) -> None

Configuration:
- ACCOUNTS_PUSH_BACKEND: 'auto' | 'log' | dotted path

A real backend would likely integrate with FCM/APNs/WebPush and would require
registered device tokens in your database.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


class PushBackendError(RuntimeError):
    pass


def send_push(*, to_user, title: str, body: str, data: dict | None = None) -> None:
    backend = getattr(settings, "ACCOUNTS_PUSH_BACKEND", "auto")

    if backend == "auto":
        if settings.DEBUG:
            backend = "log"
        else:
            raise PushBackendError("Push backend not configured. Set ACCOUNTS_PUSH_BACKEND.")

    if backend == "log":
        logger.warning("PUSH to user=%s title=%s body=%s data=%s", getattr(to_user, "pk", None), title, body, data)
        return

    sender = import_string(backend)
    sender(to_user=to_user, title=title, body=body, data=data or {})
