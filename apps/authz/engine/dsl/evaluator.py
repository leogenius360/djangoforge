"""
AST evaluator for the authz DSL.

Walks the AST produced by :class:`Parser` and evaluates it against an
:class:`EvaluationContext` containing the principal, resource, action, and
environment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apps.authz.exceptions import DSLEvaluationError

if TYPE_CHECKING:
    from apps.authz.engine.dsl.ast_nodes import (
        BinaryOp,
        GetAttr,
        Identifier,
        ListLiteral,
        Literal,
        Node,
        UnaryOp,
    )


class EvaluationContext:
    """Provides variable namespaces for DSL evaluation."""

    __slots__ = ("principal", "resource", "action", "environment")

    def __init__(
        self,
        principal: Any = None,
        resource: Any = None,
        action: str = "",
        environment: dict | None = None,
    ) -> None:
        self.principal = principal
        self.resource = resource
        self.action = action
        self.environment = environment or {}

    def resolve(self, name: str) -> Any:
        """Resolve a top-level variable name."""
        if name == "principal":
            return self.principal
        if name == "resource":
            return self.resource
        if name == "action":
            return self.action
        if name == "environment":
            return self.environment
        raise DSLEvaluationError(f"Unknown variable: {name!r}")


class Evaluator:
    """Evaluates a DSL AST against a context."""

    def __init__(self, context: EvaluationContext) -> None:
        self.context = context

    def evaluate(self, node: Node) -> Any:
        """Evaluate an AST node and return its value."""
        handler = getattr(self, f"_eval_{type(node).__name__.lower()}", None)
        if handler is None:
            raise DSLEvaluationError(f"Unknown AST node: {type(node).__name__.lower()}")
        return handler(node)

    # ------------------------------------------------------------------
    # Node handlers
    # ------------------------------------------------------------------

    def _eval_literal(self, node: Literal) -> Any:
        return node.value

    def _eval_listliteral(self, node: ListLiteral) -> list:
        return [self.evaluate(item) for item in node.items]

    def _eval_identifier(self, node: Identifier) -> Any:
        return self.context.resolve(node.name)

    def _eval_getattr(self, node: GetAttr) -> Any:
        obj = self.evaluate(node.obj)
        if obj is None:
            return None

        # Try dict-style access first (for metadata, environment, etc.)
        if isinstance(obj, dict):
            return obj.get(node.attr)

        # Then regular attribute access
        return getattr(obj, node.attr, None)

    def _eval_unaryop(self, node: UnaryOp) -> Any:
        value = self.evaluate(node.operand)
        if node.operator == "not":
            return not value
        if node.operator == "-":
            return -value
        if node.operator == "+":
            return +value
        raise DSLEvaluationError(f"Unknown unary operator: {node.operator!r}")

    def _eval_binaryop(self, node: BinaryOp) -> Any:
        op = node.operator

        # Short-circuit logical operators
        if op == "and":
            left = self.evaluate(node.left)
            if not left:
                return False
            return bool(self.evaluate(node.right))

        if op == "or":
            left = self.evaluate(node.left)
            if left:
                return True
            return bool(self.evaluate(node.right))

        # Eagerly evaluate both sides for everything else
        left = self.evaluate(node.left)
        right = self.evaluate(node.right)

        try:
            return _BINARY_OPS[op](left, right)
        except KeyError:
            raise DSLEvaluationError(f"Unknown operator: {op!r}") from None
        except Exception as exc:
            raise DSLEvaluationError(f"Error evaluating {left!r} {op} {right!r}: {exc}") from exc


# Mapping of operator strings to their implementations.
_BINARY_OPS: dict[str, Any] = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "in": lambda a, b: a in b if b is not None and hasattr(b, "__contains__") else False,
    "contains": lambda a, b: b in a if a is not None and hasattr(a, "__contains__") else False,
}
