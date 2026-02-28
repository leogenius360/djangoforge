"""
Recursive-descent parser for the authz DSL.

Parses token streams produced by :class:`Lexer` into an AST made of nodes
defined in :mod:`.ast_nodes`.

Grammar
-------
::

    expression  := or_expr
    or_expr     := and_expr (("or" | "||") and_expr)*
    and_expr    := not_expr (("and" | "&&") not_expr)*
    not_expr    := ("not" | "!") not_expr | comparison
    comparison  := access (("==" | "!=" | "<" | "<=" | ">" | ">=" | "in" | "contains") access)?
    access      := primary ("." IDENTIFIER)*
    primary     := "true" | "false" | "null" | NUMBER | STRING
                 | IDENTIFIER | "(" expression ")" | "[" list_items "]"
"""

from __future__ import annotations

from apps.authz.engine.dsl.ast_nodes import (
    BinaryOp,
    GetAttr,
    Identifier,
    ListLiteral,
    Literal,
    Node,
    UnaryOp,
)
from apps.authz.engine.dsl.lexer import (
    TT_COMMA,
    TT_COMP,
    TT_DOT,
    TT_EOF,
    TT_IDENTIFIER,
    TT_LBRACKET,
    TT_LPAREN,
    TT_NOT_OP,
    TT_NUMBER,
    TT_RBRACKET,
    TT_RPAREN,
    TT_STRING,
    Lexer,
    Token,
)
from apps.authz.exceptions import DSLSyntaxError


class Parser:
    """Parses a DSL source string into an AST."""

    def __init__(self, source: str) -> None:
        self.tokens: list[Token] = list(Lexer(source).tokenize())
        self.pos: int = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def _current(self) -> Token:
        return self.tokens[self.pos]

    def _advance(self) -> Token:
        tok = self._current
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return tok

    def _expect(self, token_type: str) -> Token:
        if self._current.type != token_type:
            raise DSLSyntaxError(
                f"Expected {token_type}, got {self._current.type} at position {self._current.position}"
            )
        return self._advance()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self) -> Node:
        """Parse the full expression and return the root AST node."""
        node = self._or_expr()
        if self._current.type != TT_EOF:
            raise DSLSyntaxError(
                f"Unexpected token after expression: {self._current.value!r} at position {self._current.position}"
            )
        return node

    # ------------------------------------------------------------------
    # Grammar rules
    # ------------------------------------------------------------------

    def _or_expr(self) -> Node:
        left = self._and_expr()
        while self._current.type in ("OR",):
            self._advance()
            right = self._and_expr()
            left = BinaryOp(left, "or", right)
        return left

    def _and_expr(self) -> Node:
        left = self._not_expr()
        while self._current.type in ("AND",):
            self._advance()
            right = self._not_expr()
            left = BinaryOp(left, "and", right)
        return left

    def _not_expr(self) -> Node:
        if self._current.type in ("NOT", TT_NOT_OP):
            self._advance()
            return UnaryOp("not", self._not_expr())
        return self._comparison()

    def _comparison(self) -> Node:
        left = self._access()

        if self._current.type == TT_COMP:
            op = self._advance().value
            right = self._access()
            return BinaryOp(left, op, right)

        if self._current.type == "IN":
            self._advance()
            right = self._access()
            return BinaryOp(left, "in", right)

        if self._current.type == "CONTAINS":
            self._advance()
            right = self._access()
            return BinaryOp(left, "contains", right)

        # Handle "not in" — current is NOT followed by IN
        if self._current.type == "NOT":
            next_idx = self.pos + 1
            if next_idx < len(self.tokens) and self.tokens[next_idx].type == "IN":
                self._advance()  # consume NOT
                self._advance()  # consume IN
                right = self._access()
                return UnaryOp("not", BinaryOp(left, "in", right))

        return left

    def _access(self) -> Node:
        node = self._primary()
        while self._current.type == TT_DOT:
            self._advance()
            attr = self._expect(TT_IDENTIFIER).value
            node = GetAttr(node, attr)
        return node

    def _primary(self) -> Node:
        tok = self._current

        if tok.type == "TRUE":
            self._advance()
            return Literal(True)

        if tok.type == "FALSE":
            self._advance()
            return Literal(False)

        if tok.type == "NULL":
            self._advance()
            return Literal(None)

        if tok.type == TT_NUMBER:
            self._advance()
            return Literal(tok.value)

        if tok.type == TT_STRING:
            self._advance()
            return Literal(tok.value)

        if tok.type == TT_IDENTIFIER:
            self._advance()
            return Identifier(tok.value)

        if tok.type == TT_LPAREN:
            self._advance()
            node = self._or_expr()
            self._expect(TT_RPAREN)
            return node

        if tok.type == TT_LBRACKET:
            return self._list_literal()

        raise DSLSyntaxError(f"Unexpected token {tok.value!r} at position {tok.position}")

    def _list_literal(self) -> Node:
        self._advance()  # consume '['
        items: list[Node] = []

        if self._current.type != TT_RBRACKET:
            items.append(self._or_expr())
            while self._current.type == TT_COMMA:
                self._advance()
                items.append(self._or_expr())

        self._expect(TT_RBRACKET)
        return ListLiteral(tuple(items))
