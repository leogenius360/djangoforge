"""
Device trust and fingerprinting services.

Handles device identification, trust levels, and fingerprinting.
"""


def identify_device_type(user_agent: str) -> str:
    """
    Identify device type from user agent string.

    Args:
        user_agent: User agent string

    Returns:
        Device type identifier
    """
    from apps.sessions.models import DeviceType

    # Simple heuristic-based detection
    ua_lower = user_agent.lower()

    if "mobile" in ua_lower or "android" in ua_lower or "iphone" in ua_lower:
        return DeviceType.MOBILE
    elif "tablet" in ua_lower or "ipad" in ua_lower:
        return DeviceType.TABLET
    elif "cli" in ua_lower or "curl" in ua_lower or "wget" in ua_lower:
        return DeviceType.CLI
    elif "bot" in ua_lower or "crawler" in ua_lower:
        return DeviceType.API
    else:
        return DeviceType.WEB


def generate_device_fingerprint(request) -> str:
    """
    Generate a device fingerprint from request data.

    Args:
        request: HTTP request object

    Returns:
        Device fingerprint hash
    """
    import hashlib

    # Combine various request attributes to create fingerprint
    fingerprint_data = [
        request.META.get("HTTP_USER_AGENT", ""),
        request.META.get("HTTP_ACCEPT_LANGUAGE", ""),
        request.META.get("HTTP_ACCEPT_ENCODING", ""),
        # Note: Some headers may not be reliable or present
    ]

    combined = "|".join(fingerprint_data)
    return hashlib.sha256(combined.encode()).hexdigest()[:64]


def is_trusted_device(user, device_fingerprint: str) -> bool:
    """
    Check if a device is trusted for the user.

    Args:
        user: The user to check
        device_fingerprint: Device fingerprint to verify

    Returns:
        True if device is trusted, False otherwise
    """
    from apps.sessions.models import AuthSession

    # Check if user has any sessions with this device fingerprint marked as trusted
    return (
        AuthSession.objects.for_principal(user)
        .filter(device_fingerprint=device_fingerprint, is_trusted_device=True)
        .exists()
    )


def trust_device(session) -> None:
    """
    Mark a device as trusted.

    Args:
        session: The session to mark as trusted
    """
    session.is_trusted_device = True
    session.save(update_fields=["is_trusted_device"])


def untrust_device(user, device_fingerprint: str) -> int:
    """
    Remove trust from a device.

    Args:
        user: The user who owns the device
        device_fingerprint: Device fingerprint to untrust

    Returns:
        Number of sessions updated
    """
    from apps.sessions.models import AuthSession

    return (
        AuthSession.objects.for_principal(user)
        .filter(device_fingerprint=device_fingerprint)
        .update(is_trusted_device=False)
    )


def get_device_metadata(request) -> dict:
    """
    Extract device metadata from request.

    Args:
        request: HTTP request object

    Returns:
        Dictionary of device metadata
    """
    user_agent = request.META.get("HTTP_USER_AGENT", "")

    return {
        "device_type": identify_device_type(user_agent),
        "user_agent": user_agent[:500],
        "device_fingerprint": generate_device_fingerprint(request),
        "platform": "",  # TODO: Extract from user agent
        "device_name": "",  # TODO: Extract from user agent if available
    }
