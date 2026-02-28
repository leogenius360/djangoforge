"""Abstract Syntax Tree node definitions for the authz DSL."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Node:
    """Base AST node."""


@dataclass(frozen=True, slots=True)
class Literal(Node):
    """A literal value (string, number, boolean, ``None``, or list)."""

    value: Any


@dataclass(frozen=True, slots=True)
class Identifier(Node):
    """A variable reference, e.g. ``principal``."""

    name: str


@dataclass(frozen=True, slots=True)
class GetAttr(Node):
    """Attribute access, e.g. ``principal.kind``."""

    obj: Node
    attr: str


@dataclass(frozen=True, slots=True)
class UnaryOp(Node):
    """Unary operation (``not``, ``-``, ``+``)."""

    operator: str
    operand: Node


@dataclass(frozen=True, slots=True)
class BinaryOp(Node):
    """Binary operation (comparison, logical, arithmetic)."""

    left: Node
    operator: str
    right: Node


@dataclass(frozen=True, slots=True)
class ListLiteral(Node):
    """A list literal, e.g. ``["a", "b"]``."""

    items: tuple[Node, ...] = field(default_factory=tuple)
