"""DSL engine tests for the authz app."""

from __future__ import annotations

import pytest

from apps.authz.engine.dsl.ast_nodes import BinaryOp, GetAttr, Literal
from apps.authz.engine.dsl.evaluator import EvaluationContext, Evaluator
from apps.authz.engine.dsl.lexer import Lexer
from apps.authz.engine.dsl.parser import Parser
from apps.authz.exceptions import DSLEvaluationError, DSLSyntaxError

# ---------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------


class TestLexer:
    def test_simple_tokens(self):
        tokens = list(Lexer('a == "hello"').tokenize())
        # IDENTIFIER, COMP, STRING, EOF
        assert len(tokens) == 4
        assert tokens[0].type == "IDENTIFIER"
        assert tokens[1].type == "COMP"
        assert tokens[2].type == "STRING"
        assert tokens[2].value == "hello"
        assert tokens[3].type == "EOF"

    def test_numeric_tokens(self):
        tokens = list(Lexer("42 3.14").tokenize())
        assert tokens[0].value == 42
        assert tokens[1].value == 3.14

    def test_keywords(self):
        tokens = list(Lexer("true false null and or not in contains").tokenize())
        types = [t.type for t in tokens[:-1]]  # exclude EOF
        assert types == [
            "TRUE",
            "FALSE",
            "NULL",
            "AND",
            "OR",
            "NOT",
            "IN",
            "CONTAINS",
        ]

    def test_comparison_operators(self):
        tokens = list(Lexer("== != < <= > >=").tokenize())
        values = [t.value for t in tokens if t.type == "COMP"]
        assert values == ["==", "!=", "<", "<=", ">", ">="]

    def test_dot_notation(self):
        tokens = list(Lexer("a.b.c").tokenize())
        types = [t.type for t in tokens[:-1]]  # exclude EOF
        assert types == ["IDENTIFIER", "DOT", "IDENTIFIER", "DOT", "IDENTIFIER"]

    def test_invalid_character(self):
        with pytest.raises(DSLSyntaxError, match="Unexpected character"):
            list(Lexer("a @ b").tokenize())


# ---------------------------------------------------------------
# Parser
# ---------------------------------------------------------------


class TestParser:
    def test_simple_comparison(self):
        ast = Parser('action == "read"').parse()
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "=="

    def test_attribute_access(self):
        ast = Parser("principal.kind").parse()
        assert isinstance(ast, GetAttr)
        assert ast.attr == "kind"

    def test_nested_attribute_access(self):
        ast = Parser("principal.metadata.level").parse()
        assert isinstance(ast, GetAttr)
        assert isinstance(ast.obj, GetAttr)

    def test_logical_and(self):
        ast = Parser("a and b").parse()
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "and"

    def test_logical_or(self):
        ast = Parser("a or b").parse()
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "or"

    def test_not_operator(self):
        from apps.authz.engine.dsl.ast_nodes import UnaryOp

        ast = Parser("not a").parse()
        assert isinstance(ast, UnaryOp)
        assert ast.operator == "not"

    def test_in_operator(self):
        ast = Parser('a in ["x", "y"]').parse()
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "in"

    def test_contains_operator(self):
        ast = Parser('"hello" contains "ell"').parse()
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "contains"

    def test_parenthesized_expression(self):
        ast = Parser("(a or b) and c").parse()
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "and"

    def test_complex_expression(self):
        ast = Parser('principal.kind == "user" and resource.status == "active"').parse()
        assert isinstance(ast, BinaryOp)
        assert ast.operator == "and"

    def test_syntax_error_unexpected_token(self):
        with pytest.raises(DSLSyntaxError):
            Parser("a ==").parse()

    def test_syntax_error_trailing_token(self):
        with pytest.raises(DSLSyntaxError, match="Unexpected token"):
            Parser("a b").parse()

    def test_list_literal_empty(self):
        ast = Parser("[]").parse()
        from apps.authz.engine.dsl.ast_nodes import ListLiteral

        assert isinstance(ast, ListLiteral)
        assert ast.items == ()

    def test_boolean_literals(self):
        ast_true = Parser("true").parse()
        ast_false = Parser("false").parse()
        assert isinstance(ast_true, Literal) and ast_true.value is True
        assert isinstance(ast_false, Literal) and ast_false.value is False

    def test_null_literal(self):
        ast = Parser("null").parse()
        assert isinstance(ast, Literal) and ast.value is None


# ---------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------


class TestEvaluator:
    def _eval(self, source: str, **kwargs) -> object:
        ast = Parser(source).parse()
        ctx = EvaluationContext(**kwargs)
        return Evaluator(ctx).evaluate(ast)

    def test_literal_true(self):
        assert self._eval("true") is True

    def test_literal_false(self):
        assert self._eval("false") is False

    def test_literal_null(self):
        assert self._eval("null") is None

    def test_string_equality(self):
        assert self._eval('action == "read"', action="read") is True
        assert self._eval('action == "write"', action="read") is False

    def test_numeric_comparison(self):
        assert self._eval("environment.hour >= 9", environment={"hour": 10}) is True
        assert self._eval("environment.hour >= 9", environment={"hour": 5}) is False

    def test_and_short_circuit(self):
        assert self._eval("false and true") is False

    def test_or_short_circuit(self):
        assert self._eval("true or false") is True

    def test_not_operator(self):
        assert self._eval("not false") is True
        assert self._eval("not true") is False

    def test_in_list(self):
        assert self._eval('action in ["read", "list"]', action="read") is True
        assert self._eval('action in ["read", "list"]', action="write") is False

    def test_contains(self):
        assert self._eval('"hello world" contains "world"') is True
        assert self._eval('"hello world" contains "xyz"') is False

    def test_attribute_access_on_object(self):
        class MockPrincipal:
            kind = "user"

        assert self._eval('principal.kind == "user"', principal=MockPrincipal()) is True

    def test_attribute_access_on_dict(self):
        assert (
            self._eval(
                'environment.region == "us-east"',
                environment={"region": "us-east"},
            )
            is True
        )

    def test_nested_dict_access(self):
        assert (
            self._eval(
                "principal.metadata.level >= 5",
                principal=type("P", (), {"metadata": {"level": 7}})(),
            )
            is True
        )

    def test_null_propagation(self):
        """Accessing an attribute on None should return None, not crash."""
        assert self._eval("principal.missing_attr", principal=None) is None

    def test_unknown_variable(self):
        with pytest.raises(DSLEvaluationError, match="Unknown variable"):
            self._eval("unknown == 1")

    def test_complex_expression(self):
        class MockPrincipal:
            kind = "user"
            is_staff = True

        class MockResource:
            status = "active"

        result = self._eval(
            '(principal.kind == "user" or principal.is_staff) and resource.status == "active"',
            principal=MockPrincipal(),
            resource=MockResource(),
        )
        assert result is True

    def test_in_on_none_returns_false(self):
        result = self._eval("action in null", action="read")
        assert result is False
