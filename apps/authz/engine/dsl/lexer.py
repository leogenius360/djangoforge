"""
Lexer (tokenizer) for the authz DSL.

Converts a source string into a stream of ``Token`` objects consumed by
the parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from apps.authz.exceptions import DSLSyntaxError

if TYPE_CHECKING:
    from collections.abc import Iterator

# Token type constants
TT_NUMBER = "NUMBER"
TT_STRING = "STRING"
TT_IDENTIFIER = "IDENTIFIER"
TT_COMP = "COMP"
TT_DOT = "DOT"
TT_COMMA = "COMMA"
TT_LPAREN = "LPAREN"
TT_RPAREN = "RPAREN"
TT_LBRACKET = "LBRACKET"
TT_RBRACKET = "RBRACKET"
TT_NOT_OP = "NOT_OP"
TT_EOF = "EOF"

# Keywords are promoted from IDENTIFIER to their own token type.
KEYWORDS = frozenset({"and", "or", "not", "true", "false", "null", "in", "contains"})

# Ordered list of (regex_pattern, token_type | None).
# ``None`` means the match is skipped (whitespace / comments).
_TOKEN_RULES: list[tuple[str, str | None]] = [
    (r"\s+", None),
    (r"#[^\n]*", None),
    (r"==|!=|<=|>=|<|>", TT_COMP),
    (r"&&", "AND"),
    (r"\|\|", "OR"),
    (r"\.", TT_DOT),
    (r",", TT_COMMA),
    (r"\(", TT_LPAREN),
    (r"\)", TT_RPAREN),
    (r"\[", TT_LBRACKET),
    (r"\]", TT_RBRACKET),
    (r"!", TT_NOT_OP),
    (r'"[^"]*"', TT_STRING),
    (r"'[^']*'", TT_STRING),
    (r"\d+(?:\.\d+)?", TT_NUMBER),
    (r"[a-zA-Z_][a-zA-Z0-9_]*", TT_IDENTIFIER),
]

_COMPILED_RULES: list[tuple[re.Pattern[str], str | None]] = [(re.compile(pat), tt) for pat, tt in _TOKEN_RULES]


@dataclass(frozen=True, slots=True)
class Token:
    """A single lexical token."""

    type: str
    value: Any
    position: int


class Lexer:
    """Tokenizes a DSL source string."""

    def __init__(self, source: str) -> None:
        self.source = source

    def tokenize(self) -> Iterator[Token]:
        """Yield tokens from the source string."""
        pos = 0
        length = len(self.source)

        while pos < length:
            matched = False
            for regex, token_type in _COMPILED_RULES:
                m = regex.match(self.source, pos)
                if m is None:
                    continue

                raw = m.group(0)
                if token_type is not None:
                    value: Any = raw
                    tt = token_type

                    if tt == TT_IDENTIFIER and raw in KEYWORDS:
                        tt = raw.upper()  # e.g. "and" -> "AND"
                    elif tt == TT_STRING:
                        value = raw[1:-1]
                    elif tt == TT_NUMBER:
                        value = float(raw) if "." in raw else int(raw)

                    yield Token(type=tt, value=value, position=pos)

                pos = m.end()
                matched = True
                break

            if not matched:
                raise DSLSyntaxError(f"Unexpected character at position {pos}: {self.source[pos]!r}")

        yield Token(type=TT_EOF, value=None, position=pos)
