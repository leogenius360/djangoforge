"""
Validators for the accounts app.

Provides reusable validators for usernames, metadata, and tags that
respect runtime configuration from ``AccountsSettings``.
"""

from __future__ import annotations

import json
import re
from typing import Any

import phonenumbers
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

from apps.accounts.constants import MAX_USERNAME_LENGTH, MIN_USERNAME_LENGTH, USERNAME_REGEX, USERNAME_RESERVED_WORDS


class UsernameValidator(RegexValidator):
    """
    Validate username format.

    Rules:
    - Must start with a letter or digit.
    - May contain letters, digits, dots, hyphens, and underscores.
    - No consecutive special characters (e.g., ``..``, ``--``, ``__``).
    - Length between ``MIN_USERNAME_LENGTH`` and ``MAX_USERNAME_LENGTH``.

    Compliance: ISO 27001 A.9.2.1 -- user registration and de-registration.
    """

    regex = USERNAME_REGEX
    message = _(
        "Username must start with a letter or digit and contain only "
        "letters, digits, dots (.), hyphens (-), or underscores (_)."
    )
    code = "invalid_username"

    def __call__(self, value: str) -> None:
        """Validate the username value."""
        super().__call__(value)

        if value.lower() in {w.lower() for w in USERNAME_RESERVED_WORDS}:
            raise ValidationError(
                _("The username '%(username)s' is reserved and cannot be used."),
                code="username_reserved",
                params={"username": value},
            )

        if len(value) < MIN_USERNAME_LENGTH:
            raise ValidationError(
                _("Username must be at least %(min_length)d characters long."),
                code="username_too_short",
                params={"min_length": MIN_USERNAME_LENGTH},
            )

        if len(value) > MAX_USERNAME_LENGTH:
            raise ValidationError(
                _("Username must be at most %(max_length)d characters long."),
                code="username_too_long",
                params={"max_length": MAX_USERNAME_LENGTH},
            )

        # Disallow consecutive special characters
        if re.search(r"[._-]{2,}", value):
            raise ValidationError(
                _("Username must not contain consecutive special characters."),
                code="username_consecutive_specials",
            )


def validate_username_not_reserved(value: str) -> None:
    """
    Reject usernames that match reserved words.

    Uses runtime settings if available; falls back to the constant list.
    """
    from apps.accounts.settings import accounts_settings

    reserved = accounts_settings.USERNAME_RESERVED_WORDS
    if value.lower() in {w.lower() for w in reserved}:
        raise ValidationError(
            _("The username '%(username)s' is reserved and cannot be used."),
            code="username_reserved",
            params={"username": value},
        )


class PhoneNumberValidator:
    """
    Validate phone numbers using the ``phonenumbers`` library.

    Accepts any format parseable by ``phonenumbers`` (E.164, national, etc.).
    Raises ``ValidationError`` for numbers that cannot be parsed or are not
    valid according to the ITU-T E.164 standard.

    Compliance: ISO 27001 A.9.2.1 -- user registration and de-registration.
    """

    message = _(
        "Enter a valid phone number (e.g. +12125552368). International format with country code is recommended."
    )
    code = "invalid_phone_number"

    def __call__(self, value: str) -> None:
        """Validate *value* as a phone number."""
        if not value:
            return
        try:
            parsed = phonenumbers.parse(value, None)
        except phonenumbers.NumberParseException as exc:
            raise ValidationError(self.message, code=self.code) from exc
        if not phonenumbers.is_valid_number(parsed):
            raise ValidationError(self.message, code=self.code)

    def __eq__(self, other: object) -> bool:
        """Support Django migration serialisation comparison."""
        return isinstance(other, self.__class__)

    def deconstruct(self) -> tuple[str, list[Any], dict[str, Any]]:
        """Support Django migration serialisation."""
        return (f"{self.__class__.__module__}.{self.__class__.__qualname__}", [], {})


def validate_metadata_size(value: Any, *, max_bytes: int | None = None) -> None:
    """
    Validate that a metadata JSON blob does not exceed the configured max size.

    Parameters
    ----------
    value : Any
        The metadata value (typically a ``dict``).
    max_bytes : int, optional
        Override the configured max size.  Defaults to
        ``accounts_settings.MAX_METADATA_SIZE_BYTES``.
    """
    if max_bytes is None:
        from apps.accounts.settings import accounts_settings

        max_bytes = accounts_settings.MAX_METADATA_SIZE_BYTES

    serialized = json.dumps(value, separators=(",", ":"))
    size = len(serialized.encode("utf-8"))
    if size > max_bytes:
        raise ValidationError(
            _("Metadata exceeds maximum size of %(max_bytes)d bytes (got %(size)d)."),
            code="metadata_too_large",
            params={"max_bytes": max_bytes, "size": size},
        )


def validate_tags_count(value: Any, *, max_count: int | None = None) -> None:
    """
    Validate that a tags list does not exceed the configured max count.

    Parameters
    ----------
    value : Any
        The tags value (typically a ``list``).
    max_count : int, optional
        Override the configured max count.  Defaults to
        ``accounts_settings.MAX_TAGS_COUNT``.
    """
    if not isinstance(value, list):
        raise ValidationError(_("Tags must be a list."), code="tags_not_list")

    if max_count is None:
        from apps.accounts.settings import accounts_settings

        max_count = accounts_settings.MAX_TAGS_COUNT

    if len(value) > max_count:
        raise ValidationError(
            _("Maximum %(max_count)d tags allowed (got %(count)d)."),
            code="too_many_tags",
            params={"max_count": max_count, "count": len(value)},
        )


__all__ = [
    "PhoneNumberValidator",
    "UsernameValidator",
    "validate_username_not_reserved",
    "validate_metadata_size",
    "validate_tags_count",
]
