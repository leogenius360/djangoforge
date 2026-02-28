"""
Services for the accounts app.

Provides ``AccountProvisioner`` for atomic creation and teardown of
Principal + concrete account pairs.
"""

from __future__ import annotations

from .provisioning import AccountProvisioner

__all__ = [
    "AccountProvisioner",
]
