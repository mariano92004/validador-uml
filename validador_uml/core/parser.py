"""Analizador sintáctico por desplazamiento-reducción guiado por la tabla LALR(1).

El autómata mantiene una pila de estados. En cada paso mira el estado del
tope y el próximo token (la anticipación) y la tabla ACTION decide:

- desplazar: apila el token y pasa a otro estado;
- reducir por A → α: desapila |α| estados, ejecuta la acción semántica y
  apila GOTO[estado, A];
- aceptar: la entrada es una oración del lenguaje;
- error: no hay acción para ese par.

Ante un error se recupera al estilo yacc: busca en la pila un estado que
sepa desplazar el terminal «error», lo desplaza y descarta tokens hasta
poder seguir. Como las reglas «Linea → error NL» se sincronizan con el fin
de línea, se pueden informar varios errores en una sola pasada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .diagnostics import ERROR as SEV_ERROR, SINTAXIS, Diagnostic
from .grammar import END, ERROR
from .lalr import ParseTable
from .lexer import NL, Token

MAX_STEPS = 4000


@dataclass
class Node:
    """Nodo del árbol de derivación (árbol sintáctico concreto)."""
    symbol: str
    children: list["Node"] = field(default_factory=list)
    token: Token | None = None

    def to_json(self) -> dict:
        if self.token is not None:
            return {"s": self.symbol, "v": self.token.value, "l": self.token.line}
        return {"s": self.symbol, "c": [c.to_json() for c in self.children]}


@dataclass
class ParseResult:
    accepted: bool
    value: Any
    tree: Node
    diagnostics: list[Diagnostic]
    steps: list[tuple]          # (tipo, argumento, índice del token, pila de estados)
    truncated: bool
    shifts: int
    reductions: int


class Parser:
    def __init__(self, table: ParseTable, describe: Callable[[str], str]) -> None:
        self.table = table
        self.describe = describe

    def parse(self, tokens: list[Token], trace: bool = True,
              max_steps: int = MAX_STEPS) -> ParseResult:
        action, goto = self.table.action, self.table.goto
        prods = self.table.grammar.productions

        states: list[int] = [0]
        values: list[Any] = [None]
        nodes: list[Node | None] = [None]
        i = 0
        tok = tokens[0]
        errflag = 0
        diags: list[Diagnostic] = []
        steps: list[tuple] = []
        truncated = False
        accepted = False
        shifts = reductions = 0
        guard = 0

        def record(kind: str, arg: Any) -> None:
            nonlocal truncated
            if not trace:
                return
            if len(steps) < max_steps:
                steps.append((kind, arg, i, tuple(states)))
            else:
                truncated = True

        while True:
            guard += 1
            if guard > 500_000:   # no debería pasar nunca: cada vuelta avanza o reduce
                raise RuntimeError("el analizador no termina")

            act = action[states[-1]].get(tok.type)

            if act is None:
                if errflag == 0:
                    record("e", None)
                    diags.append(self._syntax_error(states, tok))
                if errflag == 3:
                    # Recién nos recuperamos y el token sigue sin servir: se descarta.
                    if tok.type == END:
                        break
                    record("x", None)
                    i += 1
                    tok = tokens[i]
                    continue
                errflag = 3
                while len(states) > 1:
                    e = action[states[-1]].get(ERROR)
                    if e is not None and e[0] == "s":
                        break
                    states.pop()
                    values.pop()
                    nodes.pop()
                e = action[states[-1]].get(ERROR)
                if e is None or e[0] != "s":
                    break          # no hay de dónde agarrarse: se abandona
                record("R", e[1])  # se desplaza el terminal «error»
                states.append(e[1])
                values.append(None)
                nodes.append(Node(ERROR))
                continue

            kind = act[0]
            if kind == "s":
                record("d", act[1])
                states.append(act[1])
                values.append(tok)
                nodes.append(Node(tok.type, token=tok))
                shifts += 1
                i += 1
                tok = tokens[i]
                if errflag:
                    errflag -= 1
            elif kind == "r":
                record("r", act[1])
                prod = prods[act[1]]
                n = len(prod.rhs)
                if n:
                    vals = values[-n:]
                    kids = nodes[-n:]
                    del states[-n:], values[-n:], nodes[-n:]
                else:
                    vals, kids = [], []
                value = prod.action(vals) if prod.action else (vals[0] if len(vals) == 1 else None)
                states.append(goto[states[-1]][prod.lhs])
                values.append(value)
                nodes.append(Node(prod.lhs, [k for k in kids if k is not None]))
                reductions += 1
            else:
                record("a", None)
                accepted = True
                break

        if accepted:
            tree = nodes[-1]
        else:
            tree = Node("…", [n for n in nodes[1:] if n is not None])
        return ParseResult(accepted, values[-1] if accepted else None, tree, diags,
                           steps, truncated, shifts, reductions)

    # ------------------------------------------------------------------

    def _viable(self, states: list[int], terminal: str) -> bool:
        """¿La pila actual llegaría a desplazar este terminal?

        En LALR(1) la fusión de estados puede sumar anticipaciones que en este
        contexto no sirven; simular las reducciones las descarta.
        """
        action, goto = self.table.action, self.table.goto
        prods = self.table.grammar.productions
        stack = list(states)
        for _ in range(1000):
            act = action[stack[-1]].get(terminal)
            if act is None:
                return False
            if act[0] != "r":
                return True
            prod = prods[act[1]]
            if prod.rhs:
                del stack[-len(prod.rhs):]
            stack.append(goto[stack[-1]][prod.lhs])
        return False

    def _syntax_error(self, states: list[int], tok: Token) -> Diagnostic:
        state = states[-1]
        expected = [t for t in self.table.grammar.terminals
                    if t in self.table.action[state] and t != ERROR and self._viable(states, t)]
        listed = [self.describe(t) for t in expected]
        if len(listed) > 7:
            listed = listed[:6] + [f"otras {len(listed) - 6} opciones"]
        options = _join(listed)

        if tok.type == END:
            msg = f"El texto termina antes de lo esperado. Se esperaba {options}."
        elif tok.type == NL:
            msg = f"La línea termina antes de lo esperado. Se esperaba {options}."
        elif expected == [NL]:
            msg = f"Sobra «{tok.value}»: la línea debería terminar antes."
        else:
            found = f"«{tok.value}»"
            desc = self.describe(tok.type)
            if not desc.startswith("«"):
                found += f" ({desc})"
            msg = f"Se encontró {found} donde se esperaba {options}."
        end = tok.end_col if tok.end_col > tok.col else tok.col + 1
        return Diagnostic(SEV_ERROR, SINTAXIS, "S01", msg, tok.line, tok.col, end)


def _join(items: list[str]) -> str:
    if not items:
        return "otra cosa"
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " o " + items[-1]
