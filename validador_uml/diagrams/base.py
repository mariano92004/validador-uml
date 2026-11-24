"""Piezas comunes a todos los tipos de diagrama."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property
from importlib import resources
from typing import Any, Callable

from ..core import (AVISO, ERROR, SEMANTICA, Diagnostic, Grammar, Lexer,
                    ParseTable, Parser, Token)


@dataclass(frozen=True)
class SemanticRule:
    code: str
    severity: str     # "error" o "aviso"
    text: str


@dataclass(frozen=True)
class Loc:
    line: int
    col: int
    end: int


def loc(tok: Token) -> Loc:
    return Loc(tok.line, tok.col, tok.end_col if tok.end_col > tok.col else tok.col + 1)


def span(a: Loc, b: Loc) -> Loc:
    """Desde a hasta b, si están en la misma línea."""
    return Loc(a.line, a.col, b.end if b.line == a.line else a.end)


class Checker:
    """Junta los diagnósticos semánticos. Cada código tiene que estar documentado."""

    def __init__(self, rules: list[SemanticRule]) -> None:
        self.rules = {r.code: r for r in rules}
        self.diagnostics: list[Diagnostic] = []

    def report(self, code: str, message: str, at: Loc) -> None:
        rule = self.rules[code]
        self.diagnostics.append(Diagnostic(rule.severity, SEMANTICA, code, message,
                                           at.line, at.col, at.end))


# -- acciones semánticas genéricas -------------------------------------------

def append(v: list) -> list:
    """Lista -> Lista Elemento"""
    if v[1] is not None:
        v[0].append(v[1])
    return v[0]


def extend(v: list) -> list:
    """Lista -> Lista SubLista"""
    if v[1]:
        v[0].extend(v[1])
    return v[0]


def empty(v: list) -> list:
    return []


def single(v: list) -> list:
    return [v[0]] if v[0] is not None else []


def first(v: list) -> Any:
    return v[0]


def second(v: list) -> Any:
    return v[1]


def nothing(v: list) -> None:
    return None


def text_of(tok: Token) -> str:
    """El texto de un token, sin comillas ni delimitadores."""
    value = tok.value
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


# -- léxico compartido por los diagramas tipo PlantUML -------------------------

_DIRECTIVES = (r"(?:title|skinparam|hide|show|scale|caption|header|footer|legend|"
               r"left[ \t]+to[ \t]+right[ \t]+direction|top[ \t]+to[ \t]+bottom[ \t]+direction|"
               r"allowmixing|!theme|!pragma|!include)\b[^\n]*")

# Flechas: «-» sólido, «.» punteado, con dirección opcional (-up->, -left-, ...)
_D = r"-+(?:(?:up|down|left|right|u|d|l|r)-+)?"
_P = r"\.+(?:(?:up|down|left|right|u|d|l|r)\.+)?"
UML_ARROW = (rf"<\|{_D}|{_D}\|>|<\|{_P}|{_P}\|>|\*-{{2,}}|-{{2,}}\*|o-{{2,}}|-{{2,}}o\b|"
             rf"<{_D}|{_D}>|<{_P}|{_P}>|-{{2,}}|\.{{2,}}")


def normalize_arrow(arrow: str) -> str:
    a = re.sub(r"up|down|left|right|[udlr]", "", arrow)
    a = re.sub(r"-+", "--", a)
    return re.sub(r"\.+", "..", a)


def plantuml_base(lx: Lexer) -> None:
    lx.ignore(r"[ \t]+")
    lx.comment(r"/'[\s\S]*?'/")
    lx.comment(r"'[^\n]*")
    lx.comment(r"note\b[^\n:]*\n[\s\S]*?\n[ \t]*end[ \t]?note\b", line_start=True)
    lx.token("DIRECTIVA", r"note\b[^\n]*:[^\n]*", "una directiva de PlantUML", line_start=True)
    lx.token("NL", r"\n")
    lx.token("MARCA", r"@startuml\b[^\n]*|@enduml\b", "una marca @startuml o @enduml",
             line_start=True)
    lx.token("DIRECTIVA", _DIRECTIVES, line_start=True)


def quoted_text(lx: Lexer) -> None:
    """Texto entre comillas, con un error a medida si falta cerrarlas."""
    lx.token("TEXTO", r'"[^"\n]*"', "un texto entre comillas")
    lx.error(r'"[^"\n]*', "Faltan las comillas de cierre.")


@dataclass
class Marker:
    text: str
    at: Loc


def check_markers(c: Checker, markers: list[Marker], code: str) -> None:
    starts = [m for m in markers if m.text.startswith("@start")]
    ends = [m for m in markers if m.text.startswith("@end")]
    if starts and not ends:
        c.report(code, "Hay @startuml pero falta @enduml al final.", starts[0].at)
    elif ends and not starts:
        c.report(code, "Hay @enduml pero falta @startuml al comienzo.", ends[0].at)


# -- tipo de diagrama ----------------------------------------------------------

class DiagramKind:
    def __init__(self, *, id: str, name: str, notation: str, extensions: tuple[str, ...],
                 summary: str, lexer: Lexer, rules: list[tuple[str, Callable | None]],
                 semantic_rules: list[SemanticRule],
                 check: Callable[[Any], list[Diagnostic]],
                 describe_model: Callable[[Any], dict],
                 help: str) -> None:
        self.id = id
        self.name = name
        self.notation = notation
        self.extensions = extensions
        self.summary = summary
        self.lexer = lexer
        self.rules = rules
        self.semantic_rules = semantic_rules
        self.check = check
        self.describe_model = describe_model
        self.help = help.strip("\n")

    @cached_property
    def grammar(self) -> Grammar:
        return Grammar(self.rules, self.lexer.types)

    @cached_property
    def table(self) -> ParseTable:
        return ParseTable(self.grammar)

    @cached_property
    def parser(self) -> Parser:
        return Parser(self.table, self.lexer.describe)

    def example(self, variant: str = "correcto") -> str:
        name = f"{self.id}_{variant}{self.extensions[0]}"
        return resources.files("validador_uml").joinpath("ejemplos", name).read_text("utf-8")


__all__ = [
    "AVISO", "ERROR", "Checker", "DiagramKind", "Loc", "Marker", "SemanticRule",
    "UML_ARROW", "append", "check_markers", "empty", "extend", "first", "loc",
    "normalize_arrow", "nothing", "plantuml_base", "quoted_text", "second", "single", "span",
    "text_of",
]
