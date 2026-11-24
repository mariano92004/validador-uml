"""Pruebas de la línea de comandos y de la exportación del sitio."""

import contextlib
import io
import unittest
from pathlib import Path

from validador_uml.cli import main
from validador_uml.diagrams import KINDS

EJEMPLOS = Path(__file__).resolve().parent.parent / "validador_uml" / "ejemplos"


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = main(list(argv))
    return code, out.getvalue()


class CLITests(unittest.TestCase):
    def test_revisar_correcto_y_con_errores(self):
        for kind in KINDS.values():
            ok = EJEMPLOS / f"{kind.id}_correcto{kind.extensions[0]}"
            bad = EJEMPLOS / f"{kind.id}_errores{kind.extensions[0]}"
            self.assertEqual(run("revisar", str(ok))[0], 0, ok.name)
            code, out = run("revisar", str(bad))
            self.assertEqual(code, 1, bad.name)
            self.assertIn("error", out)

    def test_traza(self):
        code, out = run("revisar", str(EJEMPLOS / "flujo_correcto.mmd"), "--traza")
        self.assertEqual(code, 0)
        self.assertIn("desplazar", out)
        self.assertIn("reducir r", out)
        self.assertIn("aceptar", out)

    def test_gramatica(self):
        code, out = run("gramatica", "mcd", "--tabla", "--estados")
        self.assertEqual(code, 0)
        self.assertIn("Sin conflictos.", out)
        self.assertIn("Estado 0", out)

    def test_archivo_inexistente(self):
        self.assertEqual(run("revisar", "no-existe.puml")[0], 2)

    def test_abrir_archivo_inexistente(self):
        self.assertEqual(run("abrir", "no-existe.puml")[0], 2)


if __name__ == "__main__":
    unittest.main()
