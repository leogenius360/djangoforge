"""SMS utilities.

This module provides a small, dependency-free SMS sending abstraction.

Supported backends:
- auto (default): uses Twilio if credentials are configured; otherwise logs in DEBUG.
- twilio: send via Twilio REST API using stdlib urllib.
- log: log the message (DEBUG/testing only).

Configuration (settings / env):
- ACCOUNTS_SMS_BACKEND: 'auto' | 'twilio' | 'log' | dotted path to callable
- TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


class SMSBackendError(RuntimeError):
    pass


def send_sms(*, to_number: str, body: str) -> None:
    backend = getattr(settings, "ACCOUNTS_SMS_BACKEND", "auto")

    if backend == "auto":
        if _twilio_is_configured():
            backend = "twilio"
        elif settings.DEBUG:
            backend = "log"
        else:
            raise SMSBackendError("SMS backend not configured. Set ACCOUNTS_SMS_BACKEND or Twilio credentials.")

    if backend == "log":
        _log_sms(to_number=to_number, body=body)
        return

    if backend == "twilio":
        _twilio_send_sms(to_number=to_number, body=body)
        return

    # Dotted path to a callable: (to_number: str, body: str) -> None
    sender = import_string(backend)
    sender(to_number=to_number, body=body)


def _log_sms(*, to_number: str, body: str) -> None:
    logger.warning("SMS to %s: %s", to_number, body)


def _twilio_is_configured() -> bool:
    return bool(
        getattr(settings, "TWILIO_ACCOUNT_SID", "")
        and getattr(settings, "TWILIO_AUTH_TOKEN", "")
        and getattr(settings, "TWILIO_FROM_NUMBER", "")
    )


def _twilio_send_sms(*, to_number: str, body: str) -> None:
    account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", "")
    auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", "")
    from_number = getattr(settings, "TWILIO_FROM_NUMBER", "")

    if not (account_sid and auth_token and from_number):
        raise SMSBackendError("Twilio credentials are not fully configured.")

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    data = urllib.parse.urlencode({"To": to_number, "From": from_number, "Body": body}).encode()

    token = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode("ascii")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = resp.read().decode("utf-8")
            if resp.status >= 400:
                raise SMSBackendError(f"Twilio error HTTP {resp.status}: {payload}")

            # Best-effort parse for logging
            try:
                parsed = json.loads(payload)
                logger.info("Twilio SMS sent: sid=%s", parsed.get("sid"))
            except Exception:
                logger.info("Twilio SMS sent")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        raise SMSBackendError(f"Twilio HTTPError: {detail}") from e
    except urllib.error.URLError as e:
        raise SMSBackendError(f"Twilio URLError: {e}") from e
