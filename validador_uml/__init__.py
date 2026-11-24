"""Validador de diagramas UML modelados como lenguajes formales.

Cada tipo de diagrama es un lenguaje con su propio léxico (expresiones
regulares), su gramática libre de contexto (analizada con LALR(1) y
desplazamiento-reducción) y sus reglas semánticas.
"""

__version__ = "0.1.0"
