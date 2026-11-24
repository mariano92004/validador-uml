"""Diagrama de actividad, con la sintaxis nueva de PlantUML.

Es un lenguaje estructurado: if/endif, while/endwhile y fork/end fork se
anidan como paréntesis balanceados. Por eso la gramática ya garantiza que
cada bloque abierto se cierre (algo que una expresión regular no puede).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core import Lexer
from .base import (AVISO, ERROR, Checker, DiagramKind, Loc, Marker,
                   SemanticRule as R, append, empty, first, loc, nothing,
                   check_markers, plantuml_base)

# -- modelo --------------------------------------------------------------------


@dataclass
class Simple:
    kind: str                 # start, stop, end, kill, detach, accion, carril, flecha
    text: str
    at: Loc


@dataclass
class Branch:
    guard: str | None         # condición (if / elseif) o None para else
    label: str | None         # etiqueta de la rama: then (sí), else (no)
    body: list
    at: Loc


@dataclass
class If:
    branches: list[Branch]
    otherwise: Branch | None
    at: Loc


@dataclass
class Loop:
    kind: str                 # while o repeat
    cond: str
    body: list
    at: Loc


@dataclass
class Parallel:
    kind: str                 # fork o split
    branches: list[list]
    at: Loc


@dataclass
class Switch:
    cond: str
    prelude: list
    cases: list[Branch]
    at: Loc


@dataclass
class Partition:
    name: str
    body: list
    at: Loc


@dataclass
class ActivityModel:
    body: list = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)


# -- léxico --------------------------------------------------------------------

def _lexer() -> Lexer:
    lx = Lexer(" Los comentarios empiezan con '.")
    plantuml_base(lx)
    multi = [
        ("fork again", r"fork[ \t]+again\b"),
        ("end fork", r"end[ \t]*(?:fork|merge)\b"),
        ("split again", r"split[ \t]+again\b"),
        ("end split", r"end[ \t]*split\b"),
        ("repeat while", r"repeat[ \t]+while\b"),
        ("endif", r"end[ \t]*if\b"),
        ("endwhile", r"end[ \t]*while\b"),
        ("endswitch", r"end[ \t]*switch\b"),
        ("elseif", r"else[ \t]*if\b"),
    ]
    for ttype, pattern in multi:
        lx.token(ttype, pattern)
    lx.token("ACCION", r":[^;\n]*;", "una acción (:texto;)")
    lx.error(r":[^;\n]*", "A la acción le falta el «;» del final.")
    lx.token("FLECHA", r"->[^;\n]*;", "una flecha con etiqueta (-> texto;)")
    lx.token("CONDICION", r"\((?:[^()\n]|\([^()\n]*\))*\)", "una condición entre paréntesis")
    lx.token("CARRIL", r"\|[^|\n]+\|", "un carril (|Nombre|)")
    lx.token("PARTICION", r"partition\b[^{\n]*", "una partición", line_start=True)
    for kw in ("start", "stop", "end", "kill", "detach", "if", "then", "else", "while", "is",
               "repeat", "not", "fork", "split", "switch", "case"):
        lx.keyword(kw)
    lx.words(r"[^\W\d]\w*", "«{lexeme}» no es una palabra clave. Las acciones se escriben "
                            "entre «:» y «;», por ejemplo :{lexeme};")
    lx.literals("{", "}")
    return lx


# -- gramática y acciones ------------------------------------------------------

def _simple(kind):
    return lambda v: Simple(kind, v[0].value, loc(v[0]))


def _action(v):
    return Simple("accion", v[0].value[1:-1].strip(), loc(v[0]))


def _cond(tok) -> str:
    return tok.value[1:-1].strip()


def _if(v):
    # 'if' CONDICION 'then' EtiqOpt NL Lineas Sinos ElseOpt 'endif'
    head = Branch(_cond(v[1]), v[3], v[5], loc(v[0]))
    return If([head] + v[6], v[7], loc(v[0]))


def _elseif(v):
    # Sinos 'elseif' CONDICION 'then' EtiqOpt NL Lineas
    return v[0] + [Branch(_cond(v[2]), v[4], v[6], loc(v[1]))]


def _doc(v):
    model = ActivityModel()

    def walk(items):
        out = []
        for s in items:
            if isinstance(s, Marker):
                model.markers.append(s)
            elif s is not None:
                out.append(s)
        return out

    model.body = walk(v[0])
    return model


RULES = [
    ("Doc -> Lineas", _doc),
    ("Lineas -> Lineas Linea", append),
    ("Lineas -> ", empty),
    ("Linea -> Sent NL", first),
    ("Linea -> NL", nothing),
    ("Linea -> error NL", nothing),
    ("Sent -> 'start'", _simple("start")),
    ("Sent -> 'stop'", _simple("stop")),
    ("Sent -> 'end'", _simple("end")),
    ("Sent -> 'kill'", _simple("kill")),
    ("Sent -> 'detach'", _simple("detach")),
    ("Sent -> ACCION", _action),
    ("Sent -> CARRIL", lambda v: Simple("carril", v[0].value[1:-1].strip(), loc(v[0]))),
    ("Sent -> FLECHA", lambda v: Simple("flecha", v[0].value[2:-1].strip(), loc(v[0]))),
    ("Sent -> MARCA", lambda v: Marker(v[0].value, loc(v[0]))),
    ("Sent -> DIRECTIVA", nothing),
    ("Sent -> Si", first),
    ("Sent -> Mientras", first),
    ("Sent -> Repetir", first),
    ("Sent -> Paralelo", first),
    ("Sent -> Seleccion", first),
    ("Sent -> Particion", first),

    ("Si -> 'if' CONDICION 'then' EtiqOpt NL Lineas Sinos ElseOpt 'endif'", _if),
    ("Sinos -> Sinos 'elseif' CONDICION 'then' EtiqOpt NL Lineas", _elseif),
    ("Sinos -> ", empty),
    ("ElseOpt -> 'else' EtiqOpt NL Lineas", lambda v: Branch(None, v[1], v[3], loc(v[0]))),
    ("ElseOpt -> ", nothing),
    ("EtiqOpt -> CONDICION", lambda v: _cond(v[0])),
    ("EtiqOpt -> ", nothing),

    ("Mientras -> 'while' CONDICION EsOpt NL Lineas 'endwhile' EtiqOpt",
     lambda v: Loop("while", _cond(v[1]), v[4], loc(v[0]))),
    ("EsOpt -> 'is' CONDICION", lambda v: _cond(v[1])),
    ("EsOpt -> ", nothing),
    ("Repetir -> 'repeat' NL Lineas 'repeat while' CONDICION EsOpt NoOpt",
     lambda v: Loop("repeat", _cond(v[4]), v[2], loc(v[0]))),
    ("NoOpt -> 'not' CONDICION", nothing),
    ("NoOpt -> ", nothing),

    ("Paralelo -> 'fork' NL Lineas Ramas 'end fork'",
     lambda v: Parallel("fork", [v[2]] + v[3], loc(v[0]))),
    ("Ramas -> Ramas 'fork again' NL Lineas", lambda v: v[0] + [v[3]]),
    ("Ramas -> ", empty),
    ("Paralelo -> 'split' NL Lineas RamasSplit 'end split'",
     lambda v: Parallel("split", [v[2]] + v[3], loc(v[0]))),
    ("RamasSplit -> RamasSplit 'split again' NL Lineas", lambda v: v[0] + [v[3]]),
    ("RamasSplit -> ", empty),

    ("Seleccion -> 'switch' CONDICION NL Lineas Casos 'endswitch'",
     lambda v: Switch(_cond(v[1]), v[3], v[4], loc(v[0]))),
    ("Casos -> Casos Caso", append),
    ("Casos -> Caso", lambda v: [v[0]]),
    ("Caso -> 'case' CONDICION NL Lineas", lambda v: Branch(_cond(v[1]), _cond(v[1]), v[3], loc(v[0]))),

    ("Particion -> PARTICION '{' Lineas '}'",
     lambda v: Partition(v[0].value[len("partition"):].strip(), v[2], loc(v[0]))),
]

# -- reglas semánticas ---------------------------------------------------------

SEMANTIC_RULES = [
    R("A01", ERROR, "La actividad tiene un nodo inicial (start)."),
    R("A02", ERROR, "Hay un solo start y es lo primero del flujo."),
    R("A03", ERROR, "Todo camino termina en un nodo final (stop o end)."),
    R("A04", ERROR, "No hay acciones después de un nodo final en el mismo camino."),
    R("A05", AVISO, "Una decisión tiene rama else, para que las guardas cubran todos los casos."),
    R("A06", ERROR, "Las condiciones de decisiones y bucles no están vacías."),
    R("A07", AVISO, "Las ramas de una misma decisión tienen etiquetas distintas."),
    R("A08", AVISO, "Las ramas y los bucles no están vacíos."),
    R("A09", AVISO, "Un fork tiene al menos dos ramas: si no, no hay concurrencia."),
    R("A10", ERROR, "Las acciones tienen texto."),
    R("A11", AVISO, "Un stop dentro de una rama concurrente termina toda la actividad."),
    R("A12", AVISO, "Si se usan carriles, el diagrama empieza con uno."),
    R("A13", ERROR, "En un switch, todo va dentro de algún case."),
    R("A14", AVISO, "Si el diagrama usa @startuml, también cierra con @enduml (y al revés)."),
    R("A15", AVISO, "Un switch tiene al menos dos casos."),
]

_FINAL = ("stop", "end", "kill", "detach")


def _flow(stmts: list) -> list:
    """Sin carriles, flechas ni particiones: solo lo que forma el flujo."""
    out = []
    for s in stmts:
        if isinstance(s, Partition):
            out.extend(_flow(s.body))
        elif isinstance(s, Simple) and s.kind in ("carril", "flecha"):
            continue
        else:
            out.append(s)
    return out


def _at(s) -> Loc:
    return s.at


def check(model: ActivityModel):
    c = Checker(SEMANTIC_RULES)
    check_markers(c, model.markers, "A14")
    body = model.body

    starts: list[Simple] = []
    _collect(body, lambda s: isinstance(s, Simple) and s.kind == "start", starts)
    flow = _flow(body)
    if not starts:
        at = _at(flow[0]) if flow else Loc(1, 1, 2)
        c.report("A01", "Falta el nodo inicial: el flujo empieza con start.", at)
    else:
        if flow and flow[0] is not starts[0]:
            c.report("A02", "start debe ser lo primero del flujo.", starts[0].at)
        for s in starts[1:]:
            c.report("A02", f"Ya hay un start en la línea {starts[0].at.line}.", s.at)

    lanes = [s for s in body if isinstance(s, Simple) and s.kind == "carril"]
    if lanes and body and body[0] is not lanes[0]:
        c.report("A12", "Hay carriles, pero el diagrama no empieza con uno.", body[0].at)

    ends = _block(c, body, in_fork=False)
    if not ends:
        last = flow[-1] if flow else None
        at = last.at if last else Loc(1, 1, 2)
        c.report("A03", "El flujo llega al final sin un nodo final (stop o end).", at)
    return c.diagnostics


def _collect(stmts, pred, out) -> None:
    for s in stmts:
        if pred(s):
            out.append(s)
        for sub in _children(s):
            _collect(sub, pred, out)


def _children(s) -> list[list]:
    if isinstance(s, If):
        return [b.body for b in s.branches] + ([s.otherwise.body] if s.otherwise else [])
    if isinstance(s, Loop):
        return [s.body]
    if isinstance(s, Parallel):
        return s.branches
    if isinstance(s, Switch):
        return [s.prelude] + [b.body for b in s.cases]
    if isinstance(s, Partition):
        return [s.body]
    return []


def _block(c: Checker, stmts: list, in_fork: bool) -> bool:
    """Revisa un bloque y devuelve True si todos sus caminos terminan."""
    terminated = False
    for s in _flow(stmts):
        if terminated:
            c.report("A04", "Instrucción inalcanzable: está después de un nodo final.", s.at)
            return True
        terminated = _statement(c, s, in_fork)
    return terminated


def _statement(c: Checker, s, in_fork: bool) -> bool:
    if isinstance(s, Simple):
        if s.kind == "accion" and not s.text:
            c.report("A10", "La acción está vacía.", s.at)
        if s.kind == "stop" and in_fork:
            c.report("A11", "Este stop termina todas las ramas del fork. Para terminar solo "
                            "esta rama corresponde end o kill.", s.at)
        return s.kind in _FINAL

    if isinstance(s, If):
        labels: dict[str, Loc] = {}
        all_end = True
        for b in s.branches + ([s.otherwise] if s.otherwise else []):
            if b.guard is not None and not b.guard:
                c.report("A06", "La condición está vacía.", b.at)
            if b.label:
                key = b.label.lower()
                if key in labels:
                    c.report("A07", f"La etiqueta «{b.label}» se repite en esta decisión.", b.at)
                labels[key] = b.at
            if not _flow(b.body):
                c.report("A08", "Esta rama no tiene acciones.", b.at)
            all_end = _block(c, b.body, in_fork) and all_end
        if s.otherwise is None:
            c.report("A05", "La decisión no tiene else: no está definido qué ocurre si ninguna condición se cumple.", s.at)
            return False
        return all_end

    if isinstance(s, Loop):
        if not s.cond:
            c.report("A06", "La condición del bucle está vacía.", s.at)
        if not _flow(s.body):
            c.report("A08", "El bucle no tiene acciones.", s.at)
        ends = _block(c, s.body, in_fork)
        return ends if s.kind == "repeat" else False   # un while puede no ejecutarse nunca

    if isinstance(s, Parallel):
        if len(s.branches) < 2:
            c.report("A09", f"El {s.kind} tiene una sola rama.", s.at)
        results = []
        for b in s.branches:
            if not _flow(b):
                c.report("A08", f"Una rama del {s.kind} no tiene acciones.", s.at)
            results.append(_block(c, b, in_fork=True))
        return all(results) and bool(results)

    if isinstance(s, Switch):
        if not s.cond:
            c.report("A06", "La condición del switch está vacía.", s.at)
        if _flow(s.prelude):
            c.report("A13", "Hay acciones antes del primer case.", _flow(s.prelude)[0].at)
        if len(s.cases) < 2:
            c.report("A15", "El switch tiene un solo case.", s.at)
        labels = {}
        for b in s.cases:
            key = (b.label or "").lower()
            if key in labels:
                c.report("A07", f"El caso «{b.label}» se repite.", b.at)
            labels[key] = b.at
            if not _flow(b.body):
                c.report("A08", "Este case no tiene acciones.", b.at)
            _block(c, b.body, in_fork)
        return False

    return False


# -- resumen ---------------------------------------------------------------------

def describe(model: ActivityModel) -> dict:
    counts = {"acciones": 0, "decisiones": 0, "bucles": 0, "paralelos": 0, "finales": 0}
    lanes: list[str] = []
    rows_actions = []

    def walk(stmts):
        for s in stmts:
            if isinstance(s, Simple):
                if s.kind == "accion":
                    counts["acciones"] += 1
                    if len(rows_actions) < 60:
                        rows_actions.append([s.text or "(vacía)", f"Acción en la línea {s.at.line}.",
                                             s.at.line])
                elif s.kind in _FINAL:
                    counts["finales"] += 1
                elif s.kind == "carril" and s.text not in lanes:
                    lanes.append(s.text)
            elif isinstance(s, If):
                counts["decisiones"] += 1
            elif isinstance(s, Switch):
                counts["decisiones"] += 1
            elif isinstance(s, Loop):
                counts["bucles"] += 1
            elif isinstance(s, Parallel):
                counts["paralelos"] += 1
            for sub in _children(s):
                walk(sub)

    walk(model.body)
    summary = [
        ["Acciones", str(counts["acciones"]), None],
        ["Decisiones", str(counts["decisiones"]), None],
        ["Bucles", str(counts["bucles"]), None],
        ["Bloques paralelos", str(counts["paralelos"]), None],
        ["Nodos finales", str(counts["finales"]), None],
    ]
    if lanes:
        summary.append(["Carriles", ", ".join(lanes), None])
    sections = [{"title": "Resumen", "rows": summary}]
    if rows_actions:
        sections.append({"title": "Acciones", "rows": rows_actions})
    return {"sections": sections}


HELP = """
start
:Recibir pedido;
if (¿Hay stock?) then (sí)
  :Reservar productos;
else (no)
  :Avisar al cliente;
  stop
endif
fork
  :Facturar;
fork again
  :Preparar envío;
end fork
while (¿Quedan paquetes?) is (sí)
  :Despachar paquete;
endwhile (no)
stop
"""

KIND = DiagramKind(
    id="actividad",
    name="Actividad",
    notation="PlantUML",
    extensions=(".puml",),
    summary="Acciones, decisiones, bucles, fork y carriles, con la sintaxis nueva de PlantUML.",
    lexer=_lexer(),
    rules=RULES,
    semantic_rules=SEMANTIC_RULES,
    check=check,
    describe_model=describe,
    help=HELP,
)
