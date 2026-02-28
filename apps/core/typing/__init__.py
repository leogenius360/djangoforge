"""Typing helpers for the project.

This package exists primarily to improve editor autocomplete (Pylance/Pyright)
without changing runtime MRO.

It contains small Protocols/TypeVars that describe Django concepts we use often
(e.g. QuerySets/Managers) and avoid re-declaring them throughout the codebase.
"""

from .django import (
    DjangoDeleteReturn,
    ManagerMixinBase,
    ManagerProtocol,
    ManagerT,
    QuerySetMixinBase,
    QuerySetProtocol,
    QuerySetProtoT,
    QuerySetT,
    SoftDeleteQuerySetProtocol,
    SoftDeleteQuerySetProtoT,
)

__all__ = [
    "DjangoDeleteReturn",
    "ManagerMixinBase",
    "ManagerProtocol",
    "ManagerT",
    "QuerySetMixinBase",
    "QuerySetProtocol",
    "QuerySetProtoT",
    "QuerySetT",
    "SoftDeleteQuerySetProtocol",
    "SoftDeleteQuerySetProtoT",
]
