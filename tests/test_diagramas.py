"""Pruebas de los cinco tipos de diagrama."""

import json
import random
import unittest

from validador_uml import api
from validador_uml.diagrams import KINDS, detect_kind


def codes(kind: str, text: str) -> list[str]:
    return [d["code"] for d in api.analyze(kind, text, trace=False, tree=False)["diagnostics"]]


EXPECTED_ERRORS = {
    "clases": {"C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09", "C10", "C11"},
    "casos": {"U02", "U03", "U04", "U05", "U06", "U07", "U09", "U11", "U12", "U13", "U14"},
    "actividad": {"A02", "A03", "A04", "A05", "A06", "A07", "A09", "A10"},
    "flujo": {"F03", "F07", "F08", "F09", "F10", "F11"},
    "mcd": {"M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08", "M09", "M10", "M12"},
}


class TodosLosTipos(unittest.TestCase):
    def test_gramaticas_sin_conflictos(self):
        for kind in KINDS.values():
            with self.subTest(kind=kind.id):
                self.assertEqual(kind.table.conflicts, [])

    def test_ejemplo_correcto_sin_diagnosticos(self):
        for kind in KINDS.values():
            with self.subTest(kind=kind.id):
                r = api.analyze(kind.id, kind.example("correcto"))
                self.assertEqual(r["diagnostics"], [])
                self.assertTrue(r["ok"])
                self.assertTrue(r["phases"]["semantica"]["ran"])

    def test_ejemplo_con_errores(self):
        for kind in KINDS.values():
            with self.subTest(kind=kind.id):
                r = api.analyze(kind.id, kind.example("errores"))
                found = {d["code"] for d in r["diagnostics"]}
                self.assertFalse(r["ok"])
                self.assertTrue(EXPECTED_ERRORS[kind.id] <= found,
                                EXPECTED_ERRORS[kind.id] - found)

    def test_reglas_documentadas(self):
        for kind in KINDS.values():
            documented = {r.code for r in kind.semantic_rules}
            for variant in ("correcto", "errores"):
                for c in codes(kind.id, kind.example(variant)):
                    if c[0] not in "LS":
                        self.assertIn(c, documented)

    def test_texto_vacio(self):
        for kind in KINDS.values():
            with self.subTest(kind=kind.id):
                r = api.analyze(kind.id, "")
                self.assertFalse(r["ok"])

    def test_json_serializable(self):
        for kind in KINDS.values():
            json.dumps(api.analyze(kind.id, kind.example("errores")))
            json.dumps(api.grammar_info(kind.id))
        json.dumps(api.catalog())

    def test_deteccion_del_tipo(self):
        for kind in KINDS.values():
            for variant in ("correcto", "errores"):
                name = f"x{kind.extensions[0]}"
                self.assertEqual(detect_kind(kind.example(variant), name), kind.id)
                self.assertEqual(detect_kind(kind.example(variant)), kind.id)


class Sintaxis(unittest.TestCase):
    def test_varios_errores_en_una_pasada(self):
        text = "class A {\n  - x :\n  + f(a : int : void\n}\nclass\nA <|-- B sobra\n"
        r = api.analyze("clases", text)
        sintaxis = [d for d in r["diagnostics"] if d["phase"] == "sintaxis"]
        self.assertEqual([d["line"] for d in sintaxis], [2, 3, 5, 6])
        self.assertFalse(r["phases"]["semantica"]["ran"])

    def test_bloque_sin_cerrar(self):
        r = api.analyze("actividad", "start\nif (x) then (sí)\n  :a;\nstop\n")
        self.assertEqual(r["diagnostics"][0]["code"], "S01")
        self.assertIn("termina antes de lo esperado", r["diagnostics"][0]["message"])

    def test_accion_sin_punto_y_coma(self):
        r = api.analyze("actividad", "start\n:Leer datos\nstop\n")
        self.assertEqual(r["diagnostics"][0]["code"], "L03")
        self.assertEqual(r["diagnostics"][0]["line"], 2)

    def test_palabra_suelta_en_actividad(self):
        r = api.analyze("actividad", "start\nLeer\nstop\n")
        self.assertEqual(r["diagnostics"][0]["code"], "L02")

    def test_cardinalidad_mal_escrita(self):
        r = api.analyze("mcd", "entidad A {\n  #id\n}\nrelacion R {\n  A (0;n)\n  A (1,1)\n}\n")
        self.assertIn("L03", [d["code"] for d in r["diagnostics"]])

    def test_flujo_sin_cabecera(self):
        r = api.analyze("flujo", "A([Inicio]) --> B([Fin])\n")
        self.assertEqual(r["diagnostics"][0]["code"], "S01")
        self.assertEqual(r["diagnostics"][0]["line"], 1)

    def test_esperaba_sin_anticipaciones_espurias(self):
        r = api.analyze("clases", "class A {\n  + f(a : int : void\n}\n")
        msg = r["diagnostics"][0]["message"]
        self.assertNotIn("«>»", msg)


