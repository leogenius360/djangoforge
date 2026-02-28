"""
Encryption and cryptographic utilities.

Provides helpers for encryption, hashing, and secure token generation.
"""

import hashlib
import secrets


def generate_secure_token(length: int = 32) -> str:
    """
    Generate a secure random token.

    Parameters
    ----------
    length : int
        Number of bytes (default: 32)

    Returns
    -------
    str
        URL-safe base64-encoded token
    """
    return secrets.token_urlsafe(length)


def generate_fingerprint(data: str) -> str:
    """
    Generate a SHA-256 fingerprint for data integrity verification.

    This function is intended for generating checksums and fingerprints
    of non-sensitive data (e.g., file contents, message digests).

    WARNING
    -------
    Do NOT use this for password hashing. Use Django's password hashers instead.

    Parameters
    ----------
    data : str
        Data to fingerprint

    Returns
    -------
    str
        Hexadecimal SHA-256 hash string

    Examples
    --------
    >>> generate_fingerprint("some data")
    '1307990e6ba5ca145eb35e99182a9bec46531bc54ddf656a602c780fa0240dee'
    """
    return hashlib.sha256(data.encode()).hexdigest()


def generate_secure_hash(data: str, salt: str | None = None) -> str:
    """
    DEPRECATED: Use generate_fingerprint() instead.

    Generate a SHA-256 hash of data.

    Notes
    -----
    This function is deprecated and will be removed in a future version.
    Use generate_fingerprint() for checksums or Django's password hashers for passwords.

    Parameters
    ----------
    data : str
        Data to hash
    salt : str | None
        Optional salt to add to the data (deprecated parameter)

    Returns
    -------
    str
        Hexadecimal hash string
    """
    import warnings

    warnings.warn(
        "generate_secure_hash() is deprecated. Use generate_fingerprint() for checksums "
        "or Django's password hashers for passwords.",
        DeprecationWarning,
        stacklevel=2,
    )
    if salt:
        data = f"{data}{salt}"
    return hashlib.sha256(data.encode()).hexdigest()


def constant_time_compare(a: str, b: str) -> bool:
    """
    Constant-time comparison to prevent timing attacks.

    Parameters
    ----------
    a : str
        First string
    b : str
        Second string

    Returns
    -------
    bool
        True if strings are equal, False otherwise
    """
    return secrets.compare_digest(a, b)
