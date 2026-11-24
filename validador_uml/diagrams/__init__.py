"""Registro de los tipos de diagrama."""

from __future__ import annotations

import re

from . import actividad, casos, clases, flujo, mcd
from .base import DiagramKind

KINDS: dict[str, DiagramKind] = {
    k.id: k for k in (clases.KIND, casos.KIND, actividad.KIND, flujo.KIND, mcd.KIND)
}


def get_kind(kind_id: str) -> DiagramKind:
    try:
        return KINDS[kind_id]
    except KeyError:
        valid = ", ".join(KINDS)
        raise ValueError(f"Tipo de diagrama desconocido: «{kind_id}». Tipos disponibles: {valid}.") from None


def detect_kind(text: str, filename: str | None = None) -> str | None:
    """Adivina el tipo de diagrama por la extensión o por el contenido."""
    if filename:
        low = filename.lower()
        if low.endswith((".mmd", ".mermaid")):
            return "flujo"
        if low.endswith(".mcd"):
            return "mcd"
    lines = [ln.strip() for ln in text.splitlines()
             if ln.strip() and not ln.strip().startswith(("'", "%%", "//"))]
    if lines and re.match(r"(flowchart|graph)\b", lines[0]):
        return "flujo"
    body = "\n".join(lines)
    if re.search(r"^(entidad|relaci[oó]n)\b", body, re.M):
        return "mcd"
    if re.search(r"^(start|stop|:[^;\n]*;|if\s*\(|fork\b|while\s*\(|repeat\b)", body, re.M):
        return "actividad"
    if re.search(r"^(actor|usecase)\b|^\([^)]+\)|^:[^:\s][^:]*:", body, re.M):
        return "casos"
    if re.search(r"^(abstract\s+|class\s|interface\s|enum\s)|<\|--|\.\.\|>", body, re.M):
        return "clases"
    return None


__all__ = ["KINDS", "DiagramKind", "detect_kind", "get_kind"]
