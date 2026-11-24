"""Genera dist/ValidadorUML.exe (un solo archivo, sin consola).

    pip install pywebview pyinstaller
    python empaquetado/construir.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "empaquetado"))

from icono import escribir_ico  # noqa: E402


def main() -> int:
    try:
        import PyInstaller.__main__ as pyinstaller
    except ImportError:
        print("Falta PyInstaller. Se instala con: pip install pyinstaller", file=sys.stderr)
        return 1
    sep = os.pathsep
    build = RAIZ / "build"
    icono = escribir_ico(build / "ValidadorUML.ico")
    paquete = RAIZ / "validador_uml"
    pyinstaller.run([
        str(RAIZ / "empaquetado" / "lanzador.py"),
        "--name", "ValidadorUML",
        "--onefile",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--icon", str(icono),
        "--paths", str(RAIZ),
        "--add-data", f"{paquete / 'escritorio' / 'interfaz'}{sep}validador_uml/escritorio/interfaz",
        "--add-data", f"{paquete / 'ejemplos'}{sep}validador_uml/ejemplos",
        "--distpath", str(RAIZ / "dist"),
        "--workpath", str(build),
        "--specpath", str(build),
    ])
    print(f"Listo: {RAIZ / 'dist' / 'ValidadorUML.exe'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
