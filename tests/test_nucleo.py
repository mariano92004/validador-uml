"""Pruebas del núcleo formal con gramáticas de libro."""

import unittest

from validador_uml.core import Grammar, GrammarError, Lexer, ParseTable, Parser


def _expr_lexer() -> Lexer:
    lx = Lexer()
    lx.ignore(r"[ \t]+")
    lx.token("NL", r"\n")
    lx.token("ID", r"[a-z]+", "un identificador")
    lx.literals("=", "*", "+", "(", ")")
    return lx


class LALRTests(unittest.TestCase):
    def test_gramatica_lalr_que_no_es_slr(self):
        # Ejemplo 4.48 del libro del dragón: S → L = R | R, L → * R | id, R → L.
        # Con SLR(1) tiene un conflicto desplazamiento/reducción con «=»; con LALR(1) no.
        lx = _expr_lexer()
        g = Grammar([
            ("S -> L '=' R", None),
            ("S -> R", None),
            ("L -> '*' R", None),
            ("L -> ID", None),
            ("R -> L", None),
        ], lx.types)
        table = ParseTable(g)
        self.assertEqual(table.conflicts, [])
        self.assertEqual(table.size, 10)   # mismos estados que LR(0)

        parser = Parser(table, lx.describe)
        for text, ok in (("a = * b", True), ("* * a", True), ("a = = b", False)):
            tokens, _, _ = lx.tokenize(text)
            tokens = [t for t in tokens if t.type != "NL"]
            self.assertEqual(parser.parse(tokens).accepted, ok, text)

    def test_detecta_ambiguedad(self):
        lx = _expr_lexer()
        g = Grammar([("E -> E '+' E", None), ("E -> ID", None)], lx.types)
        table = ParseTable(g)
        self.assertTrue(table.conflicts)
        self.assertEqual(table.conflicts[0].kind, "desplazamiento/reducción")

    def test_acciones_semanticas_y_traza(self):
        lx = _expr_lexer()
        g = Grammar([
            ("E -> E '+' T", lambda v: v[0] + v[2]),
            ("E -> T", lambda v: v[0]),
            ("T -> '(' E ')'", lambda v: v[1]),
            ("T -> ID", lambda v: len(v[0].value)),
        ], lx.types)
        parser = Parser(ParseTable(g), lx.describe)
        tokens, _, _ = lx.tokenize("ab + (abc + d)")
        tokens = [t for t in tokens if t.type != "NL"]
        res = parser.parse(tokens)
        self.assertTrue(res.accepted)
        self.assertEqual(res.value, 6)
        kinds = [s[0] for s in res.steps]
        self.assertEqual(kinds[-1], "a")
        self.assertEqual(kinds.count("d"), len(tokens) - 1)
        self.assertEqual(res.shifts, len(tokens) - 1)

    def test_simbolo_desconocido(self):
        with self.assertRaises(GrammarError):
            Grammar([("S -> Nada", None)], ["ID"])
        with self.assertRaises(GrammarError):
            Grammar([("S -> FALTA", None)], ["ID"])

    def test_no_terminal_improductivo(self):
        with self.assertRaises(GrammarError):
            Grammar([("S -> A", None), ("A -> A ID", None)], ["ID"])


class LexerTests(unittest.TestCase):
    def test_posiciones_y_errores(self):
        lx = _expr_lexer()
        tokens, diags, _ = lx.tokenize("a = b\n\n  c $ d\n")
        types = [t.type for t in tokens]
        self.assertEqual(types, ["ID", "=", "ID", "NL", "NL", "ID", "ID", "NL", "$"])
        c = tokens[5]
        self.assertEqual((c.line, c.col, c.end_col), (3, 3, 4))
        self.assertEqual(len(diags), 1)
        self.assertEqual((diags[0].line, diags[0].col, diags[0].code), (3, 5, "L01"))

    def test_agrega_fin_de_linea_final(self):
        lx = _expr_lexer()
        tokens, _, _ = lx.tokenize("\n\na")
        self.assertEqual([t.type for t in tokens], ["ID", "NL", "$"])


if __name__ == "__main__":
    unittest.main()
