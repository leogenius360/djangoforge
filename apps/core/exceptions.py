"""
Core exceptions for the application.

This module centralizes all core-level exceptions for better reusability
and clearer error handling patterns across the codebase.
"""


class OptimisticLockError(RuntimeError):
    """Raised when optimistic locking detects a concurrent update."""


class LifecycleTransitionError(ValueError):
    """Raised when a lifecycle status transition is not allowed."""


class LifecycleStateError(ValueError):
    """Raised when lifecycle fields are incoherent for the current status."""


__all__ = [
    "OptimisticLockError",
    "LifecycleTransitionError",
    "LifecycleStateError",
]
