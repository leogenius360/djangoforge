"""
Authentication backends module.

Provides multiple authentication backends:
- EmailBackend: Authenticate via email and password
- UsernameBackend: Authenticate via username and password
- PhoneBackend: Authenticate via phone number and password
- PasswordlessBackend: Authenticate via magic link token
"""

from .base import BaseAccountsBackend
from .email import EmailBackend
from .passwordless import PasswordlessBackend
from .phone import PhoneBackend
from .username import UsernameBackend

__all__ = [
    "BaseAccountsBackend",
    "EmailBackend",
    "UsernameBackend",
    "PhoneBackend",
    "PasswordlessBackend",
]
