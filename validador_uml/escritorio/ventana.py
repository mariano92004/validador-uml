"""Ventana nativa del validador.

Usa pywebview: una ventana del sistema (WebView2 en Windows) que muestra la
interfaz y llama a Python directamente, sin navegador ni servidor visibles.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .puente import Puente


def carpeta_interfaz() -> Path:
    base = getattr(sys, "_MEIPASS", None)   # dentro del ejecutable de PyInstaller
    if base:
        return Path(base) / "validador_uml" / "escritorio" / "interfaz"
    return Path(__file__).resolve().parent / "interfaz"


def main(archivo: str | None = None) -> int:
    try:
        import webview
    except ImportError:
        print("Falta pywebview. Se instala con: pip install pywebview", file=sys.stderr)
        return 1

    if archivo is None and len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        archivo = sys.argv[1]   # el ejecutable recibe el archivo al abrirlo con doble clic

    puente = Puente(abrir_al_iniciar=archivo)
    ventana = webview.create_window(
        "Validador UML",
        url=str(carpeta_interfaz() / "index.html"),
        js_api=puente,
        width=1280,
        height=880,
        min_size=(860, 600),
        background_color="#EEF2F5",
        text_select=True,
    )
    puente._ventana = ventana
    webview.start(http_server=True, private_mode=True,
                  debug=bool(os.environ.get("VALIDADOR_UML_DEPURAR")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
