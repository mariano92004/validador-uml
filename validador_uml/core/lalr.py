"""Construcción de la tabla LALR(1).

Método del libro del dragón (Aho, Lam, Sethi y Ullman, algoritmo 4.63):

1. Se arma la colección canónica de conjuntos de ítems LR(0) y sus
   transiciones (el autómata de prefijos viables).
2. Para cada ítem del núcleo se calcula la clausura LR(1) con un símbolo
   de anticipación ficticio «#». Lo que aparece distinto de «#» se genera
   espontáneamente; «#» indica que la anticipación se propaga.
3. Se propagan las anticipaciones hasta un punto fijo.
4. Con los núcleos y sus anticipaciones se llenan ACTION y GOTO.

El resultado tiene tantos estados como LR(0), pero con anticipaciones
LR(1) fusionadas: eso es LALR(1). Si quedan conflictos se registran;
las pruebas exigen que ninguna gramática del proyecto los tenga.
"""

from __future__ import annotations

from dataclasses import dataclass

from .grammar import END, Grammar

Item = tuple[int, int]          # (producción, posición del punto)

_DUMMY = "\0#"


@dataclass
class Conflict:
    state: int
    terminal: str
    first: tuple
    second: tuple

    @property
    def kind(self) -> str:
        kinds = {self.first[0], self.second[0]}
        return "desplazamiento/reducción" if "s" in kinds else "reducción/reducción"

    def __str__(self) -> str:
        return (f"conflicto {self.kind} en el estado {self.state} con «{self.terminal}»: "
                f"{self.first} contra {self.second}")


class ParseTable:
    def __init__(self, grammar: Grammar) -> None:
        self.grammar = grammar
        self.action: list[dict[str, tuple]] = []
        self.goto: list[dict[str, int]] = []
        self.kernels: list[tuple[Item, ...]] = []
        self.kernel_lookaheads: list[dict[Item, set[str]]] = []
        self.accessing: list[str | None] = []   # símbolo con el que se entra a cada estado
        self.conflicts: list[Conflict] = []
        self._build()

    # ------------------------------------------------------------------

    def _build(self) -> None:
        g = self.grammar
        P = g.productions
        nts = set(g.nonterminals)

        def closure0(kernel: tuple[Item, ...]) -> list[Item]:
            result = list(kernel)
            seen = set(kernel)
            i = 0
            while i < len(result):
                p, d = result[i]
                i += 1
                rhs = P[p].rhs
                if d < len(rhs) and rhs[d] in nts:
                    for q in g.by_lhs[rhs[d]]:
                        if (q, 0) not in seen:
                            seen.add((q, 0))
                            result.append((q, 0))
            return result

        # 1. Autómata LR(0)
        kernels: list[tuple[Item, ...]] = [((0, 0),)]
        index = {kernels[0]: 0}
        accessing: list[str | None] = [None]
        trans: list[dict[str, int]] = []
        i = 0
        while i < len(kernels):
            moves: dict[str, list[Item]] = {}
            for p, d in closure0(kernels[i]):
                rhs = P[p].rhs
                if d < len(rhs):
                    moves.setdefault(rhs[d], []).append((p, d + 1))
            t: dict[str, int] = {}
            for sym, adv in moves.items():
                k = tuple(sorted(set(adv)))
                if k not in index:
                    index[k] = len(kernels)
                    kernels.append(k)
                    accessing.append(sym)
                t[sym] = index[k]
            trans.append(t)
            i += 1

        # 2. Clausura LR(1) con conjuntos de anticipación
        suffix: dict[Item, tuple[frozenset[str], bool]] = {}

        def first_after(p: int, d: int) -> tuple[frozenset[str], bool]:
            key = (p, d)
            if key not in suffix:
                suffix[key] = g.first_seq(P[p].rhs[d:])
            return suffix[key]

        def closure1(kernel: dict[Item, set[str]]) -> dict[Item, set[str]]:
            res = {it: set(la) for it, la in kernel.items()}
            stack = list(res)
            while stack:
                it = stack.pop()
                p, d = it
                rhs = P[p].rhs
                if d < len(rhs) and rhs[d] in nts:
                    first, nullable = first_after(p, d + 1)
                    new = set(first)
                    if nullable:
                        new |= res[it]
                    for q in g.by_lhs[rhs[d]]:
                        cur = res.get((q, 0))
                        if cur is None:
                            res[(q, 0)] = set(new)
                            stack.append((q, 0))
                        elif not new <= cur:
                            cur |= new
                            stack.append((q, 0))
            return res

        # 3. Anticipaciones espontáneas y propagación
        la: list[dict[Item, set[str]]] = [{it: set() for it in k} for k in kernels]
        la[0][(0, 0)].add(END)
        propagate: dict[tuple[int, Item], list[tuple[int, Item]]] = {}
        for s, kernel in enumerate(kernels):
            for it in kernel:
                for (p, d), las in closure1({it: {_DUMMY}}).items():
                    rhs = P[p].rhs
                    if d >= len(rhs):
                        continue
                    j = trans[s][rhs[d]]
                    target = (p, d + 1)
                    for a in las:
                        if a == _DUMMY:
                            propagate.setdefault((s, it), []).append((j, target))
                        else:
                            la[j][target].add(a)

        changed = True
        while changed:
            changed = False
            for (s, it), targets in propagate.items():
                src = la[s][it]
                if not src:
                    continue
                for j, target in targets:
                    dst = la[j][target]
                    if not src <= dst:
                        dst |= src
                        changed = True

        # 4. Tablas ACTION y GOTO
        for s, kernel in enumerate(kernels):
            items = closure1({it: la[s][it] for it in kernel})
            act: dict[str, tuple] = {}
            for (p, d), las in sorted(items.items()):
                rhs = P[p].rhs
                if d < len(rhs):
                    x = rhs[d]
                    if x not in nts:
                        self._set(act, s, x, ("s", trans[s][x]))
                elif p == 0:
                    self._set(act, s, END, ("a", 0))
                else:
                    for a in sorted(las):
                        self._set(act, s, a, ("r", p))
            self.action.append(act)
            self.goto.append({x: j for x, j in trans[s].items() if x in nts})

        self.kernels = kernels
        self.kernel_lookaheads = la
        self.accessing = accessing

    def _set(self, act: dict[str, tuple], state: int, terminal: str, new: tuple) -> None:
        old = act.get(terminal)
        if old is None or old == new:
            act[terminal] = new
            return
        self.conflicts.append(Conflict(state, terminal, old, new))
        # Resolución clásica de yacc: se prefiere desplazar; entre dos
        # reducciones gana la producción escrita primero.
        if old[0] == "s":
            return
        if new[0] == "s" or (new[0] == "r" and new[1] < old[1]):
            act[terminal] = new

    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        return len(self.action)

    def item_text(self, item: Item, show=str) -> str:
        p, d = item
        return self.grammar.productions[p].text(show, dot=d)
