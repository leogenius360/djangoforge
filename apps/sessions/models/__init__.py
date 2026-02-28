"""Sessions models package.

This module is the stable import surface for the sessions app.
"""

from apps.authn.models.enums import AuthenticationMethod, AuthenticationStatus, MFAMethod

from ..enums import SessionChannel, SessionCredentialKind
from .auth_session import AuthSession
from .credentials import SessionCredential
from .enums import DeviceType
from .managers import AuthSessionManager
from .querysets import AuthSessionQuerySet

__all__ = [
    # Enums
    "SessionChannel",
    "SessionCredentialKind",
    "AuthenticationStatus",
    "AuthenticationMethod",
    "MFAMethod",
    "DeviceType",
    # Model
    "AuthSession",
    "SessionCredential",
    # QuerySet & Manager
    "AuthSessionQuerySet",
    "AuthSessionManager",
]
