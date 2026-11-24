"""Punto de entrada único: lo usan la línea de comandos y la aplicación de escritorio.

Todas las funciones devuelven estructuras que se pueden pasar a JSON.
"""

from __future__ import annotations

from . import __version__
from .core import (AVISO, END, ERROR, LEXICO, SEMANTICA, SINTAXIS, Diagnostic, Node,
                   ParseResult, Token)
from .diagrams import KINDS, detect_kind, get_kind

_PHASE_ORDER = {LEXICO: 0, SINTAXIS: 1, SEMANTICA: 2}
_ACTION_CODE = {"s": "d", "r": "r", "a": "acc"}


_PHASE_NAME = {LEXICO: "léxica", SINTAXIS: "sintáctica", SEMANTICA: "semántica"}


def _internal(exc: Exception, phase: str) -> Diagnostic:
    """Un defecto del validador se informa como error, nunca como una excepción."""
    return Diagnostic(ERROR, phase, "I01",
                      f"Error interno del validador en la fase {_PHASE_NAME[phase]} "
                      f"({type(exc).__name__}). El diagrama no pudo revisarse por completo.", 1)


def analyze(kind_id: str, text: str, trace: bool = True, tree: bool = True) -> dict:
    """Analiza un diagrama en tres fases: léxico, sintaxis y semántica."""
    kind = get_kind(kind_id)
    internal: list[Diagnostic] = []

    try:
        tokens, lex_diags, comments = kind.lexer.tokenize(text)
    except Exception as exc:  # noqa: BLE001 - se informa como diagnóstico
        tokens, lex_diags, comments = [Token(END, "", 1, 1, 1)], [], []
        internal.append(_internal(exc, LEXICO))

    try:
        result = kind.parser.parse(tokens, trace=trace)
    except Exception as exc:  # noqa: BLE001
        result = ParseResult(False, None, Node("…"), [], [], False, 0, 0)
        internal.append(_internal(exc, SINTAXIS))

    sem_diags = []
    ran = False
    model = None
    if result.accepted and not lex_diags and not result.diagnostics and not internal:
        ran = True
        try:
            sem_diags = kind.check(result.value)
            model = kind.describe_model(result.value)
        except Exception as exc:  # noqa: BLE001
            sem_diags = [_internal(exc, SEMANTICA)]
            model = None

    diags = internal + lex_diags + result.diagnostics + sem_diags
    diags.sort(key=lambda d: (d.line, d.col, _PHASE_ORDER[d.phase]))
    errors = sum(d.severity == ERROR for d in diags)
    warnings = sum(d.severity == AVISO for d in diags)

    def count(phase: str, severity: str = ERROR) -> int:
        return sum(d.phase == phase and d.severity == severity for d in diags)

    return {
        "kind": kind.id,
        "ok": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "phases": {
            "lexico": {"tokens": max(0, len(tokens) - 1), "errors": count(LEXICO)},
            "sintaxis": {
                "accepted": result.accepted,
                "errors": count(SINTAXIS),
                "steps": result.shifts + result.reductions,
                "shifts": result.shifts,
                "reductions": result.reductions,
            },
            "semantica": {
                "ran": ran,
                "errors": count(SEMANTICA),
                "warnings": count(SEMANTICA, AVISO),
                "rules": len(kind.semantic_rules),
            },
        },
        "diagnostics": [d.to_dict() for d in diags],
        "tokens": [t.to_list() for t in tokens],
        "comments": comments,
        "trace": [[k, a, i, list(st)] for k, a, i, st in result.steps] if trace else [],
        "trace_truncated": result.truncated,
        "tree": result.tree.to_json() if tree else None,
        "model": model,
    }


def grammar_info(kind_id: str) -> dict:
    """La gramática, la tabla LALR(1) y los estados del autómata."""
    kind = get_kind(kind_id)
    g, t, lx = kind.grammar, kind.table, kind.lexer

    def show(sym: str) -> str:
        return lx.bnf(sym) if g.is_terminal(sym) else sym

    states = []
    for s, kernel in enumerate(t.kernels):
        items = []
        for item in kernel:
            la = sorted(t.kernel_lookaheads[s][item], key=lambda x: (x == "$", x))
            items.append([t.item_text(item, show), [show(a) for a in la]])
        acc = t.accessing[s]
        states.append({"sym": show(acc) if acc else None, "kernel": items})

    def encode(act: tuple) -> str:
        code = _ACTION_CODE[act[0]]
        return code if code == "acc" else f"{code}{act[1]}"

    return {
        "kind": kind.id,
        "start": g.start,
        "productions": [{"lhs": p.lhs, "rhs": [show(s) for s in p.rhs]} for p in g.productions],
        "terminals": [{"name": term, "bnf": lx.bnf(term), "desc": lx.describe(term)}
                      for term in g.terminals],
        "nonterminals": list(g.nonterminals),
        "action": [{a: encode(v) for a, v in row.items()} for row in t.action],
        "goto": t.goto,
        "states": states,
        "conflicts": [str(c) for c in t.conflicts],
    }


def catalog() -> dict:
    kinds = []
    for k in KINDS.values():
        kinds.append({
            "id": k.id,
            "name": k.name,
            "notation": k.notation,
            "extensions": list(k.extensions),
            "summary": k.summary,
            "help": k.help,
            "rules": [{"code": r.code, "severity": r.severity, "text": r.text}
                      for r in k.semantic_rules],
            "examples": {"correcto": k.example("correcto"), "errores": k.example("errores")},
        })
    return {"version": __version__, "kinds": kinds}


__all__ = ["analyze", "catalog", "detect_kind", "grammar_info"]
