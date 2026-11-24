"""Pruebas del puente de la aplicación de escritorio (sin abrir ventanas)."""

import json
import tempfile
import unittest
from pathlib import Path

from validador_uml.escritorio.puente import Puente
from validador_uml.escritorio.ventana import carpeta_interfaz


class PuenteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.puente = Puente(datos=self.dir / "datos")

    def tearDown(self):
        self.tmp.cleanup()

    def test_catalogo_y_analisis(self):
        catalogo = self.puente.catalogo()
        self.assertEqual(len(catalogo["kinds"]), 5)
        r = self.puente.analizar("mcd", catalogo["kinds"][4]["examples"]["correcto"])
        self.assertTrue(r["ok"])
        self.assertEqual(r["trace"], [])
        json.dumps(r)

    def test_borrador_persiste_entre_sesiones(self):
        self.puente.guardar_borrador("flujo", "flowchart TD\n")
        otro = Puente(datos=self.dir / "datos")
        estado = otro.estado()
        self.assertEqual(estado["tipo"], "flujo")
        self.assertEqual(estado["borradores"]["flujo"], "flowchart TD\n")

    def test_abrir_detecta_el_tipo(self):
        ruta = self.dir / "pedido.mmd"
        ruta.write_bytes("flowchart LR\r\nA([Inicio]) --> B([Fin])\r\n".encode("utf-8-sig"))
        r = self.puente._abrir_ruta(str(ruta))
        self.assertEqual(r["tipo"], "flujo")
        self.assertEqual(r["texto"], "flowchart LR\nA([Inicio]) --> B([Fin])\n")
        self.assertEqual(self.puente.estado()["archivos"]["flujo"]["nombre"], "pedido.mmd")

    def test_guardar_agrega_extension_y_recuerda_la_ruta(self):
        r = self.puente._guardar_en("clases", "class A\n", str(self.dir / "modelo"))
        self.assertEqual(r["nombre"], "modelo.puml")
        self.assertEqual((self.dir / "modelo.puml").read_text(encoding="utf-8"), "class A\n")
        r = self.puente.guardar("clases", "class B\n")   # ya tiene ruta: no abre diálogo
        self.assertEqual(r["nombre"], "modelo.puml")
        self.assertEqual((self.dir / "modelo.puml").read_text(encoding="utf-8"), "class B\n")

    def test_archivo_inexistente(self):
        r = self.puente._abrir_ruta(str(self.dir / "no-existe.puml"))
        self.assertIn("error", r)

    def test_archivo_pendiente_al_iniciar(self):
        ruta = self.dir / "uso.puml"
        ruta.write_text("actor A\nusecase \"Comprar\" as U\nA --> U\n", encoding="utf-8")
        puente = Puente(datos=self.dir / "datos", abrir_al_iniciar=str(ruta))
        estado = puente.estado()
        self.assertEqual(estado["abrir"]["tipo"], "casos")
        self.assertIsNone(puente.estado()["abrir"])

    def test_estado_corrupto_no_impide_abrir(self):
        (self.dir / "datos").mkdir()
        (self.dir / "datos" / "estado.json").write_text("{roto", encoding="utf-8")
        self.assertIn("tipo", Puente(datos=self.dir / "datos").estado())

    def test_interfaz_completa(self):
        base = carpeta_interfaz()
        for nombre in ("index.html", "estilos.css", "app.js", "campo.js", "veredicto.js",
                       "fuentes/Doto.ttf", "fuentes/HankenGrotesk.ttf", "fuentes/FragmentMono-Regular.ttf"):
            self.assertTrue((base / nombre).is_file(), nombre)
        html = (base / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("googleapis", html)


if __name__ == "__main__":
    unittest.main()