class Semantica(unittest.TestCase):
    def test_clases_realizacion_completa(self):
        text = ("interface I {\n  + f() : void\n}\nclass A {\n  + f() : void\n}\n"
                "class B\nA ..|> I\nB ..|> I\n")
        self.assertEqual(codes("clases", text), ["C12"])

    def test_clases_multiplicidades(self):
        text = 'class A\nclass B\nA "0..n" -- "1..3" B\nA "x" -- "*" B\n'
        self.assertEqual(codes("clases", text), ["C06"])

    def test_casos_por_texto(self):
        text = "actor :Cliente:\n:Cliente: --> (Comprar productos)\n"
        self.assertEqual(codes("casos", text), [])

    def test_actividad_if_que_termina(self):
        text = ("start\nif (x) then (sí)\n  stop\nelse (no)\n  end\nendif\n:Nunca;\n")
        self.assertEqual(codes("actividad", text), ["A04"])

    def test_flujo_decision_con_dos_salidas(self):
        text = ("flowchart LR\nI([Inicio]) --> D{¿x?}\nD -->|sí| F([Fin])\nD -- no --> F\n")
        self.assertEqual(codes("flujo", text), [])

    def test_mcd_entidad_debil(self):
        text = ("entidad Factura {\n  #numero\n  fecha\n}\nentidad debil Linea {\n  #renglon\n  monto\n}\n"
                "relacion Tiene {\n  Factura (1,n)\n  Linea (1,1)\n}\n")
        self.assertEqual(codes("mcd", text), [])


class PlantUMLReal(unittest.TestCase):
    """Construcciones frecuentes en diagramas de clases hechos con PlantUML."""

    BASE = ("skinparam class {\n  BackgroundColor #FFFFFF\n  BorderColor #3A4A5A\n}\n"
            "hide circle\n"
            "legend top left\n<color:#C9DBF2>██</color> 1. Grupo\nendlegend\n"
            "class Socio #C9DBF2 {\n  - nombre: String\n  # dni: String\n  #edad: int\n  # add(x: int): void\n}\n"
            "class Curso #LightBlue {\n  - titulo: String\n}\n"
            "class Inscripcion #FFF\n")

    def test_estilos_colores_y_leyenda(self):
        text = self.BASE + 'Socio "0..*" -- "0..*" Curso : cursa >\n(Socio, Curso) .. Inscripcion\n'
        self.assertEqual(codes("clases", text), [])

    def test_clase_de_asociacion_sin_asociacion(self):
        text = self.BASE + "Socio --> Curso\n(Socio, Inscripcion) .. Curso\n"
        self.assertIn("C22", codes("clases", text))

    def test_clase_de_asociacion_con_linea_continua(self):
        text = self.BASE + "Socio -- Curso\n(Socio, Curso) -- Inscripcion\n"
        self.assertEqual(codes("clases", text), ["C23"])

    def test_clase_de_asociacion_no_declarada(self):
        text = self.BASE + "Socio -- Curso\n(Socio, Curso) .. Matricula\n"
        self.assertIn("C02", codes("clases", text))

    def test_tipo_desconocido_una_sola_vez(self):
        text = ("class A {\n  - x: Estado\n  - y: Estado\n  + f(e: Estado): void\n}\n"
                "class B\nA -- B\n")
        diags = api.analyze("clases", text)["diagnostics"]
        self.assertEqual([d["code"] for d in diags], ["C09"])
        self.assertIn("3 veces", diags[0]["message"])


class Robustez(unittest.TestCase):
    SNIPPETS = ["{", "}", "(", ")", ":", ";", "\n", '"', "-->", "<|--", "..|>", "*--", "class",
                "if", "endif", "fork", "end", "#", "(0,n)", "([x])", "{x}", "|a|", "actor",
                "<<include>>", "entidad", "relacion", "debil", "stop", "start", "else",
                "@startuml", "subgraph", "[x]", ":a;", "repeat while (x)", "switch (x)",
                "{static}", "+", "1..*", "2..1"]

    def test_textos_mutados_no_rompen_el_validador(self):
        rnd = random.Random(2026)
        bases = [k.example(v) for k in KINDS.values() for v in ("correcto", "errores")]
        for kind in KINDS.values():
            for _ in range(250):
                text = rnd.choice(bases)
                for _ in range(rnd.randint(1, 5)):
                    p = rnd.randint(0, len(text))
                    r = rnd.random()
                    if r < 0.4:
                        text = text[:p] + text[p + rnd.randint(1, 25):]
                    elif r < 0.85:
                        text = text[:p] + rnd.choice(self.SNIPPETS) + text[p:]
                    else:
                        lines = text.split("\n")
                        rnd.shuffle(lines)
                        text = "\n".join(lines)
                res = api.analyze(kind.id, text, trace=False, tree=False)
                self.assertNotIn("I01", {d["code"] for d in res["diagnostics"]}, text)

    def test_error_interno_se_informa_como_error(self):
        kind = KINDS["clases"]

        def falla(model):
            raise RuntimeError("defecto simulado")

        original = kind.check
        kind.check = falla
        try:
            r = api.analyze("clases", kind.example("correcto"))
        finally:
            kind.check = original
        self.assertFalse(r["ok"])
        self.assertEqual(r["errors"], 1)
        self.assertEqual(r["diagnostics"][0]["code"], "I01")
        self.assertEqual(r["phases"]["semantica"]["errors"], 1)


if __name__ == "__main__":
    unittest.main()
