"""Phone number utilities for authentication."""

import phonenumbers
from rest_framework import serializers


def validate_and_normalize_phone(phone_number: str) -> str:
    """
    Validate and normalize phone number to E.164 format.

    Args:
        phone_number: Phone number string to validate

    Returns:
        Normalized phone number in E.164 format

    Raises:
        serializers.ValidationError: If phone number is invalid
    """
    try:
        parsed = phonenumbers.parse(phone_number, None)
        if not phonenumbers.is_valid_number(parsed):
            raise serializers.ValidationError("Invalid phone number.")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException as e:
        raise serializers.ValidationError("Invalid phone number format.") from e
