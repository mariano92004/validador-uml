"""Diagrama de flujo, con sintaxis de Mermaid (flowchart).

A diferencia del diagrama de actividad, acá el texto describe un grafo:
nodos y aristas en cualquier orden. La gramática solo asegura que cada
línea esté bien formada; las propiedades del flujo (un inicio, decisiones
con dos salidas, todo alcanzable, todo llega a un fin) se revisan después,
recorriendo el grafo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core import Lexer
from .base import (AVISO, ERROR, Checker, DiagramKind, Loc, SemanticRule as R,
                   append, empty, first, loc, nothing)

# -- modelo --------------------------------------------------------------------


@dataclass
class NodeRef:
    id: str
    shape: str | None         # None si se nombra sin forma
    label: str | None
    at: Loc


@dataclass
class Edge:
    src: NodeRef
    dst: NodeRef
    arrow: str
    label: str | None
    at: Loc


@dataclass
class Chain:
    refs: list[NodeRef]
    edges: list[Edge]


@dataclass
class FlowModel:
    direction: str | None = None
    refs: list[NodeRef] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


# -- léxico --------------------------------------------------------------------

# (forma, apertura, cierre). El orden importa: «(((» antes que «((» y que «(».
_SHAPE_DELIMS = [
    ("terminal", "([", "])"),       # ([Inicio])
    ("terminal", "(((", ")))"),     # (((Fin)))
    ("conector", "((", "))"),       # ((A))
    ("subproceso", "[[", "]]"),     # [[Subrutina]]
    ("datos", "[(", ")]"),          # [(Base de datos)]
    ("es", "[/", "/]"),             # [/Leer N/]
    ("es", "[\\", "\\]"),           # [\Mostrar\]
    ("proceso", "[/", "\\]"),       # trapecio
    ("proceso", "[\\", "/]"),       # trapecio invertido
    ("proceso", "{{", "}}"),        # {{Preparación}}
    ("decision", "{", "}"),         # {¿N > 0?}
    ("proceso", ">", "]"),          # >Asimétrico]
    ("terminal", "(", ")"),         # (Inicio)
    ("proceso", "[", "]"),          # [Proceso]
]


def _shape_pattern(open_: str, close: str) -> str:
    inner = rf'(?:"[^"\n]*"|[^{re.escape(close[0])}\n]*)'
    return re.escape(open_) + inner + re.escape(close)


SHAPES = [(kind, o, cl, re.compile(_shape_pattern(o, cl) + "$")) for kind, o, cl in _SHAPE_DELIMS]

_ARROW = r"<-{2,}>|<={2,}>|-{2,}>|={2,}>|-\.+->|-{2,}[xo]\b|-{3,}|={3,}|-\.+-"
_ARROW_TEXT = r"--[ \t]+[^\n]*?[ \t]+-{2,}>|==[ \t]+[^\n]*?[ \t]+={2,}>|-\.[ \t]+[^\n]*?[ \t]+\.+->"


def _lexer() -> Lexer:
    lx = Lexer(" Los comentarios empiezan con %%.")
    lx.ignore(r"[ \t]+")
    lx.comment(r"%%[^\n]*")
    lx.ignore(r":::[\w-]+")
    lx.token("NL", r"\n|;")
    lx.token("CABECERA", r"(?:flowchart|graph)\b(?:[ \t]+(?:TD|TB|BT|RL|LR))?",
             "la cabecera (flowchart TD)", line_start=True)
    lx.token("DIRECTIVA", r"(?:classDef|class|style|linkStyle|click|direction)\b[^\n]*",
             "una directiva de estilo", line_start=True)
    lx.token("SUBGRAFO", r"subgraph\b[^\n]*", "un subgrafo", line_start=True)
    lx.token("FLECHA_TEXTO", _ARROW_TEXT, "una flecha con texto (-- texto -->)")
    lx.token("FLECHA", _ARROW, "una flecha (-->)")
    lx.token("ETIQUETA", r"\|[^|\n]*\|", "una etiqueta (|texto|)")
    lx.token("FORMA", "|".join(_shape_pattern(o, cl) for _, o, cl in _SHAPE_DELIMS),
             "una forma ([...], {...}, ([...]), [/.../])")
    lx.error(r"[\[({][^\n]*", "La forma del nodo no está cerrada.")
    lx.token("NOMBRE", r"\w+", "el identificador de un nodo", keywords=True)
    lx.keyword("end")
    return lx


# -- gramática y acciones ------------------------------------------------------

def _shape(text: str) -> tuple[str, str]:
    for kind, open_, close, rx in SHAPES:
        if rx.match(text):
            inner = text[len(open_):len(text) - len(close)].strip()
            if len(inner) >= 2 and inner[0] == inner[-1] == '"':
                inner = inner[1:-1]
            return kind, inner
    return "proceso", text


def _node(v):
    if len(v) == 1:
        return NodeRef(v[0].value, None, None, loc(v[0]))
    kind, label = _shape(v[1].value)
    at = loc(v[0])
    return NodeRef(v[0].value, kind, label, Loc(at.line, at.col, loc(v[1]).end))


def _link(v):
    tok = v[0]
    if tok.type == "FLECHA_TEXTO":
        m = re.match(r"(--|==|-\.)[ \t]+(.*?)[ \t]+(-{2,}>|={2,}>|\.+->)$", tok.value)
        return ("-->", m.group(2).strip() if m else None, loc(tok))
    label = v[1].value[1:-1].strip() if len(v) > 1 else None
    return (tok.value, label, loc(tok))


def _arrow_kind(arrow: str) -> str:
    if arrow.startswith("<"):
        return "doble"
    if arrow.endswith(">") or arrow[-1] in "xo":
        return "dirigida"
    return "sin_direccion"


def _chain_start(v):
    arrow, label, at = v[1]
    return Chain([v[0], v[2]], [Edge(v[0], v[2], arrow, label, at)])


def _chain_more(v):
    chain: Chain = v[0]
    arrow, label, at = v[1]
    prev = chain.refs[-1]
    chain.refs.append(v[2])
    chain.edges.append(Edge(prev, v[2], arrow, label, at))
    return chain


def _doc(v):
    model = FlowModel()
    head = v[0]
    if head is not None:
        parts = head.value.split()
        model.direction = parts[1] if len(parts) > 1 else None

    def walk(items):
        for s in items:
            if isinstance(s, NodeRef):
                model.refs.append(s)
            elif isinstance(s, Chain):
                model.refs.extend(s.refs)
                model.edges.extend(s.edges)
            elif isinstance(s, list):
                walk(s)

    walk(v[2])
    return model


RULES = [
    ("Doc -> Cabecera NL Lineas", _doc),
    ("Cabecera -> CABECERA", first),
    ("Cabecera -> error", nothing),
    ("Lineas -> Lineas Linea", append),
    ("Lineas -> ", empty),
    ("Linea -> Sent NL", first),
    ("Linea -> NL", nothing),
    ("Linea -> error NL", nothing),
    ("Sent -> Nodo", first),
    ("Sent -> Cadena", first),
    ("Sent -> DIRECTIVA", nothing),
    ("Sent -> Subgrafo", first),
    ("Cadena -> Nodo Enlace Nodo", _chain_start),
    ("Cadena -> Cadena Enlace Nodo", _chain_more),
    ("Enlace -> FLECHA", _link),
    ("Enlace -> FLECHA ETIQUETA", _link),
    ("Enlace -> FLECHA_TEXTO", _link),
    ("Nodo -> NOMBRE", _node),
    ("Nodo -> NOMBRE FORMA", _node),
    ("Subgrafo -> SUBGRAFO NL Lineas 'end'", lambda v: v[2]),
]

# -- reglas semánticas ---------------------------------------------------------

SEMANTIC_RULES = [
    R("F01", ERROR, "Un nodo tiene una sola forma."),
    R("F02", AVISO, "Todo nodo tiene forma; si no, Mermaid lo dibuja como un proceso."),
    R("F03", ERROR, "Hay exactamente un terminal de inicio."),
    R("F04", ERROR, "Hay al menos un terminal de fin."),
    R("F05", ERROR, "Un terminal es de inicio (solo salidas) o de fin (solo entradas)."),
    R("F06", ERROR, "Una decisión tiene al menos dos salidas."),
    R("F07", ERROR, "Cada salida de una decisión tiene una etiqueta distinta (sí / no)."),
    R("F08", ERROR, "Un proceso o una entrada/salida tiene exactamente una salida."),
    R("F09", ERROR, "Todo nodo se alcanza desde el inicio."),
    R("F10", ERROR, "Desde cada nodo se puede llegar a un fin."),
    R("F11", ERROR, "Las líneas de un diagrama de flujo tienen dirección (-->)."),
    R("F12", AVISO, "Solo las salidas de una decisión llevan etiqueta."),
    R("F13", AVISO, "No hay nodos sueltos."),
    R("F14", AVISO, "Una misma flecha no se repite."),
    R("F15", AVISO, "Una decisión con más de dos salidas se lee mejor como decisiones anidadas."),
    R("F16", AVISO, "Un nodo conserva el mismo texto en todas sus apariciones."),
]

_SHAPE_NAME = {
    "terminal": "terminal", "conector": "conector", "subproceso": "subproceso",
    "datos": "almacenamiento", "es": "entrada/salida", "proceso": "proceso", "decision": "decisión",
}


def check(model: FlowModel):
    c = Checker(SEMANTIC_RULES)

    nodes: dict[str, NodeRef] = {}
    for ref in model.refs:
        known = nodes.get(ref.id)
        if known is None:
            nodes[ref.id] = ref
            continue
        if ref.shape is None:
            continue
        if known.shape is None:
            nodes[ref.id] = ref
        elif known.shape != ref.shape:
            c.report("F01", f"«{ref.id}» ya era un {_SHAPE_NAME[known.shape]} (línea {known.at.line}) "
                            f"y acá es un {_SHAPE_NAME[ref.shape]}.", ref.at)
        elif (known.label or "") != (ref.label or ""):
            c.report("F16", f"«{ref.id}» decía «{known.label}» y acá dice «{ref.label}».", ref.at)

    if not nodes:
        c.report("F03", "El diagrama no tiene nodos.", Loc(1, 1, 2))
        return c.diagnostics

    for n in nodes.values():
        if n.shape is None:
            c.report("F02", f"«{n.id}» no tiene forma: se dibuja como un proceso con su identificador "
                            "como texto.", n.at)

    shape = {nid: (n.shape or "proceso") for nid, n in nodes.items()}
    out: dict[str, list[Edge]] = {nid: [] for nid in nodes}
    inc: dict[str, list[Edge]] = {nid: [] for nid in nodes}
    seen: set[tuple] = set()
    for e in model.edges:
        kind = _arrow_kind(e.arrow)
        if kind == "sin_direccion":
            c.report("F11", f"La línea «{e.arrow}» no tiene dirección; corresponde «-->».", e.at)
        elif kind == "doble":
            c.report("F11", f"La flecha «{e.arrow}» va en los dos sentidos: el flujo tiene una sola "
                            "dirección.", e.at)
        key = (e.src.id, e.dst.id, e.label)
        if key in seen:
            c.report("F14", f"La flecha de «{e.src.id}» a «{e.dst.id}» se repite.", e.at)
            continue
        seen.add(key)
        out[e.src.id].append(e)
        inc[e.dst.id].append(e)

    starts, finals = [], []
    for nid, n in nodes.items():
        if shape[nid] != "terminal":
            continue
        if inc[nid] and out[nid]:
            c.report("F05", f"El terminal «{n.label or nid}» tiene entradas y salidas: un terminal "
                            "es inicio o fin.", n.at)
        elif out[nid]:
            starts.append(nid)
        elif inc[nid]:
            finals.append(nid)

    if not starts:
        c.report("F03", "No hay terminal de inicio: un nodo ([Inicio]) con una sola salida.",
                 next(iter(nodes.values())).at)
    for nid in starts[1:]:
        c.report("F03", f"Hay más de un inicio: {starts[0]} y {nid}. El flujo empieza en un solo "
                        "terminal.", nodes[nid].at)
    if not finals:
        c.report("F04", "No hay terminal de fin: un nodo ([Fin]) al que solo llegan flechas.",
                 next(iter(nodes.values())).at)

    for nid, n in nodes.items():
        k = shape[nid]
        outs = out[nid]
        if not outs and not inc[nid]:
            c.report("F13", f"«{n.label or nid}» no está conectado con nada.", n.at)
            continue
        if k == "decision":
            if len(outs) < 2:
                c.report("F06", f"La decisión «{n.label or nid}» tiene {len(outs)} salida"
                                f"{'s' if len(outs) != 1 else ''}: necesita al menos dos.", n.at)
            elif len(outs) > 2:
                c.report("F15", f"La decisión «{n.label or nid}» tiene {len(outs)} salidas.", n.at)
            labels: dict[str, Edge] = {}
            for e in outs:
                if not e.label:
                    c.report("F07", f"La salida de «{n.label or nid}» hacia «{e.dst.id}» no tiene "
                                     "etiqueta (por ejemplo -->|sí| o -->|no|).", e.at)
                elif e.label.lower() in labels:
                    c.report("F07", f"Dos salidas de «{n.label or nid}» dicen «{e.label}».", e.at)
                else:
                    labels[e.label.lower()] = e
        else:
            for e in outs:
                if e.label:
                    c.report("F12", f"«{n.label or nid}» no es una decisión: la etiqueta «{e.label}» "
                                     "sobra.", e.at)
            if k in ("proceso", "es", "subproceso", "datos") and inc[nid]:
                if not outs:
                    c.report("F08", f"El flujo se corta en «{n.label or nid}»: le falta una salida.", n.at)
                elif len(outs) > 1:
                    c.report("F08", f"«{n.label or nid}» tiene {len(outs)} salidas: para bifurcar "
                                     "se usa una decisión.", n.at)

    if starts:
        reach = _reach(starts[0], out, lambda e: e.dst.id)
        for nid, n in nodes.items():
            if nid not in reach and (inc[nid] or out[nid]) and nid not in starts:
                c.report("F09", f"No se llega a «{n.label or nid}» desde el inicio.", n.at)
        if finals:
            back = set()
            for f in finals:
                back |= _reach(f, inc, lambda e: e.src.id)
            stuck = [nid for nid in nodes if nid in reach and nid not in back and out[nid]]
            if stuck:
                names = ", ".join(f"«{nodes[n].label or n}»" for n in stuck[:6])
                more = f" y {len(stuck) - 6} más" if len(stuck) > 6 else ""
                c.report("F10", f"Desde {names}{more} no se llega a ningún fin: hay un bucle sin salida.",
                         nodes[stuck[0]].at)
    return c.diagnostics


def _reach(start: str, edges: dict[str, list[Edge]], nxt) -> set[str]:
    seen = {start}
    stack = [start]
    while stack:
        n = stack.pop()
        for e in edges[n]:
            m = nxt(e)
            if m not in seen:
                seen.add(m)
                stack.append(m)
    return seen


# -- resumen ---------------------------------------------------------------------

def describe(model: FlowModel) -> dict:
    nodes: dict[str, NodeRef] = {}
    for ref in model.refs:
        if ref.id not in nodes or (nodes[ref.id].shape is None and ref.shape):
            nodes[ref.id] = ref
    rows = [[n.id, f"{_SHAPE_NAME[n.shape or 'proceso'].capitalize()}"
                   + (f": {n.label}." if n.label else "."), n.at.line] for n in nodes.values()]
    edges = [[f"{e.src.id} {e.arrow} {e.dst.id}", f"Etiqueta «{e.label}»." if e.label else "Sin etiqueta.",
              e.at.line] for e in model.edges]
    sections = [{"title": "Nodos", "rows": rows}]
    if edges:
        sections.append({"title": "Flechas", "rows": edges})
    if model.direction:
        sections.insert(0, {"title": "Dirección", "rows": [["Orientación", model.direction, None]]})
    return {"sections": sections}


HELP = """
flowchart TD
  %% Formas: ([terminal]) [proceso] [/entrada o salida/] {decisión} [[subproceso]]
  I([Inicio]) --> L[/Leer N/]
  L --> D{¿N > 0?}
  D -->|sí| S[Sumar N]
  D -->|no| M[/Mostrar suma/]
  S --> L
  M --> F([Fin])
"""

KIND = DiagramKind(
    id="flujo",
    name="Flujo",
    notation="Mermaid",
    extensions=(".mmd", ".mermaid"),
    summary="Diagrama de flujo clásico escrito como flowchart de Mermaid.",
    lexer=_lexer(),
    rules=RULES,
    semantic_rules=SEMANTIC_RULES,
    check=check,
    describe_model=describe,
    help=HELP,
)
