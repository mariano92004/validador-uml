"""Modelo conceptual de datos (MCD): entidades, relaciones y cardinalidades.

No hay una notación textual estándar, así que uso una propia en castellano.
Las cardinalidades siguen la convención (mín,máx) de Merise: el par que
acompaña a una entidad dice en cuántas ocurrencias de la relación participa
cada ejemplar de esa entidad.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core import Lexer
from .base import (AVISO, ERROR, Checker, DiagramKind, Loc, SemanticRule as R,
                   append, empty, first, loc, nothing, second)

# -- modelo --------------------------------------------------------------------


@dataclass
class Attribute:
    name: str
    is_id: bool
    domain: str | None
    at: Loc


@dataclass
class Entity:
    name: str
    weak: bool
    attributes: list[Attribute]
    at: Loc


@dataclass
class Leg:
    entity: str
    card: str
    low: int | None
    high: float | None
    role: str | None
    at: Loc
    card_at: Loc


@dataclass
class Relationship:
    name: str
    legs: list[Leg]
    attributes: list[Attribute]
    at: Loc


@dataclass
class DataModel:
    entities: list[Entity] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)


INF = float("inf")

# -- léxico --------------------------------------------------------------------


def _lexer() -> Lexer:
    lx = Lexer(" Los comentarios empiezan con //.")
    lx.ignore(r"[ \t]+")
    lx.comment(r"//[^\n]*")
    lx.token("NL", r"\n")
    lx.token("CARDINALIDAD", r"\([ \t]*\d+[ \t]*,[ \t]*(?:\d+|[nNmM*])[ \t]*\)",
             "una cardinalidad como (0,n) o (1,1)")
    lx.error(r"\([^)\n]*\)?", "Cardinalidad mal escrita. Formato: (mín,máx), por ejemplo (0,n) o (1,1).")
    lx.token("NOMBRE", r"[^\W\d]\w*", "un nombre", keywords=True)
    lx.keyword("entidad")
    lx.keyword("relacion")
    lx.keyword("relación", "relacion")
    lx.keyword("debil")
    lx.keyword("débil", "debil")
    lx.keyword("como")
    lx.literals("{", "}", ":", "#")
    return lx


# -- gramática y acciones ------------------------------------------------------

_CARD = re.compile(r"\(\s*(\d+)\s*,\s*(\d+|[nNmM*])\s*\)")


def _leg(v):
    tok = v[1]
    m = _CARD.match(tok.value)
    low = int(m.group(1)) if m else None
    hi_s = m.group(2) if m else None
    high = INF if hi_s and not hi_s.isdigit() else (int(hi_s) if hi_s else None)
    card = tok.value.replace(" ", "").replace("\t", "")
    return Leg(v[0].value, card, low, high, v[2], loc(v[0]), loc(tok))


def _doc(v):
    model = DataModel()
    for s in v[0]:
        if isinstance(s, Entity):
            model.entities.append(s)
        elif isinstance(s, Relationship):
            model.relationships.append(s)
    return model


def _relationship(v):
    legs = [x for x in v[3] if isinstance(x, Leg)]
    attrs = [x for x in v[3] if isinstance(x, Attribute)]
    return Relationship(v[1].value, legs, attrs, loc(v[1]))


RULES = [
    ("Doc -> Lineas", _doc),
    ("Lineas -> Lineas Linea", append),
    ("Lineas -> ", empty),
    ("Linea -> Sent NL", first),
    ("Linea -> NL", nothing),
    ("Linea -> error NL", nothing),
    ("Sent -> Entidad", first),
    ("Sent -> Relacion", first),

    ("Entidad -> 'entidad' DebilOpt NOMBRE CuerpoOpt",
     lambda v: Entity(v[2].value, v[1], v[3] or [], loc(v[2]))),
    ("DebilOpt -> 'debil'", lambda v: True),
    ("DebilOpt -> ", lambda v: False),
    ("CuerpoOpt -> '{' Atributos '}'", second),
    ("CuerpoOpt -> ", nothing),
    ("Atributos -> Atributos LineaAtributo", append),
    ("Atributos -> ", empty),
    ("LineaAtributo -> Atributo NL", first),
    ("LineaAtributo -> NL", nothing),
    ("LineaAtributo -> error NL", nothing),
    ("Atributo -> '#' NOMBRE DominioOpt", lambda v: Attribute(v[1].value, True, v[2], loc(v[1]))),
    ("Atributo -> NOMBRE DominioOpt", lambda v: Attribute(v[0].value, False, v[1], loc(v[0]))),
    ("DominioOpt -> ':' NOMBRE", lambda v: v[1].value),
    ("DominioOpt -> ", nothing),

    ("Relacion -> 'relacion' NOMBRE '{' Patas '}'", _relationship),
    ("Patas -> Patas LineaPata", append),
    ("Patas -> ", empty),
    ("LineaPata -> Pata NL", first),
    ("LineaPata -> Atributo NL", first),
    ("LineaPata -> NL", nothing),
    ("LineaPata -> error NL", nothing),
    ("Pata -> NOMBRE CARDINALIDAD RolOpt", _leg),
    ("RolOpt -> 'como' NOMBRE", lambda v: v[1].value),
    ("RolOpt -> ", nothing),
]

# -- reglas semánticas ---------------------------------------------------------

SEMANTIC_RULES = [
    R("M00", ERROR, "El modelo tiene al menos una entidad."),
    R("M01", ERROR, "Entidades y relaciones comparten espacio de nombres: no se repiten."),
    R("M02", ERROR, "Toda entidad fuerte tiene un identificador (#)."),
    R("M03", ERROR, "Un atributo no se repite dentro de una entidad o relación."),
    R("M04", ERROR, "Las relaciones solo unen entidades declaradas."),
    R("M05", ERROR, "Una relación une al menos dos patas (la misma entidad dos veces si es reflexiva)."),
    R("M06", ERROR, "En una cardinalidad (mín,máx), mín ≤ máx y máx ≥ 1."),
    R("M07", AVISO, "Toda entidad participa de alguna relación."),
    R("M08", AVISO, "Una relación 1:N no lleva atributos: van en la entidad del lado (x,1)."),
    R("M09", AVISO, "En el modelo conceptual no hay claves foráneas: la relación ya expresa el vínculo."),
    R("M10", AVISO, "Una relación reflexiva nombra los roles de cada pata (… como jefe)."),
    R("M11", ERROR, "Los atributos de una relación no son identificadores."),
    R("M12", ERROR, "Una entidad débil depende de otra por una relación en la que participa con (1,1)."),
    R("M13", AVISO, "En una relación de tres o más patas, un máximo 1 suele indicar que se puede descomponer."),
    R("M14", AVISO, "Una relación con (1,1) en ambos lados suele indicar que las entidades son la misma."),
    R("M15", AVISO, "Un mínimo mayor que 1 es válido pero poco habitual."),
    R("M16", AVISO, "Una entidad tiene algún atributo además del identificador."),
]


def check(model: DataModel):
    c = Checker(SEMANTIC_RULES)
    if not model.entities:
        at = model.relationships[0].at if model.relationships else Loc(1, 1, 2)
        c.report("M00", "El modelo no declara ninguna entidad.", at)
        return c.diagnostics

    names: dict[str, Loc] = {}
    entities: dict[str, Entity] = {}
    for obj in [*model.entities, *model.relationships]:
        key = obj.name.lower()
        if key in names:
            c.report("M01", f"«{obj.name}» ya está declarado en la línea {names[key].line}.", obj.at)
            continue
        names[key] = obj.at
        if isinstance(obj, Entity):
            entities[obj.name.lower()] = obj

    id_names: dict[str, str] = {}
    for e in entities.values():
        ids = [a for a in e.attributes if a.is_id]
        _check_duplicates(c, e.attributes, e.name)
        if not ids and not e.weak:
            c.report("M02", f"«{e.name}» no tiene identificador: debe marcarse uno con #.", e.at)
        if e.attributes and all(a.is_id for a in e.attributes) and not e.weak:
            c.report("M16", f"«{e.name}» solo tiene su identificador.", e.at)
        if len(ids) == 1:
            id_names[ids[0].name.lower()] = e.name

    for e in entities.values():
        base = e.name.lower()
        for a in e.attributes:
            if a.is_id:
                continue
            low = a.name.lower()
            owner = id_names.get(low)
            if owner and owner != e.name:
                c.report("M09", f"«{a.name}» es el identificador de «{owner}»: en el MCD no se repite, "
                                "lo aporta la relación.", a.at)
                continue
            m = re.fullmatch(r"(?:id|cod|codigo|código|nro|num)_?(\w+)|(\w+?)_?(?:id|cod)", low)
            if m:
                target = (m.group(1) or m.group(2) or "").lower()
                if target and target != base and target in entities:
                    c.report("M09", f"«{a.name}» parece una clave foránea hacia «{entities[target].name}».",
                             a.at)

    participates: set[str] = set()
    identifying: set[str] = set()
    for r in model.relationships:
        _check_duplicates(c, r.attributes, r.name)
        for a in r.attributes:
            if a.is_id:
                c.report("M11", f"«{a.name}» es atributo de la relación «{r.name}»: no puede ser "
                                "identificador.", a.at)
        if len(r.legs) < 2:
            c.report("M05", f"La relación «{r.name}» tiene {len(r.legs)} pata"
                            f"{'s' if len(r.legs) != 1 else ''}: necesita al menos dos.", r.at)
        valid = []
        for leg in r.legs:
            ent = entities.get(leg.entity.lower())
            if ent is None:
                c.report("M04", f"«{leg.entity}» no es una entidad declarada.", leg.at)
            else:
                participates.add(ent.name)
            if leg.low is None or leg.high is None:
                continue
            if leg.high == 0:
                c.report("M06", f"En {leg.card} el máximo es 0: la entidad nunca participaría.", leg.card_at)
            elif leg.low > leg.high:
                c.report("M06", f"En {leg.card} el mínimo es mayor que el máximo.", leg.card_at)
            else:
                if leg.low > 1:
                    c.report("M15", f"{leg.card}: cada «{leg.entity}» participa al menos {leg.low} veces.",
                             leg.card_at)
                valid.append(leg)
                if ent is not None and leg.low == 1 and leg.high == 1:
                    identifying.add(ent.name)

        if len(r.legs) == 2 and r.legs[0].entity.lower() == r.legs[1].entity.lower():
            if not all(leg.role for leg in r.legs):
                c.report("M10", f"«{r.name}» es reflexiva sobre «{r.legs[0].entity}»: deben nombrarse los roles.",
                         r.at)
        if len(valid) == 2 and len(r.legs) == 2:
            highs = [leg.high for leg in valid]
            if r.attributes and sorted(h == 1 for h in highs) == [False, True]:
                one = next(leg for leg in valid if leg.high == 1)
                c.report("M08", f"«{r.name}» es 1:N: sus atributos van en «{one.entity}».",
                         r.attributes[0].at)
            if all(leg.low == 1 and leg.high == 1 for leg in valid):
                c.report("M14", f"«{r.name}» es (1,1) en ambos lados: es posible que "
                                f"«{valid[0].entity}» y «{valid[1].entity}» sean la misma entidad.", r.at)
        if len(r.legs) >= 3:
            for leg in valid:
                if leg.high == 1:
                    c.report("M13", f"En «{r.name}», «{leg.entity}» tiene máximo 1.", leg.card_at)

    for e in entities.values():
        if e.weak and e.name not in identifying:
            c.report("M12", f"La entidad débil «{e.name}» no participa con (1,1) en ninguna relación.", e.at)
        if e.name not in participates and len(entities) > 1:
            c.report("M07", f"«{e.name}» no participa de ninguna relación.", e.at)
    return c.diagnostics


def _check_duplicates(c: Checker, attrs: list[Attribute], owner: str) -> None:
    seen: set[str] = set()
    for a in attrs:
        key = a.name.lower()
        if key in seen:
            c.report("M03", f"«{a.name}» se repite en «{owner}».", a.at)
        seen.add(key)


# -- resumen ---------------------------------------------------------------------

def describe(model: DataModel) -> dict:
    ents = []
    for e in model.entities:
        ids = [a.name for a in e.attributes if a.is_id]
        rest = [a.name for a in e.attributes if not a.is_id]
        text = ("Entidad débil. " if e.weak else "") + \
               (f"Identificador: {', '.join(ids)}." if ids else "Sin identificador.")
        if rest:
            text += f" Atributos: {', '.join(rest)}."
        ents.append([e.name, text, e.at.line])
    rels = []
    for r in model.relationships:
        legs = ", ".join(f"{leg.entity} {leg.card}" + (f" como {leg.role}" if leg.role else "") for leg in r.legs)
        text = f"{legs}." if legs else "Sin patas."
        if r.attributes:
            text += f" Atributos: {', '.join(a.name for a in r.attributes)}."
        rels.append([r.name, text, r.at.line])
    sections = [{"title": "Entidades", "rows": ents}]
    if rels:
        sections.append({"title": "Relaciones", "rows": rels})
    return {"sections": sections}


HELP = """
// Entidades: # marca el identificador
entidad Cliente {
  #dni
  nombre
  email
}
entidad Pedido {
  #numero
  fecha : fecha
}

// Relaciones: cada pata lleva (mín,máx)
relacion Realiza {
  Cliente (0,n)
  Pedido (1,1)
}

// Entidad débil y relación reflexiva con roles
entidad debil Linea {
  numero
}
relacion Supervisa {
  Empleado (0,n) como jefe
  Empleado (0,1) como subordinado
}
"""

KIND = DiagramKind(
    id="mcd",
    name="MCD",
    notation="propia",
    extensions=(".mcd",),
    summary="Modelo conceptual de datos: entidades, relaciones y cardinalidades (mín,máx).",
    lexer=_lexer(),
    rules=RULES,
    semantic_rules=SEMANTIC_RULES,
    check=check,
    describe_model=describe,
    help=HELP,
)
