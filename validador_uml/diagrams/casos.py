"""Diagrama de casos de uso, con sintaxis basada en PlantUML."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core import Lexer
from .base import (AVISO, ERROR, Checker, DiagramKind, Loc, Marker,
                   SemanticRule as R, append, check_markers, empty, first, loc,
                   normalize_arrow, nothing, plantuml_base, quoted_text, single,
                   text_of)

# -- modelo --------------------------------------------------------------------


@dataclass
class Ref:
    text: str            # cómo se escribió
    form: str            # "nombre", "caso" (entre paréntesis) o "actor" (entre dos puntos)
    at: Loc


@dataclass
class Element:
    kind: str            # "actor" o "caso"
    label: str           # el texto que se ve
    alias: str | None    # el identificador para referirlo
    stereotype: str | None
    boundary: str | None
    at: Loc
    implicit: bool = False


@dataclass
class Boundary:
    name: str
    body: list
    at: Loc


@dataclass
class Link:
    left: Ref
    right: Ref
    arrow: str
    label: str | None
    at: Loc


@dataclass
class UseCaseModel:
    elements: list[Element] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    boundaries: list[Boundary] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)


# -- léxico --------------------------------------------------------------------

_D = r"-+(?:(?:up|down|left|right|u|d|l|r)-+)?"
_P = r"\.+(?:(?:up|down|left|right|u|d|l|r)\.+)?"
_ARROW = rf"<\|{_D}|{_D}\|>|<\|{_P}|{_P}\|>|<{_D}|{_D}>|<{_P}|{_P}>|-{{2,}}|\.{{2,}}"


def _lexer() -> Lexer:
    lx = Lexer(" Los comentarios empiezan con '.")
    plantuml_base(lx)
    lx.token("ESTEREOTIPO", r"<<[^<>\n]+>>", "un estereotipo, como <<include>>")
    lx.token("FLECHA", _ARROW, "una flecha (-->, --, ..>, <|--)")
    quoted_text(lx)
    lx.token("CASO", r"\([^()\n]+\)", "un caso de uso entre paréntesis")
    lx.token("ACTOR_CORTO", r":[^:\s][^:\n]*:", "un actor entre dos puntos")
    lx.token("NOMBRE", r"[^\W\d]\w*", "un nombre", keywords=True)
    for kw in ("actor", "usecase", "as", "rectangle", "package"):
        lx.keyword(kw)
    lx.literals("{", "}", ":")
    return lx


# -- gramática y acciones ------------------------------------------------------

def _strip(tok) -> tuple[str, str]:
    v = tok.value
    if tok.type == "CASO":
        return v[1:-1].strip(), "caso"
    if tok.type == "ACTOR_CORTO":
        return v[1:-1].strip(), "actor"
    return text_of(tok), "nombre"


def _decl(kind):
    def build(v):
        name_tok, alias, stereo = v[1], v[2], v[3]
        return _element(kind, name_tok, alias, stereo)
    return build


def _decl_short(v):
    kind = "caso" if v[0].type == "CASO" else "actor"
    return _element(kind, v[0], v[1], v[2])


def _element(kind, name_tok, alias, stereo):
    label, _ = _strip(name_tok)
    ident = None
    if alias is not None:
        # «usecase UC1 as "Comprar"» y «usecase "Comprar" as UC1» valen lo mismo.
        if alias.type == "NOMBRE":
            ident = alias.value
        else:
            ident = label if name_tok.type == "NOMBRE" else None
            label = _strip(alias)[0]
    elif name_tok.type == "NOMBRE":
        ident = name_tok.value
    st = stereo.value[2:-2].strip() if stereo else None
    return Element(kind, label, ident, st, None, loc(name_tok))


def _ref(v):
    label, form = _strip(v[0])
    return Ref(label if form != "nombre" else v[0].value, form, loc(v[0]))


def _boundary(v):
    label, _ = _strip(v[1])
    return Boundary(label, v[3], loc(v[1]))


def _doc(v):
    model = UseCaseModel()

    def walk(items, boundary):
        for s in items:
            if isinstance(s, Element):
                s.boundary = boundary
                model.elements.append(s)
            elif isinstance(s, Link):
                model.links.append(s)
            elif isinstance(s, Boundary):
                model.boundaries.append(s)
                walk(s.body, s.name)
            elif isinstance(s, Marker):
                model.markers.append(s)

    walk(v[0], None)
    return model


RULES = [
    ("Doc -> Lineas", _doc),
    ("Lineas -> Lineas Linea", append),
    ("Lineas -> ", empty),
    ("Linea -> Sent NL", first),
    ("Linea -> NL", nothing),
    ("Linea -> error NL", nothing),
    ("Sent -> Declaracion", first),
    ("Sent -> Relacion", first),
    ("Sent -> Sistema", first),
    ("Sent -> MARCA", lambda v: Marker(v[0].value, loc(v[0]))),
    ("Sent -> DIRECTIVA", nothing),

    ("Declaracion -> 'actor' Nombre AliasOpt EsteOpt", _decl("actor")),
    ("Declaracion -> 'usecase' Nombre AliasOpt EsteOpt", _decl("caso")),
    ("Declaracion -> CASO AliasOpt EsteOpt", _decl_short),
    ("Declaracion -> ACTOR_CORTO AliasOpt EsteOpt", _decl_short),
    ("Nombre -> NOMBRE", first),
    ("Nombre -> TEXTO", first),
    ("Nombre -> CASO", first),
    ("Nombre -> ACTOR_CORTO", first),
    ("AliasOpt -> 'as' NOMBRE", lambda v: v[1]),
    ("AliasOpt -> 'as' TEXTO", lambda v: v[1]),
    ("AliasOpt -> 'as' CASO", lambda v: v[1]),
    ("AliasOpt -> ", nothing),
    ("EsteOpt -> ESTEREOTIPO", first),
    ("EsteOpt -> ", nothing),

    ("Sistema -> Frontera Nombre '{' Lineas '}'", _boundary),
    ("Frontera -> 'rectangle'", first),
    ("Frontera -> 'package'", first),

    ("Relacion -> Ref FLECHA Ref EtiqOpt",
     lambda v: Link(v[0], v[2], normalize_arrow(v[1].value), v[3], loc(v[1]))),
    ("Ref -> NOMBRE", _ref),
    ("Ref -> CASO", _ref),
    ("Ref -> ACTOR_CORTO", _ref),
    ("EtiqOpt -> ':' Palabras", lambda v: " ".join(v[1])),
    ("EtiqOpt -> ", nothing),
    ("Palabras -> Palabra", single),
    ("Palabras -> Palabras Palabra", append),
    ("Palabra -> NOMBRE", lambda v: v[0].value),
    ("Palabra -> TEXTO", lambda v: text_of(v[0])),
    ("Palabra -> ESTEREOTIPO", lambda v: v[0].value),
]

# -- reglas semánticas ---------------------------------------------------------

SEMANTIC_RULES = [
    R("U00", ERROR, "El diagrama tiene al menos un actor y un caso de uso."),
    R("U01", ERROR, "Cada actor y cada caso de uso se declara una sola vez."),
    R("U02", ERROR, "Las relaciones solo usan elementos declarados."),
    R("U03", ERROR, "Dos actores no se asocian entre sí: solo pueden generalizarse."),
    R("U04", ERROR, "<<include>> y <<extend>> unen casos de uso, nunca actores."),
    R("U05", ERROR, "Dos casos de uso no se asocian directamente: se unen con <<include>> o <<extend>>."),
    R("U06", ERROR, "<<include>> y <<extend>> son dependencias: van con flecha punteada (..>)."),
    R("U07", ERROR, "La generalización une actor con actor o caso de uso con caso de uso."),
    R("U08", AVISO, "Entre casos de uso, los estereotipos conocidos son <<include>> y <<extend>>."),
    R("U09", ERROR, "Las inclusiones y extensiones no forman ciclos."),
    R("U10", ERROR, "La generalización no forma ciclos."),
    R("U11", ERROR, "Los actores están fuera del límite del sistema."),
    R("U12", AVISO, "Todo caso de uso se alcanza desde algún actor."),
    R("U13", AVISO, "Todo actor participa de algún caso de uso."),
    R("U14", AVISO, "El nombre de un caso de uso empieza con un verbo en infinitivo."),
    R("U15", ERROR, "Una dependencia entre casos de uso indica su dirección (..> o <..)."),
    R("U16", ERROR, "La realización (..|>) no existe en casos de uso."),
    R("U17", AVISO, "Una misma relación no se repite."),
    R("U18", AVISO, "Si el diagrama usa @startuml, también cierra con @enduml (y al revés)."),
]

_INFINITIVE = re.compile(r"^[^\W\d_]+(?:ar|er|ir|ár|ér|ír)(?:se|lo|la|los|las|le|les)?$", re.I)


def _kind_of_link(arrow: str) -> str:
    if "|>" in arrow or "<|" in arrow:
        return "realizacion" if ".." in arrow else "generalizacion"
    return "dependencia" if ".." in arrow else "asociacion"


def check(model: UseCaseModel):
    c = Checker(SEMANTIC_RULES)
    check_markers(c, model.markers, "U18")

    by_id: dict[str, Element] = {}
    by_label: dict[tuple[str, str], Element] = {}
    for e in model.elements:
        key = e.alias or e.label
        if key in by_id:
            c.report("U01", f"«{key}» ya estaba declarado en la línea {by_id[key].at.line}.", e.at)
            continue
        by_id[key] = e
        by_label.setdefault((e.kind, e.label.lower()), e)
        if e.kind == "actor" and e.boundary:
            c.report("U11", f"El actor «{e.label}» está dentro de «{e.boundary}».", e.at)

    def resolve(ref: Ref) -> Element | None:
        if ref.form == "nombre":
            e = by_id.get(ref.text)
            if e is None:
                e = by_label.get(("actor", ref.text.lower())) or by_label.get(("caso", ref.text.lower()))
            if e is None:
                c.report("U02", f"«{ref.text}» no está declarado. Debe declararse con actor o usecase.", ref.at)
            return e
        kind = "caso" if ref.form == "caso" else "actor"
        e = by_label.get((kind, ref.text.lower()))
        if e is None:   # en PlantUML, (Texto) y :Texto: declaran al usarse
            e = Element(kind, ref.text, None, None, None, ref.at, implicit=True)
            by_label[(kind, ref.text.lower())] = e
            by_id.setdefault(ref.text, e)
            model.elements.append(e)
        return e

    assoc: dict[int, set[int]] = {}         # actor -> casos (por id de objeto)
    deps: dict[int, list[int]] = {}         # caso -> casos (include / extend)
    gens: dict[int, list[int]] = {}         # hijo -> padres
    seen_links: set[tuple] = set()

    for ln in model.links:
        a, b = resolve(ln.left), resolve(ln.right)
        if a is None or b is None:
            continue
        kind = _kind_of_link(ln.arrow)
        label = (ln.label or "").strip()
        stereo = label.lower().strip("<>").strip() if label.startswith("<<") else None

        key = (id(a), id(b), kind, stereo)
        if key in seen_links:
            c.report("U17", f"La relación entre «{a.label}» y «{b.label}» se repite.", ln.at)
        seen_links.add(key)

        if kind == "realizacion":
            c.report("U16", "La realización (..|>) no se usa en casos de uso. Para una "
                            "generalización corresponde --|>.", ln.at)
            continue
        if kind == "generalizacion":
            if a.kind != b.kind:
                c.report("U07", f"«{a.label}» y «{b.label}» son de distinta clase: no hay generalización "
                                "entre un actor y un caso de uso.", ln.at)
                continue
            child, parent = (b, a) if ln.arrow.startswith("<|") else (a, b)
            gens.setdefault(id(child), []).append(id(parent))
            continue

        if stereo in ("include", "extend"):
            if a.kind == "actor" or b.kind == "actor":
                c.report("U04", f"<<{stereo}>> une casos de uso; «{(a if a.kind == 'actor' else b).label}» "
                                "es un actor.", ln.at)
                continue
            if kind == "asociacion":
                c.report("U06", f"<<{stereo}>> va con flecha punteada: «..>» en lugar de «{ln.arrow}».", ln.at)
            elif ln.arrow == "..":
                c.report("U15", f"La relación <<{stereo}>> entre «{a.label}» y «{b.label}» no tiene "
                                "dirección.", ln.at)
            if ln.arrow in ("..", "--"):
                continue
            src, dst = (b, a) if ln.arrow.startswith("<") else (a, b)
            deps.setdefault(id(src), []).append(id(dst))
            continue

        if a.kind == "actor" and b.kind == "actor":
            c.report("U03", f"«{a.label}» y «{b.label}» son actores: no se asocian entre sí.", ln.at)
            continue
        if a.kind == "caso" and b.kind == "caso":
            if kind == "dependencia" and stereo is None:
                c.report("U05", f"La dependencia entre «{a.label}» y «{b.label}» necesita <<include>> "
                                "o <<extend>>.", ln.at)
            elif kind == "dependencia":
                c.report("U08", f"<<{stereo}>> no es un estereotipo de casos de uso.", ln.at)
            else:
                c.report("U05", f"«{a.label}» y «{b.label}» son casos de uso: no se asocian directamente. "
                                "Corresponde ..> con <<include>> o <<extend>>.", ln.at)
            continue
        actor, case = (a, b) if a.kind == "actor" else (b, a)
        assoc.setdefault(id(actor), set()).add(id(case))

    elements = {id(e): e for e in model.elements}
    _check_cycles(c, deps, elements, "U09", "inclusiones y extensiones")
    _check_cycles(c, gens, elements, "U10", "generalizaciones")

    actors = [e for e in model.elements if e.kind == "actor"]
    cases = [e for e in model.elements if e.kind == "caso"]
    if not actors or not cases:
        at = model.elements[0].at if model.elements else Loc(1, 1, 2)
        falta = "actores" if not actors else "casos de uso"
        if not model.elements:
            falta = "actores ni casos de uso"
        c.report("U00", f"El diagrama no tiene {falta}.", at)
        return c.diagnostics

    # Un caso es alcanzable si un actor (o su padre) lo usa, o si lo incluye/extiende
    # o especializa un caso alcanzable.
    reach: set[int] = set()
    for actor in actors:
        lineage = [id(actor)] + _ancestors(id(actor), gens)
        for x in lineage:
            reach |= assoc.get(x, set())
    changed = True
    while changed:
        changed = False
        for src, dsts in deps.items():
            for dst in dsts:
                for x, y in ((src, dst), (dst, src)):
                    if x in reach and y not in reach:
                        reach.add(y)
                        changed = True
        for child, ps in gens.items():
            if child in elements and elements[child].kind == "caso":
                for p in ps:
                    if p in reach and child not in reach:
                        reach.add(child)
                        changed = True
    for case in cases:
        if id(case) not in reach:
            c.report("U12", f"Ningún actor alcanza «{case.label}».", case.at)

    for actor in actors:
        lineage = [id(actor)] + _ancestors(id(actor), gens) + _descendants(id(actor), gens)
        if not any(assoc.get(x) for x in lineage):
            c.report("U13", f"El actor «{actor.label}» no participa de ningún caso de uso.", actor.at)

    for case in cases:
        verb = case.label.split()[0] if case.label.split() else ""
        if verb and not _INFINITIVE.match(verb):
            c.report("U14", f"«{case.label}» no empieza con un verbo en infinitivo (por ejemplo, "
                            "«Registrar…», «Consultar…»).", case.at)
    return c.diagnostics


def _ancestors(node: int, gens: dict[int, list[int]]) -> list[int]:
    out, stack, seen = [], list(gens.get(node, [])), {node}
    while stack:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
        stack.extend(gens.get(p, []))
    return out


def _descendants(node: int, gens: dict[int, list[int]]) -> list[int]:
    return [child for child, ps in gens.items() if node in ps]


def _check_cycles(c: Checker, edges: dict[int, list[int]], elements: dict[int, Element],
                  code: str, what: str) -> None:
    color: dict[int, int] = {}
    reported: set[frozenset] = set()

    def visit(n: int, path: list[int]) -> None:
        color[n] = 1
        path.append(n)
        for m in edges.get(n, []):
            if color.get(m) == 1:
                cycle = path[path.index(m):]
                key = frozenset(cycle)
                if key not in reported:
                    reported.add(key)
                    chain = " → ".join(elements[x].label for x in cycle + [m])
                    c.report(code, f"Ciclo de {what}: {chain}.", elements[n].at)
            elif color.get(m, 0) == 0:
                visit(m, path)
        path.pop()
        color[n] = 2

    for n in list(edges):
        if color.get(n, 0) == 0:
            visit(n, [])


# -- resumen ---------------------------------------------------------------------

def describe(model: UseCaseModel) -> dict:
    actors, cases = [], []
    for e in model.elements:
        detail = []
        if e.alias and e.alias != e.label:
            detail.append(f"Alias {e.alias}.")
        if e.boundary:
            detail.append(f"Dentro de «{e.boundary}».")
        if e.implicit:
            detail.append("Declarado al usarlo.")
        row = [e.label, " ".join(detail) or "Declarado.", e.at.line]
        (actors if e.kind == "actor" else cases).append(row)
    links = []
    for ln in model.links:
        kind = _kind_of_link(ln.arrow)
        names = {"asociacion": "Asociación", "dependencia": "Dependencia",
                 "generalizacion": "Generalización", "realizacion": "Realización"}
        text = names[kind] + (f" {ln.label}" if ln.label else "") + "."
        links.append([f"{ln.left.text} {ln.arrow} {ln.right.text}", text, ln.at.line])
    sections = [{"title": "Actores", "rows": actors}, {"title": "Casos de uso", "rows": cases}]
    if links:
        sections.append({"title": "Relaciones", "rows": links})
    return {"sections": sections}


HELP = """
' Actores y casos de uso
actor Cliente
actor "Empleado de caja" as Cajero
usecase "Realizar compra" as UC1
(Pagar con tarjeta) as UC2

' Límite del sistema (los actores van afuera)
rectangle "Sistema de ventas" {
  usecase "Emitir factura" as UC3
}

' Relaciones
Cliente --> UC1
UC1 ..> UC2 : <<include>>
UC3 ..> UC1 : <<extend>>
Cajero --|> Cliente
"""

KIND = DiagramKind(
    id="casos",
    name="Casos de uso",
    notation="PlantUML",
    extensions=(".puml",),
    summary="Actores, casos de uso, límites del sistema, include y extend.",
    lexer=_lexer(),
    rules=RULES,
    semantic_rules=SEMANTIC_RULES,
    check=check,
    describe_model=describe,
    help=HELP,
)
