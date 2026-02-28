"""
Forge Auth — claims ingestion from trusted proxies and JWT tokens.
"""

from djangoforge.auth.policy import ForgeAuthPolicy, Principal

__all__ = [
    "ForgeAuthPolicy",
    "Principal",
]
