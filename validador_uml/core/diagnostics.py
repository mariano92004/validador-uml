"""Diagnósticos: lo que el validador le dice a quien escribe el diagrama."""

from __future__ import annotations

from dataclasses import dataclass

ERROR = "error"
AVISO = "aviso"

LEXICO = "lexico"
SINTAXIS = "sintaxis"
SEMANTICA = "semantica"


@dataclass
class Diagnostic:
    severity: str          # "error" o "aviso"
    phase: str             # "lexico", "sintaxis" o "semantica"
    code: str              # L01, S01, C02, ...
    message: str
    line: int
    col: int = 1
    end_col: int | None = None   # columna final (exclusiva), si se conoce

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "phase": self.phase,
            "code": self.code,
            "message": self.message,
            "line": self.line,
            "col": self.col,
            "end": self.end_col if self.end_col is not None else self.col + 1,
        }

    def format(self, origin: str = "") -> str:
        where = f"{origin}:" if origin else ""
        return f"{where}{self.line}:{self.col}: {self.severity} {self.code}: {self.message}"
