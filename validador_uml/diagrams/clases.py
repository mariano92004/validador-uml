"""Diagrama de clases, con sintaxis basada en PlantUML."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core import Lexer
from .base import (AVISO, ERROR, UML_ARROW, Checker, DiagramKind, Loc, Marker,
                   SemanticRule as R, append, check_markers, empty, first, loc,
                   normalize_arrow, nothing, plantuml_base, quoted_text, second,
                   single, text_of)

# -- modelo --------------------------------------------------------------------


@dataclass
class TypeRef:
    text: str
    names: list[tuple[str, Loc]]


@dataclass
class Member:
    kind: str                  # "atributo" o "metodo"
    name: str
    type: TypeRef | None
    params: list[tuple[str | None, TypeRef | None]]
    visibility: str | None
    static: bool
    abstract: bool
    at: Loc


@dataclass
class ClassDecl:
    name: str
    kind: str                  # "clase", "abstracta", "interfaz" o "enum"
    stereotype: str | None
    members: list[Member]
    literals: list[tuple[str, Loc]]
    at: Loc


@dataclass
class Relation:
    left: str
    right: str
    left_at: Loc
    right_at: Loc
    arrow: str                 # normalizada: <|--, ..|>, *--, -->, ...
    mult_left: tuple[str, Loc] | None
    mult_right: tuple[str, Loc] | None
    label: str | None
    at: Loc


@dataclass
class ClassModel:
    classes: list[ClassDecl] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)


# -- léxico --------------------------------------------------------------------

def _lexer() -> Lexer:
    lx = Lexer(" Los comentarios empiezan con '.")
    plantuml_base(lx)
    lx.token("ESTEREOTIPO", r"<<[^<>\n]+>>", "un estereotipo, como <<entity>>")
    lx.token("FLECHA", UML_ARROW, "una flecha (<|--, ..|>, *--, o--, -->, ..>)")
    lx.token("MOD", r"\{[ \t]*(?:static|abstract|classifier)[ \t]*\}",
             "un modificador ({static} o {abstract})")
    quoted_text(lx)
    lx.token("NOMBRE", r"[^\W\d]\w*", "un nombre", keywords=True)
    for kw in ("class", "abstract", "interface", "enum"):
        lx.keyword(kw)
    lx.literals("{", "}", "(", ")", ":", ",", "<", ">", "[", "]")
    lx.token("VIS", r"[+\-#~]", "una visibilidad (+, -, # o ~)")
    return lx


# -- gramática y acciones ------------------------------------------------------

def _doc(v):
    model = ClassModel()
    for s in v[0]:
        if isinstance(s, ClassDecl):
            model.classes.append(s)
        elif isinstance(s, Relation):
            model.relations.append(s)
        elif isinstance(s, Marker):
            model.markers.append(s)
    return model


def _header(kind, name_at, stereo_at):
    def build(v):
        stereo = v[stereo_at]
        return (kind, v[name_at], stereo.value[2:-2].strip() if stereo else None)
    return build


def _class(v):
    kind, name, stereo = v[0]
    return ClassDecl(name.value, kind, stereo, v[1] or [], [], loc(name))


def _enum(v):
    stereo = v[2].value[2:-2].strip() if v[2] else None
    return ClassDecl(v[1].value, "enum", stereo, [], v[3] or [], loc(v[1]))


def _mods(v):
    word = v[1].value.strip("{} \t")
    return v[0] + ["static" if word == "classifier" else word]


def _member(kind, name_at, type_at, params_at=None):
    def build(v):
        vis, mods = v[0]
        name = v[name_at]
        params = v[params_at] if params_at is not None else []
        return Member(kind, name.value, v[type_at] if type_at is not None else None,
                      params or [], vis, "static" in mods, "abstract" in mods, loc(name))
    return build


def _type_simple(v):
    return TypeRef(v[0].value, [(v[0].value, loc(v[0]))])


def _type_array(v):
    return TypeRef(v[0].value + "[]", [(v[0].value, loc(v[0]))])


def _type_generic(v):
    inner = v[2]
    names = [(v[0].value, loc(v[0]))]
    for t in inner:
        names.extend(t.names)
    return TypeRef(f"{v[0].value}<{', '.join(t.text for t in inner)}>", names)


def _relation(v):
    left, mult_l, arrow, mult_r, right, label = v
    return Relation(left.value, right.value, loc(left), loc(right),
                    normalize_arrow(arrow.value), mult_l, mult_r, label, loc(arrow))


def _mult(v):
    return (text_of(v[0]), loc(v[0]))


RULES = [
    ("Doc -> Lineas", _doc),
    ("Lineas -> Lineas Linea", append),
    ("Lineas -> ", empty),
    ("Linea -> Sent NL", first),
    ("Linea -> NL", nothing),
    ("Linea -> error NL", nothing),
    ("Sent -> Clase", first),
    ("Sent -> Enum", first),
    ("Sent -> Relacion", first),
    ("Sent -> MARCA", lambda v: Marker(v[0].value, loc(v[0]))),
    ("Sent -> DIRECTIVA", nothing),

    ("Clase -> Cabecera CuerpoOpt", _class),
    ("Cabecera -> 'class' NOMBRE EsteOpt", _header("clase", 1, 2)),
    ("Cabecera -> 'abstract' 'class' NOMBRE EsteOpt", _header("abstracta", 2, 3)),
    ("Cabecera -> 'abstract' NOMBRE EsteOpt", _header("abstracta", 1, 2)),
    ("Cabecera -> 'interface' NOMBRE EsteOpt", _header("interfaz", 1, 2)),
    ("EsteOpt -> ESTEREOTIPO", first),
    ("EsteOpt -> ", nothing),
    ("CuerpoOpt -> '{' Miembros '}'", second),
    ("CuerpoOpt -> ", nothing),
    ("Miembros -> Miembros LineaMiembro", append),
    ("Miembros -> ", empty),
    ("LineaMiembro -> Miembro NL", first),
    ("LineaMiembro -> NL", nothing),
    ("LineaMiembro -> error NL", nothing),

    ("Miembro -> Prefijo NOMBRE TipoOpt", _member("atributo", 1, 2)),
    ("Miembro -> Prefijo NOMBRE '(' ParamsOpt ')' TipoOpt", _member("metodo", 1, 5, 3)),
    ("Miembro -> Prefijo Tipo NOMBRE", _member("atributo", 2, 1)),
    ("Miembro -> Prefijo Tipo NOMBRE '(' ParamsOpt ')'", _member("metodo", 2, 1, 4)),
    ("Prefijo -> VisOpt Mods", lambda v: (v[0], v[1])),
    ("VisOpt -> VIS", lambda v: v[0].value),
    ("VisOpt -> ", nothing),
    ("Mods -> Mods MOD", _mods),
    ("Mods -> ", empty),
    ("TipoOpt -> ':' Tipo", second),
    ("TipoOpt -> ", nothing),
    ("Tipo -> NOMBRE", _type_simple),
    ("Tipo -> NOMBRE '[' ']'", _type_array),
    ("Tipo -> NOMBRE '<' Tipos '>'", _type_generic),
    ("Tipos -> Tipo", single),
    ("Tipos -> Tipos ',' Tipo", lambda v: v[0] + [v[2]]),
    ("ParamsOpt -> Params", first),
    ("ParamsOpt -> ", empty),
    ("Params -> Param", single),
    ("Params -> Params ',' Param", lambda v: v[0] + [v[2]]),
    ("Param -> NOMBRE TipoOpt", lambda v: (v[0].value, v[1])),
    ("Param -> Tipo NOMBRE", lambda v: (v[1].value, v[0])),

    ("Enum -> 'enum' NOMBRE EsteOpt CuerpoEnumOpt", _enum),
    ("CuerpoEnumOpt -> '{' Literales '}'", second),
    ("CuerpoEnumOpt -> ", nothing),
    ("Literales -> Literales LineaLiteral", lambda v: v[0] + (v[1] or [])),
    ("Literales -> ", empty),
    ("LineaLiteral -> ListaNombres NL", first),
    ("LineaLiteral -> NL", nothing),
    ("LineaLiteral -> error NL", nothing),
    ("ListaNombres -> NOMBRE", lambda v: [(v[0].value, loc(v[0]))]),
    ("ListaNombres -> ListaNombres ',' NOMBRE", lambda v: v[0] + [(v[2].value, loc(v[2]))]),

    ("Relacion -> NOMBRE MultOpt FLECHA MultOpt NOMBRE EtiqOpt", _relation),
    ("MultOpt -> TEXTO", _mult),
    ("MultOpt -> ", nothing),
    ("EtiqOpt -> ':' Palabras", lambda v: " ".join(v[1])),
    ("EtiqOpt -> ", nothing),
    ("Palabras -> Palabra", single),
    ("Palabras -> Palabras Palabra", append),
    ("Palabra -> NOMBRE", lambda v: v[0].value),
    ("Palabra -> TEXTO", lambda v: text_of(v[0])),
    ("Palabra -> '<'", lambda v: "<"),
    ("Palabra -> '>'", lambda v: ">"),
]

# -- reglas semánticas ---------------------------------------------------------

SEMANTIC_RULES = [
    R("C00", ERROR, "El diagrama tiene que declarar al menos una clase."),
    R("C01", ERROR, "Cada clase, interfaz o enum se declara una sola vez."),
    R("C02", ERROR, "Las relaciones solo pueden unir clases declaradas."),
    R("C03", ERROR, "La herencia no puede formar ciclos."),
    R("C04", ERROR, "La generalización une clase con clase o interfaz con interfaz; los enum no heredan."),
    R("C05", ERROR, "La realización (..|>) va de una clase a una interfaz."),
    R("C06", ERROR, "Las multiplicidades tienen la forma n, n..m o n..* con n ≤ m."),
    R("C07", ERROR, "En una composición, el todo tiene multiplicidad 1 o 0..1: una parte no pertenece a varios todos."),
    R("C08", ERROR, "No se repiten atributos ni métodos con la misma firma dentro de una clase."),
    R("C09", AVISO, "Los tipos de atributos y parámetros son primitivos o clases del diagrama."),
    R("C10", ERROR, "Un método abstracto solo puede estar en una clase abstracta o una interfaz."),
    R("C11", AVISO, "Una interfaz no debería tener atributos de instancia."),
    R("C12", AVISO, "Una clase concreta implementa los métodos de sus interfaces y los abstractos que hereda."),
    R("C13", AVISO, "Un enum declara al menos un literal."),
    R("C14", AVISO, "Una clase sin relaciones ni referencias suele indicar que falta algo."),
    R("C15", AVISO, "La herencia múltiple entre clases es válida en UML pero conviene revisarla."),
    R("C16", ERROR, "Los literales de un enum no se repiten."),
    R("C17", AVISO, "Los nombres de clases empiezan con mayúscula."),
    R("C18", AVISO, "Una dependencia (..) tiene dirección: ..> o <.."),
    R("C19", ERROR, "La generalización y la realización no llevan multiplicidades."),
    R("C20", AVISO, "Los métodos de una interfaz son públicos."),
    R("C21", AVISO, "Si el diagrama usa @startuml, también cierra con @enduml (y al revés)."),
]

PRIMITIVES = {
    "int", "integer", "long", "short", "byte", "float", "double", "decimal", "number",
    "real", "bool", "boolean", "char", "character", "string", "str", "void", "date",
    "datetime", "time", "localdate", "localdatetime", "object", "any", "list", "set",
    "map", "dict", "array", "collection", "optional", "uuid", "bigdecimal",
    "biginteger", "texto", "entero", "fecha", "booleano", "caracter", "carácter",
    "cadena", "hora", "moneda", "lista", "coleccion", "colección", "arreglo", "vector",
}

_MULT = re.compile(r"^\s*(\*|\d+|[nN])\s*(?:\.\.\s*(\*|\d+|[nN])\s*)?$")
INF = float("inf")


def parse_mult(text: str) -> tuple[float, float] | str:
    """(mínimo, máximo) o un texto que explica el problema."""
    m = _MULT.match(text)
    if not m:
        return f"«{text}» no es una multiplicidad válida. Formas admitidas: 1, 0..1, 1..* o 0..*."
    a, b = m.groups()
    val = lambda s: INF if s in ("*", "n", "N") else int(s)
    if b is None:
        return (0, INF) if val(a) == INF else (val(a), val(a))
    lo, hi = val(a), val(b)
    if lo == INF:
        return f"En «{text}» el mínimo no puede ser *."
    if lo > hi:
        return f"En «{text}» el mínimo es mayor que el máximo."
    if hi == 0:
        return f"«{text}» no permite ninguna instancia."
    return (lo, hi)


def _fmt_mult(text: str) -> str:
    return text.replace(" ", "")


def classify(r: Relation) -> tuple[str, str, str]:
    """(tipo, a, b): para herencia a=hija y b=madre; para todo-parte a=todo y b=parte."""
    a, l, rt = r.arrow, r.left, r.right
    table = {
        "<|--": ("generalizacion", rt, l), "--|>": ("generalizacion", l, rt),
        "<|..": ("realizacion", rt, l), "..|>": ("realizacion", l, rt),
        "*--": ("composicion", l, rt), "--*": ("composicion", rt, l),
        "o--": ("agregacion", l, rt), "--o": ("agregacion", rt, l),
        "-->": ("asociacion", l, rt), "<--": ("asociacion", rt, l), "--": ("asociacion", l, rt),
        "..>": ("dependencia", l, rt), "<..": ("dependencia", rt, l), "..": ("dependencia", l, rt),
    }
    return table.get(a, ("asociacion", l, rt))


def check(model: ClassModel):
    c = Checker(SEMANTIC_RULES)
    check_markers(c, model.markers, "C21")
    if not model.classes:
        at = model.relations[0].at if model.relations else Loc(1, 1, 2)
        c.report("C00", "El diagrama no declara ninguna clase.", at)
        return c.diagnostics

    classes: dict[str, ClassDecl] = {}
    for cl in model.classes:
        if cl.name in classes:
            c.report("C01", f"«{cl.name}» ya estaba declarada en la línea {classes[cl.name].at.line}.", cl.at)
        else:
            classes[cl.name] = cl

    referenced: set[str] = set()
    for cl in classes.values():
        if cl.name[:1].islower():
            c.report("C17", f"«{cl.name}» empieza con minúscula.", cl.at)
        _check_members(c, cl, classes, referenced)

    parents: dict[str, list[str]] = {n: [] for n in classes}
    realizes: dict[str, list[str]] = {n: [] for n in classes}
    related: set[str] = set()

    for r in model.relations:
        kind, a, b = classify(r)
        for mult in (r.mult_left, r.mult_right):
            if mult:
                res = parse_mult(mult[0])
                if isinstance(res, str):
                    c.report("C06", res, mult[1])
        if kind in ("generalizacion", "realizacion") and (r.mult_left or r.mult_right):
            what = "La generalización" if kind == "generalizacion" else "La realización"
            c.report("C19", f"{what} entre «{r.left}» y «{r.right}» no lleva multiplicidades.", r.at)

        missing = False
        for name, at in ((r.left, r.left_at), (r.right, r.right_at)):
            if name not in classes:
                c.report("C02", f"«{name}» no está declarada. Debe declararse con class, interface o enum.", at)
                missing = True
        related.update((r.left, r.right))
        if missing:
            continue

        ca, cb = classes[a], classes[b]
        if kind == "generalizacion":
            if "enum" in (ca.kind, cb.kind):
                c.report("C04", f"«{a}» y «{b}»: un enum no participa de la herencia.", r.at)
            elif ca.kind == "interfaz" and cb.kind != "interfaz":
                c.report("C04", f"La interfaz «{a}» no puede heredar de la clase «{b}».", r.at)
            elif ca.kind != "interfaz" and cb.kind == "interfaz":
                c.report("C04", f"«{a}» no hereda de la interfaz «{b}»: la realiza. "
                                f"Corresponde «{a} ..|> {b}».", r.at)
            else:
                parents[a].append(b)
        elif kind == "realizacion":
            if cb.kind != "interfaz":
                c.report("C05", f"«{b}» no es una interfaz, así que «{a}» no puede realizarla.", r.at)
            elif ca.kind == "interfaz":
                c.report("C05", f"Una interfaz no realiza otra: «{a}» extiende a «{b}» con <|--.", r.at)
            else:
                realizes[a].append(b)
        elif kind == "composicion":
            whole_mult = r.mult_left if r.arrow == "*--" else r.mult_right
            if whole_mult:
                res = parse_mult(whole_mult[0])
                if not isinstance(res, str) and res[1] > 1:
                    c.report("C07", f"«{a}» es el todo de la composición: su multiplicidad debe ser 1 "
                                    f"o 0..1, no {_fmt_mult(whole_mult[0])}.", whole_mult[1])
        elif kind == "dependencia" and r.arrow == "..":
            c.report("C18", f"La dependencia entre «{r.left}» y «{r.right}» no indica hacia dónde va.", r.at)

    _check_cycles(c, classes, parents)

    for name, ps in parents.items():
        concrete = [p for p in ps if classes[p].kind != "interfaz"]
        if len(concrete) > 1:
            c.report("C15", f"«{name}» hereda de {', '.join(concrete)}.", classes[name].at)

    _check_implementations(c, classes, parents, realizes)

    if len(classes) > 1:
        for cl in classes.values():
            if cl.name not in related and cl.name not in referenced:
                c.report("C14", f"«{cl.name}» no se relaciona con ninguna otra clase.", cl.at)
    return c.diagnostics


def _check_members(c: Checker, cl: ClassDecl, classes: dict[str, ClassDecl], referenced: set[str]) -> None:
    if cl.kind == "enum":
        if not cl.literals:
            c.report("C13", f"El enum «{cl.name}» no tiene literales.", cl.at)
        seen: dict[str, Loc] = {}
        for lit, at in cl.literals:
            if lit in seen:
                c.report("C16", f"El literal «{lit}» se repite en «{cl.name}».", at)
            seen[lit] = at
        return

    attrs: dict[str, Member] = {}
    methods: dict[tuple, Member] = {}
    for mb in cl.members:
        types = [mb.type] + [t for _, t in mb.params]
        for t in types:
            if t is None:
                continue
            for tname, at in t.names:
                if tname in classes:
                    if tname != cl.name:
                        referenced.add(tname)
                        referenced.add(cl.name)
                elif tname.lower() not in PRIMITIVES and not re.fullmatch(r"[A-Z]", tname):
                    c.report("C09", f"El tipo «{tname}» no es primitivo ni una clase del diagrama.", at)

        if mb.kind == "atributo":
            if mb.name in attrs:
                c.report("C08", f"El atributo «{mb.name}» se repite en «{cl.name}».", mb.at)
            attrs[mb.name] = mb
            if cl.kind == "interfaz" and not mb.static:
                c.report("C11", f"La interfaz «{cl.name}» declara el atributo «{mb.name}».", mb.at)
        else:
            sig = (mb.name, tuple(t.text if t else f"?{i}" for i, (_, t) in enumerate(mb.params)))
            if sig in methods:
                c.report("C08", f"El método «{mb.name}» ya existe en «{cl.name}» con los mismos parámetros.", mb.at)
            methods[sig] = mb
            if mb.abstract and cl.kind not in ("abstracta", "interfaz"):
                c.report("C10", f"«{mb.name}» es abstracto pero «{cl.name}» no es una clase abstracta.", mb.at)
            if cl.kind == "interfaz" and mb.visibility in ("-", "#"):
                c.report("C20", f"«{mb.name}» es {'privado' if mb.visibility == '-' else 'protegido'} "
                                f"en la interfaz «{cl.name}».", mb.at)


def _check_cycles(c: Checker, classes: dict[str, ClassDecl], parents: dict[str, list[str]]) -> None:
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in classes}
    reported: set[frozenset] = set()

    def visit(n: str, path: list[str]) -> None:
        color[n] = GREY
        path.append(n)
        for p in parents[n]:
            if color[p] == GREY:
                cycle = path[path.index(p):]
                key = frozenset(cycle)
                if key not in reported:
                    reported.add(key)
                    chain = " → ".join(cycle + [p])
                    c.report("C03", f"Ciclo de herencia: {chain}.", classes[n].at)
            elif color[p] == WHITE:
                visit(p, path)
        path.pop()
        color[n] = BLACK

    for n in classes:
        if color[n] == WHITE:
            visit(n, [])


def _check_implementations(c: Checker, classes, parents, realizes) -> None:
    def ancestors(name: str) -> list[str]:
        out, stack, seen = [], list(parents[name]), {name}
        while stack:
            p = stack.pop()
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
            stack.extend(parents[p])
        return out

    for cl in classes.values():
        if cl.kind != "clase":
            continue
        lineage = [cl.name] + ancestors(cl.name)
        available = {m.name for n in lineage for m in classes[n].members
                     if m.kind == "metodo" and not m.abstract}
        required: dict[str, str] = {}
        for n in lineage[1:]:
            for m in classes[n].members:
                if m.kind == "metodo" and m.abstract:
                    required.setdefault(m.name, n)
        ifaces = []
        for n in lineage:
            for i in realizes[n]:
                ifaces.append(i)
                ifaces.extend(ancestors(i))
        for i in ifaces:
            for m in classes[i].members:
                if m.kind == "metodo" and not m.static:
                    required.setdefault(m.name, i)
        missing = [f"{name}() de {origin}" for name, origin in required.items() if name not in available]
        if missing:
            c.report("C12", f"«{cl.name}» no implementa {', '.join(missing)}.", cl.at)


# -- resumen del modelo ----------------------------------------------------------

_KIND_NAME = {"clase": "Clase", "abstracta": "Clase abstracta", "interfaz": "Interfaz", "enum": "Enum"}


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def describe(model: ClassModel) -> dict:
    rows = []
    for cl in model.classes:
        if cl.kind == "enum":
            detail = f"Enum con {_plural(len(cl.literals), 'literal', 'literales')}."
        else:
            attrs = sum(1 for m in cl.members if m.kind == "atributo")
            meths = len(cl.members) - attrs
            detail = (f"{_KIND_NAME[cl.kind]} con {_plural(attrs, 'atributo', 'atributos')} "
                      f"y {_plural(meths, 'método', 'métodos')}.")
        if cl.stereotype:
            detail += f" Estereotipo «{cl.stereotype}»."
        rows.append([cl.name, detail, cl.at.line])

    rels = []
    for r in model.relations:
        kind, a, b = classify(r)
        if kind == "generalizacion":
            text = f"{a} hereda de {b}."
        elif kind == "realizacion":
            text = f"{a} realiza la interfaz {b}."
        elif kind in ("composicion", "agregacion"):
            verb = "se compone de" if kind == "composicion" else "agrega"
            text = f"{a} {verb} {b}."
        elif kind == "dependencia":
            text = f"{a} depende de {b}."
        else:
            text = f"Asociación entre {r.left} y {r.right}."
        if r.mult_left or r.mult_right:
            ml = _fmt_mult(r.mult_left[0]) if r.mult_left else "sin indicar"
            mr = _fmt_mult(r.mult_right[0]) if r.mult_right else "sin indicar"
            text += f" Multiplicidad {ml} a {mr}."
        if r.label:
            text += f" «{r.label}»."
        rels.append([f"{r.left} {r.arrow} {r.right}", text, r.at.line])

    sections = [{"title": "Clases", "rows": rows}]
    if rels:
        sections.append({"title": "Relaciones", "rows": rels})
    return {"sections": sections}


HELP = """
' Clases, interfaces y enums
class Libro {
  - isbn : String
  + prestar(socio : Socio) : Prestamo
}
abstract class Persona
interface Prestable
enum Estado {
  DISPONIBLE, PRESTADO
}

' Relaciones: <|-- herencia, ..|> realización,
' *-- composición, o-- agregación, --> asociación, ..> dependencia
Persona <|-- Socio
Libro ..|> Prestable
Socio "1" -- "0..*" Prestamo : realiza
"""

KIND = DiagramKind(
    id="clases",
    name="Clases",
    notation="PlantUML",
    extensions=(".puml",),
    summary="Clases, interfaces y enums con sus miembros y relaciones.",
    lexer=_lexer(),
    rules=RULES,
    semantic_rules=SEMANTIC_RULES,
    check=check,
    describe_model=describe,
    help=HELP,
)
