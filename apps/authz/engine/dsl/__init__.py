"""
DSL (Domain-Specific Language) for authz policy conditions.

Provides a lexer, parser, and evaluator for expressions such as::

    principal.kind == "user" and resource.status == "active"
"""
