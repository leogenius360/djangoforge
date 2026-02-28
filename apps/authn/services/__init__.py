"""
Authentication services package.

Services encapsulate all business logic for the authn subsystem.
Views and backends delegate to these services.
"""

from .authentication import AuthenticationResult, AuthenticationService
from .jwt import JWTService
from .lockout import LockoutService
from .mfa import MFAService, MFAVerificationResult
from .password import PasswordService
from .token import TokenCreationResult, TokenService
from .verification import VerificationService

__all__ = [
    # Core orchestrator
    "AuthenticationService",
    "AuthenticationResult",
    # JWT
    "JWTService",
    # MFA
    "MFAService",
    "MFAVerificationResult",
    # Password
    "PasswordService",
    # Token
    "TokenService",
    "TokenCreationResult",
    # Lockout
    "LockoutService",
    # Verification
    "VerificationService",
]
