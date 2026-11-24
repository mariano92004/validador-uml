"""Puente entre la interfaz y Python.

Los métodos públicos de `Puente` son los que la ventana puede llamar desde
JavaScript (`window.pywebview.api.<método>`). Todo lo demás es privado.
El estado (tipo elegido, borradores y archivo asociado a cada tipo) se guarda
en un JSON en la carpeta de datos del usuario, así que nada depende del
almacenamiento del navegador.
"""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from pathlib import Path

from .. import api
from ..diagrams import KINDS, detect_kind

TIPOS_DE_ARCHIVO = (
    "Diagramas (*.puml;*.plantuml;*.mmd;*.mermaid;*.mcd;*.txt)",
    "Todos los archivos (*.*)",
)


def carpeta_de_datos() -> Path:
    propia = os.environ.get("VALIDADOR_UML_DATOS")
    if propia:
        return Path(propia)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "ValidadorUML"


def _leer(ruta: Path) -> str:
    datos = ruta.read_bytes()
    try:
        texto = datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = datos.decode("cp1252", errors="replace")
    return texto.replace("\r\n", "\n").replace("\r", "\n")


class Puente:
    def __init__(self, datos: Path | None = None, abrir_al_iniciar: str | None = None) -> None:
        self._datos = Path(datos) if datos else carpeta_de_datos()
        self._ventana = None
        self._pendiente = abrir_al_iniciar
        self._estado = self._leer_estado()

    # -- estado persistente --------------------------------------------------------

    @property
    def _archivo_estado(self) -> Path:
        return self._datos / "estado.json"

    def _leer_estado(self) -> dict:
        try:
            estado = json.loads(self._archivo_estado.read_text(encoding="utf-8"))
            if not isinstance(estado, dict):
                estado = {}
        except (OSError, ValueError):
            estado = {}
        estado.setdefault("tipo", next(iter(KINDS)))
        estado.setdefault("borradores", {})
        estado.setdefault("rutas", {})
        return estado

    def _escribir_estado(self) -> None:
        try:
            self._datos.mkdir(parents=True, exist_ok=True)
            tmp = self._archivo_estado.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._estado, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self._archivo_estado)
        except OSError:
            pass   # sin carpeta de datos la herramienta sigue funcionando, sin recordar nada

    # -- llamados desde la interfaz -------------------------------------------------

    def catalogo(self) -> dict:
        return api.catalog()

    def estado(self) -> dict:
        """Tipo elegido, borradores y el archivo asociado a cada tipo, con su contenido."""
        archivos = {}
        for tipo, ruta in list(self._estado["rutas"].items()):
            p = Path(ruta)
            try:
                archivos[tipo] = {"ruta": str(p), "nombre": p.name, "texto": _leer(p)}
            except OSError:
                del self._estado["rutas"][tipo]
        abrir = None
        if self._pendiente:
            abrir = self._abrir_ruta(self._pendiente)
            self._pendiente = None
        return {"tipo": self._estado["tipo"], "borradores": self._estado["borradores"],
                "archivos": archivos, "abrir": abrir}

    def analizar(self, tipo: str, texto: str) -> dict:
        return api.analyze(tipo, texto, trace=False, tree=False)

    def guardar_borrador(self, tipo: str, texto: str) -> bool:
        if tipo not in KINDS:
            return False
        self._estado["tipo"] = tipo
        self._estado["borradores"][tipo] = texto
        self._escribir_estado()
        return True

    def abrir(self) -> dict | None:
        rutas = self._dialogo("OPEN", file_types=TIPOS_DE_ARCHIVO)
        return self._abrir_ruta(rutas[0]) if rutas else None

    def guardar(self, tipo: str, texto: str) -> dict | None:
        ruta = self._estado["rutas"].get(tipo)
        if not ruta:
            return self.guardar_como(tipo, texto)
        return self._guardar_en(tipo, texto, ruta)

    def guardar_como(self, tipo: str, texto: str) -> dict | None:
        extension = KINDS[tipo].extensions[0] if tipo in KINDS else ".txt"
        actual = self._estado["rutas"].get(tipo)
        nombre = Path(actual).name if actual else f"diagrama_{tipo}{extension}"
        directorio = str(Path(actual).parent) if actual else ""
        rutas = self._dialogo("SAVE", save_filename=nombre, directory=directorio,
                              file_types=TIPOS_DE_ARCHIVO)
        return self._guardar_en(tipo, texto, rutas[0]) if rutas else None

    def titulo(self, texto: str) -> None:
        if self._ventana is not None:
            self._ventana.title = texto

    def abrir_enlace(self, url: str) -> None:
        if isinstance(url, str) and url.startswith(("https://", "http://")):
            webbrowser.open(url)

    # -- internos (también los usan las pruebas) ---------------------------------------------

    def _abrir_ruta(self, ruta: str) -> dict:
        p = Path(ruta)
        try:
            texto = _leer(p)
        except OSError as e:
            return {"error": f"No se pudo abrir {p.name}: {e.strerror or e}."}
        tipo = detect_kind(texto, p.name) or self._estado["tipo"]
        self._estado["tipo"] = tipo
        self._estado["rutas"][tipo] = str(p)
        self._estado["borradores"][tipo] = texto
        self._escribir_estado()
        return {"ruta": str(p), "nombre": p.name, "texto": texto, "tipo": tipo}

    def _guardar_en(self, tipo: str, texto: str, ruta: str) -> dict:
        p = Path(ruta)
        if not p.suffix and tipo in KINDS:
            p = p.with_suffix(KINDS[tipo].extensions[0])
        try:
            p.write_text(texto, encoding="utf-8", newline="\n")
        except OSError as e:
            return {"error": f"No se pudo guardar {p.name}: {e.strerror or e}."}
        self._estado["rutas"][tipo] = str(p)
        self._escribir_estado()
        return {"ruta": str(p), "nombre": p.name}

    def _dialogo(self, modo: str, **opciones) -> list[str] | None:
        if self._ventana is None:
            return None
        import webview
        resultado = self._ventana.create_file_dialog(getattr(webview.FileDialog, modo), **opciones)
        if not resultado:
            return None
        return [resultado] if isinstance(resultado, str) else list(resultado)
