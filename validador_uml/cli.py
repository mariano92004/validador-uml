"""Línea de comandos.

    python -m validador_uml                      abre la aplicación
    python -m validador_uml abrir diagrama.puml  abre la aplicación con un archivo
    python -m validador_uml revisar diagrama.puml
    python -m validador_uml revisar flujo.mmd --traza
    python -m validador_uml gramatica clases --tabla
    python -m validador_uml ejemplo mcd --errores
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, api
from .diagrams import KINDS, detect_kind, get_kind


def _utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8-sig")


def cmd_revisar(args: argparse.Namespace) -> int:
    try:
        text = _read(args.archivo)
    except OSError as e:
        print(f"No se pudo leer {args.archivo}: {e.strerror or e}", file=sys.stderr)
        return 2
    kind_id = args.tipo or detect_kind(text, None if args.archivo == "-" else args.archivo)
    if kind_id is None:
        print("No se pudo determinar el tipo de diagrama. Debe indicarse con --tipo "
              f"({', '.join(KINDS)}).", file=sys.stderr)
        return 2

    result = api.analyze(kind_id, text, trace=args.traza or args.json, tree=args.json)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1

    origin = "<stdin>" if args.archivo == "-" else args.archivo
    kind = get_kind(kind_id)
    if args.traza:
        _print_trace(kind_id, result)
        print()

    for d in result["diagnostics"]:
        print(f"{origin}:{d['line']}:{d['col']}: {d['severity']} {d['code']}: {d['message']}")

    ph = result["phases"]
    sem = ph["semantica"]
    print()
    print(f"{kind.name} ({kind.notation}). {ph['lexico']['tokens']} tokens, "
          f"{ph['sintaxis']['shifts']} desplazamientos y {ph['sintaxis']['reductions']} reducciones.")
    if not sem["ran"]:
        print("La validación semántica no se ejecutó: requiere un léxico y una sintaxis sin errores.")
    if result["ok"]:
        extra = f", con {result['warnings']} aviso{'s' if result['warnings'] != 1 else ''}" \
            if result["warnings"] else ""
        print(f"Correcto{extra}.")
    else:
        e, w = result["errors"], result["warnings"]
        print(f"{e} error{'es' if e != 1 else ''} y {w} aviso{'s' if w != 1 else ''}.")
    return 0 if result["ok"] else 1


def _print_trace(kind_id: str, result: dict) -> None:
    info = api.grammar_info(kind_id)
    syms = [s["sym"] for s in info["states"]]
    prods = info["productions"]
    tokens = result["tokens"]
    rows = []
    for n, (kind, arg, la, states) in enumerate(result["trace"], 1):
        stack = "0"
        for s in states[1:]:
            stack += f" {syms[s]} {s}"
        rest = " ".join(_tok(t) for t in tokens[la:la + 4])
        if kind == "d":
            act = f"desplazar {arg}"
        elif kind == "r":
            p = prods[arg]
            act = f"reducir r{arg}: {p['lhs']} → {' '.join(p['rhs']) or 'ε'}"
        elif kind == "a":
            act = "aceptar"
        elif kind == "e":
            act = "error"
        elif kind == "R":
            act = f"recuperar: desplazar error {arg}"
        else:
            act = "descartar token"
        rows.append((str(n), stack, rest, act))
    w0 = max([4] + [len(r[0]) for r in rows])
    w1 = min(max((len(r[1]) for r in rows), default=4), 60)
    w2 = min(max((len(r[2]) for r in rows), default=7), 32)
    print(f"{'Paso':>{w0}}  {'Pila':<{w1}}  {'Entrada':<{w2}}  Acción")
    for n, stack, rest, act in rows:
        if len(stack) > w1:
            stack = "…" + stack[-(w1 - 1):]
        if len(rest) > w2:
            rest = rest[:w2 - 1] + "…"
        print(f"{n:>{w0}}  {stack:<{w1}}  {rest:<{w2}}  {act}")
    if result["trace_truncated"]:
        print("(traza truncada)")


def _tok(t: list) -> str:
    ttype, value = t[0], t[1]
    if ttype == "$":
        return "$"
    if ttype == "NL":
        return "⏎"
    return value if len(value) <= 14 else value[:13] + "…"


def cmd_gramatica(args: argparse.Namespace) -> int:
    info = api.grammar_info(args.tipo)
    kind = get_kind(args.tipo)
    print(f"Gramática del diagrama de {kind.name.lower()} ({kind.notation})\n")
    width = max(len(p["lhs"]) for p in info["productions"])
    prev = None
    for i, p in enumerate(info["productions"]):
        lhs = p["lhs"] if p["lhs"] != prev else ""
        sep = "→" if lhs else "|"
        print(f"r{i:<3} {lhs:>{width}} {sep} {' '.join(p['rhs']) or 'ε'}")
        prev = p["lhs"]
    n_states = len(info["states"])
    conflicts = info["conflicts"]
    print(f"\n{len(info['productions']) - 1} producciones, {len(info['terminals'])} terminales, "
          f"{len(info['nonterminals'])} no terminales y {n_states} estados LALR(1). "
          + ("Sin conflictos." if not conflicts else f"{len(conflicts)} conflictos."))
    for c in conflicts:
        print("  ", c)

    if args.estados:
        print()
        for s, st in enumerate(info["states"]):
            print(f"Estado {s}" + (f" (se entra con {st['sym']})" if st["sym"] else ""))
            for item, la in st["kernel"]:
                print(f"    {item}    [{', '.join(la)}]")
    if args.tabla:
        print()
        terms = [t["name"] for t in info["terminals"]]
        heads = [t["bnf"] for t in info["terminals"]] + info["nonterminals"]
        print("estado\t" + "\t".join(heads))
        for s, row in enumerate(info["action"]):
            cells = [row.get(t, "") for t in terms]
            cells += [str(info["goto"][s].get(nt, "")) for nt in info["nonterminals"]]
            print(f"{s}\t" + "\t".join(cells))
    return 0


def cmd_ejemplo(args: argparse.Namespace) -> int:
    print(get_kind(args.tipo).example("errores" if args.errores else "correcto"), end="")
    return 0


def cmd_tipos(args: argparse.Namespace) -> int:
    for k in KINDS.values():
        print(f"{k.id:<10} {k.name} ({k.notation}, {', '.join(k.extensions)}). {k.summary}")
    return 0


def cmd_abrir(args: argparse.Namespace) -> int:
    from .escritorio.ventana import main as ventana
    archivo = getattr(args, "archivo", None)
    if archivo and not Path(archivo).is_file():
        print(f"No existe el archivo {archivo}.", file=sys.stderr)
        return 2
    return ventana(archivo)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="validador-uml",
        description="Revisa diagramas UML tratándolos como lenguajes formales "
                    "(léxico, gramática LALR(1) y reglas semánticas).")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="comando")
    p.set_defaults(func=cmd_abrir)

    a = sub.add_parser("abrir", help="abre la aplicación (opcionalmente con un archivo)")
    a.add_argument("archivo", nargs="?")
    a.set_defaults(func=cmd_abrir)

    r = sub.add_parser("revisar", help="revisa un diagrama")
    r.add_argument("archivo", help="archivo del diagrama, o - para leer de la entrada estándar")
    r.add_argument("--tipo", choices=list(KINDS), help="tipo de diagrama (si no, lo adivina)")
    r.add_argument("--traza", action="store_true", help="muestra los pasos del analizador")
    r.add_argument("--json", action="store_true", help="resultado completo en JSON")
    r.set_defaults(func=cmd_revisar)

    g = sub.add_parser("gramatica", help="muestra la gramática de un tipo de diagrama")
    g.add_argument("tipo", choices=list(KINDS))
    g.add_argument("--tabla", action="store_true", help="incluye la tabla ACTION/GOTO")
    g.add_argument("--estados", action="store_true", help="incluye los ítems de cada estado")
    g.set_defaults(func=cmd_gramatica)

    e = sub.add_parser("ejemplo", help="imprime un diagrama de ejemplo")
    e.add_argument("tipo", choices=list(KINDS))
    e.add_argument("--errores", action="store_true", help="el ejemplo con errores")
    e.set_defaults(func=cmd_ejemplo)

    t = sub.add_parser("tipos", help="lista los tipos de diagrama")
    t.set_defaults(func=cmd_tipos)

    return p


def main(argv: list[str] | None = None) -> int:
    _utf8_output()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
