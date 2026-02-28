"""
Admin module for the authz app.

Registers admin interfaces for Permission, Role, RoleAssignment, and Policy.
"""

from __future__ import annotations

from .assignment import RoleAssignmentAdmin
from .base import BaseAuthzAdmin
from .permission import PermissionAdmin
from .policy import PolicyAdmin
from .role import RoleAdmin

__all__ = [
    "BaseAuthzAdmin",
    "PermissionAdmin",
    "PolicyAdmin",
    "RoleAdmin",
    "RoleAssignmentAdmin",
]
