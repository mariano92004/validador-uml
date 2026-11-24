"""Núcleo formal: léxico, gramáticas, tabla LALR(1) y analizador."""

from .diagnostics import AVISO, ERROR, LEXICO, SEMANTICA, SINTAXIS, Diagnostic
from .grammar import END, Grammar, GrammarError, Production
from .lalr import Conflict, ParseTable
from .lexer import NL, Lexer, Token
from .parser import Node, Parser, ParseResult

__all__ = [
    "AVISO", "ERROR", "LEXICO", "SEMANTICA", "SINTAXIS", "Diagnostic",
    "END", "Grammar", "GrammarError", "Production",
    "Conflict", "ParseTable",
    "NL", "Lexer", "Token",
    "Node", "Parser", "ParseResult",
]
