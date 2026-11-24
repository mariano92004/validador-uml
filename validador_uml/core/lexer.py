"""Analizador léxico guiado por expresiones regulares.

El léxico de cada diagrama es un lenguaje regular (tipo 3 en la jerarquía
de Chomsky): una lista ordenada de expresiones regulares. En cada posición
gana la primera regla que reconoce algo, así que el orden importa
(por ejemplo, las flechas van antes que los nombres para que «o--» no se
lea como el nombre «o»).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .diagnostics import ERROR, LEXICO, Diagnostic

NL = "NL"
END = "$"

_NAMED = re.compile(r"^[A-Z_]+$")


@dataclass
class Token:
    type: str
    value: str
    line: int
    col: int        # columna inicial, desde 1
    end_col: int    # columna final, exclusiva
    index: int = -1

    def to_list(self) -> list:
        return [self.type, self.value, self.line, self.col, self.end_col]


@dataclass
class _Rule:
    kind: str                   # token | ignore | comment | error | words
    regex: re.Pattern
    type: str | None = None
    message: str | None = None
    line_start: bool = False    # solo vale al comienzo de una línea
    keywords: bool = False      # el lexema puede ser una palabra reservada


class Lexer:
    """Una lista ordenada de reglas léxicas más un mapa de palabras reservadas."""

    def __init__(self, comment_hint: str = "") -> None:
        self.rules: list[_Rule] = []
        self.keywords: dict[str, str] = {}      # lexema -> tipo de token
        self.descriptions: dict[str, str] = {}  # tipo con nombre -> descripción
        self.types: list[str] = [NL]
        self.descriptions[NL] = "un salto de línea"
        self.comment_hint = comment_hint

    # -- construcción -------------------------------------------------------

    def _add_type(self, ttype: str) -> None:
        if ttype not in self.types:
            self.types.append(ttype)

    def ignore(self, pattern: str) -> None:
        self.rules.append(_Rule("ignore", re.compile(pattern)))

    def comment(self, pattern: str, line_start: bool = False) -> None:
        self.rules.append(_Rule("comment", re.compile(pattern), line_start=line_start))

    def token(self, ttype: str, pattern: str, desc: str | None = None,
              line_start: bool = False, keywords: bool = False) -> None:
        self.rules.append(_Rule("token", re.compile(pattern), ttype,
                                line_start=line_start, keywords=keywords))
        self._add_type(ttype)
        if desc:
            self.descriptions[ttype] = desc

    def literals(self, *symbols: str) -> None:
        """Signos sueltos: el tipo del token es el propio signo."""
        ordered = sorted(symbols, key=len, reverse=True)
        pattern = "|".join(re.escape(s) for s in ordered)
        self.rules.append(_Rule("token", re.compile(pattern), None))
        for s in symbols:
            self._add_type(s)

    def keyword(self, word: str, ttype: str | None = None) -> None:
        ttype = ttype or word
        self.keywords[word] = ttype
        self._add_type(ttype)

    def words(self, pattern: str, message: str) -> None:
        """Palabras que solo pueden ser reservadas: cualquier otra es un error."""
        self.rules.append(_Rule("words", re.compile(pattern), message=message))

    def error(self, pattern: str, message: str, line_start: bool = False) -> None:
        """Un error frecuente con un mensaje a medida."""
        self.rules.append(_Rule("error", re.compile(pattern), message=message,
                                line_start=line_start))

    # -- descripción --------------------------------------------------------

    def describe(self, ttype: str) -> str:
        if ttype == END:
            return "el final del texto"
        if ttype == "error":
            return "un error"
        if _NAMED.match(ttype):
            return self.descriptions.get(ttype, ttype)
        return f"«{ttype}»"

    def bnf(self, ttype: str) -> str:
        """Cómo se escribe el terminal en la gramática."""
        if ttype in (END, "error") or _NAMED.match(ttype):
            return ttype
        return f"'{ttype}'"

    # -- análisis -----------------------------------------------------------

    def tokenize(self, text: str) -> tuple[list[Token], list[Diagnostic], list[list[int]]]:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        pos, line, line_pos = 0, 1, 0
        at_line_start = True
        tokens: list[Token] = []
        diags: list[Diagnostic] = []
        comments: list[list[int]] = []
        n = len(text)

        while pos < n:
            rule, match = self._match(text, pos, at_line_start)
            col = pos - line_pos + 1

            if match is None:
                # Juntamos los caracteres seguidos que ninguna regla reconoce.
                end = pos + 1
                while end < n and not text[end].isspace() and \
                        self._match(text, end, False)[1] is None:
                    end += 1
                bad = text[pos:end]
                hint = self.comment_hint if bad[0] in "/%#'" else ""
                diags.append(Diagnostic(ERROR, LEXICO, "L01", f"Símbolo no reconocido: «{bad}».{hint}",
                                        line, col, col + len(bad)))
                pos = end
                at_line_start = False
                continue

            lexeme = match.group()
            newlines = lexeme.count("\n")
            end_col = col + len(lexeme) if not newlines else col + len(lexeme.split("\n", 1)[0])

            if rule.kind == "token":
                ttype = rule.type if rule.type is not None else lexeme
                if rule.keywords and lexeme in self.keywords:
                    ttype = self.keywords[lexeme]
                tokens.append(Token(ttype, lexeme, line, col, end_col))
                at_line_start = ttype == NL
            elif rule.kind == "words":
                if lexeme in self.keywords:
                    tokens.append(Token(self.keywords[lexeme], lexeme, line, col, end_col))
                else:
                    diags.append(Diagnostic(ERROR, LEXICO, "L02",
                                            rule.message.format(lexeme=lexeme),
                                            line, col, end_col))
                at_line_start = False
            elif rule.kind == "comment":
                comments.append([line, col, end_col])
            elif rule.kind == "error":
                diags.append(Diagnostic(ERROR, LEXICO, "L03", rule.message,
                                        line, col, end_col))
                at_line_start = False

            if newlines:
                line += newlines
                line_pos = pos + lexeme.rfind("\n") + 1
                if rule.kind != "token":
                    at_line_start = True
            pos = match.end()

        # Las líneas en blanco del comienzo no aportan nada.
        first = 0
        while first < len(tokens) and tokens[first].type == NL:
            first += 1
        tokens = tokens[first:]

        col = pos - line_pos + 1
        if tokens and tokens[-1].type != NL:
            tokens.append(Token(NL, "", line, col, col))
        tokens.append(Token(END, "", line, col, col))
        for i, tok in enumerate(tokens):
            tok.index = i
        return tokens, diags, comments

    def _match(self, text: str, pos: int, at_line_start: bool):
        for rule in self.rules:
            if rule.line_start and not at_line_start:
                continue
            m = rule.regex.match(text, pos)
            if m and m.end() > pos:
                return rule, m
        return None, None
