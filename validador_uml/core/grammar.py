"""Gramáticas libres de contexto (tipo 2 en la jerarquía de Chomsky).

Las reglas se escriben como texto, una producción por regla:

    "Clase -> Cabecera CuerpoOpt"
    "Cabecera -> 'class' NOMBRE EsteOpt"
    "CuerpoOpt -> "                        (producción vacía, ε)

- Entre comillas simples: un terminal literal (palabra reservada o signo).
- En MAYÚSCULAS: un terminal con nombre (NOMBRE, TEXTO, NL, ...).
- El resto: no terminales; cada uno necesita al menos una producción.
- «error» es el terminal especial que usa la recuperación de errores.

Cada producción puede llevar una acción semántica: una función que recibe
los valores de los símbolos del lado derecho y devuelve el valor del lado
izquierdo. Así se arma el modelo del diagrama mientras se reduce.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

END = "$"
ERROR = "error"

_SYMBOL = re.compile(r"'[^']*'|\S+")
_NAMED = re.compile(r"^[A-Z_]+$")

Action = Callable[[list], Any]


class GrammarError(Exception):
    """La gramática está mal escrita (símbolo desconocido, no terminal inútil...)."""


@dataclass(eq=False)
class Production:
    index: int
    lhs: str
    rhs: tuple[str, ...]
    action: Action | None = field(default=None, repr=False)

    def text(self, show: Callable[[str], str] = str, dot: int | None = None) -> str:
        syms = [show(s) for s in self.rhs]
        if dot is not None:
            syms.insert(dot, "·")
        body = " ".join(syms) if syms else "ε"
        return f"{self.lhs} → {body}"


class Grammar:
    def __init__(self, rules: Iterable[tuple[str, Action | None]],
                 terminals: Iterable[str], start: str | None = None) -> None:
        parsed: list[tuple[str, tuple[str, ...], Action | None]] = []
        for spec, action in rules:
            lhs, arrow, rhs = spec.partition("->")
            lhs = lhs.strip()
            if not arrow or not lhs:
                raise GrammarError(f"Regla mal escrita: {spec!r}")
            syms = tuple(s[1:-1] if s.startswith("'") else s for s in _SYMBOL.findall(rhs))
            parsed.append((lhs, syms, action))
        if not parsed:
            raise GrammarError("La gramática no tiene reglas.")

        self.start = start or parsed[0][0]
        self.nonterminals: list[str] = []
        for lhs, _, _ in parsed:
            if lhs not in self.nonterminals:
                self.nonterminals.append(lhs)
        nts = set(self.nonterminals)

        declared = set(terminals) | {ERROR}
        self.terminals: list[str] = []
        for lhs, rhs, _ in parsed:
            for s in rhs:
                if s in nts:
                    continue
                if s not in declared:
                    kind = "terminal" if _NAMED.match(s) or not s[:1].isupper() else "no terminal"
                    raise GrammarError(f"{kind} desconocido {s!r} en «{lhs} -> {' '.join(rhs)}»")
                if s not in self.terminals:
                    self.terminals.append(s)
        self.terminals.append(END)

        self.augmented = self.start + "'"
        self.productions: list[Production] = [Production(0, self.augmented, (self.start,))]
        for lhs, rhs, action in parsed:
            self.productions.append(Production(len(self.productions), lhs, rhs, action))

        self.by_lhs: dict[str, list[int]] = {nt: [] for nt in self.nonterminals}
        for p in self.productions[1:]:
            self.by_lhs[p.lhs].append(p.index)

        self._compute_first()
        self._check_useful()

    # -- FIRST y anulables --------------------------------------------------

    def _compute_first(self) -> None:
        nts = set(self.nonterminals)
        self.nullable: set[str] = set()
        self.first: dict[str, set[str]] = {nt: set() for nt in self.nonterminals}
        changed = True
        while changed:
            changed = False
            for p in self.productions[1:]:
                if p.lhs not in self.nullable and all(s in self.nullable for s in p.rhs):
                    self.nullable.add(p.lhs)
                    changed = True
                acc: set[str] = set()
                for s in p.rhs:
                    if s in nts:
                        acc |= self.first[s]
                        if s not in self.nullable:
                            break
                    else:
                        acc.add(s)
                        break
                if not acc <= self.first[p.lhs]:
                    self.first[p.lhs] |= acc
                    changed = True

    def first_seq(self, seq: Iterable[str]) -> tuple[frozenset[str], bool]:
        """FIRST de una secuencia de símbolos y si la secuencia es anulable."""
        acc: set[str] = set()
        for s in seq:
            if s in self.first:
                acc |= self.first[s]
                if s not in self.nullable:
                    return frozenset(acc), False
            else:
                acc.add(s)
                return frozenset(acc), False
        return frozenset(acc), True

    # -- símbolos inútiles --------------------------------------------------

    def _check_useful(self) -> None:
        nts = set(self.nonterminals)
        productive: set[str] = set()
        changed = True
        while changed:
            changed = False
            for p in self.productions[1:]:
                if p.lhs not in productive and all(s not in nts or s in productive for s in p.rhs):
                    productive.add(p.lhs)
                    changed = True
        dead = [nt for nt in self.nonterminals if nt not in productive]
        if dead:
            raise GrammarError(f"No terminales que no generan ninguna cadena: {', '.join(dead)}")

        reachable = {self.start}
        stack = [self.start]
        while stack:
            nt = stack.pop()
            for i in self.by_lhs[nt]:
                for s in self.productions[i].rhs:
                    if s in nts and s not in reachable:
                        reachable.add(s)
                        stack.append(s)
        lost = [nt for nt in self.nonterminals if nt not in reachable]
        if lost:
            raise GrammarError(f"No terminales inalcanzables: {', '.join(lost)}")

    # -- presentación -------------------------------------------------------

    def is_terminal(self, symbol: str) -> bool:
        return symbol not in self.by_lhs and symbol != self.augmented
