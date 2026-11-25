# Validador UML

Herramienta de validación de diagramas UML que trata cada diagrama como un
lenguaje formal. Cada tipo de diagrama tiene su propio léxico, su gramática libre
de contexto y sus reglas semánticas. Un analizador LALR(1), escrito a mano,
recorre el texto desplazando y reduciendo; después se aplican las reglas que una
gramática no puede expresar.

| Diagrama     | Notación                  | Extensión       | Reglas |
|--------------|---------------------------|-----------------|--------|
| Clases       | PlantUML                  | `.puml`         | 24     |
| Casos de uso | PlantUML                  | `.puml`         | 19     |
| Actividad    | PlantUML (sintaxis nueva) | `.puml`         | 15     |
| Flujo        | Mermaid `flowchart`       | `.mmd`          | 16     |
| MCD          | propia, en castellano     | `.mcd`          | 17     |

## Cómo se usa

Es una aplicación de escritorio: una ventana propia que funciona sin internet.

**Ejecutable para Windows.** `ValidadorUML.exe` se descarga desde la sección
Releases del repositorio y se abre con doble clic. No requiere Python. También
abre directamente un diagrama arrastrado sobre el ejecutable.

**Desde el código.** Requiere Python 3.10 o posterior y
[pywebview](https://pywebview.flowrl.com/):

```powershell
git clone https://github.com/mariano92004/validador-uml.git
cd validador-uml
python -m pip install pywebview
python -m validador_uml
```

La ventana permite abrir y guardar archivos `.puml`, `.mmd` y `.mcd` (Ctrl+O,
Ctrl+S, Ctrl+Mayús+S). El borrador de cada tipo de diagrama se guarda
automáticamente en la carpeta de datos del usuario
(`%APPDATA%\ValidadorUML` en Windows).

Desde la terminal, sin pywebview:

```powershell
python -m validador_uml revisar diagrama.puml           # adivina el tipo
python -m validador_uml revisar flujo.mmd --traza       # cada desplazamiento y reducción
python -m validador_uml revisar modelo.mcd --json       # todo el resultado en JSON
python -m validador_uml gramatica clases --tabla        # gramática y tabla ACTION/GOTO
python -m validador_uml ejemplo actividad --errores     # un ejemplo con errores
```

`revisar` devuelve 0 si no hay errores (los avisos no cuentan) y 1 si los hay,
así que sirve en un hook o en integración continua. `pip install -e .[app]`
instala los comandos `validador-uml` y `validador-uml-app`.

Una salida real:

```text
actividad_errores.puml:5:1: aviso A05: La decisión no tiene else: no está definido qué ocurre si ninguna condición se cumple.
actividad_errores.puml:11:1: error A10: La acción está vacía.
actividad_errores.puml:17:3: error A04: Instrucción inalcanzable: está después de un nodo final.
actividad_errores.puml:21:1: error A02: Ya hay un start en la línea 3.

Actividad (PlantUML). 51 tokens, 51 desplazamientos y 71 reducciones.
5 errores y 3 avisos.
```

## Cómo funciona

El análisis tiene tres fases, una por nivel de la jerarquía de Chomsky.

**Léxico (lenguaje regular).** Cada token es una expresión regular y se prueban
en orden: las flechas antes que los nombres, para que `o--` no se lea como el
nombre `o`. Algunos errores frecuentes tienen su propio patrón, como una acción
sin `;` o una cardinalidad `(0;n)`.

**Sintaxis (lenguaje libre de contexto).** Cada diagrama tiene su gramática,
escrita como texto en su módulo:

```text
r1        Doc → Cabecera NL Lineas
r4     Lineas → Lineas Linea
r5            | ε
r8      Linea → error NL
r13    Cadena → Nodo Enlace Nodo
r14           | Cadena Enlace Nodo
r19      Nodo → NOMBRE FORMA
```

Con ella se construye la tabla LALR(1) con el método del libro del dragón:
el autómata de ítems LR(0), las anticipaciones que se generan espontáneamente
y las que se propagan hasta un punto fijo. Las cinco gramáticas salen sin
conflictos y las pruebas lo verifican. Un autómata de pila recorre la tabla:

```text
Paso  Pila                              Entrada            Acción
   6  0 Cabecera 2 NL 5 Lineas 6        I ([Inicio]) -->   desplazar 15
   7  … Lineas 6 NOMBRE 15 FORMA 23     --> F ([Fin])      reducir r19: Nodo → NOMBRE FORMA
   8  … Lineas 6 Nodo 11                --> F ([Fin])      desplazar 20
```

Cuando algo no encaja, el analizador se recupera como yacc: busca en la pila un
estado que acepte el terminal `error`, descarta tokens hasta el fin de línea y
sigue. Por eso
un diagrama con cuatro errores de sintaxis muestra los cuatro a la vez. El mensaje
indica qué se esperaba, y antes de listarlo se simula cada candidato sobre la pila real,
porque la fusión de estados de LALR suma anticipaciones que en ese contexto no
sirven.

**Semántica (más allá de lo libre de contexto).** Mientras reduce, cada
producción ejecuta una acción que arma el modelo del diagrama. Después se recorre
ese modelo con las reglas que una gramática libre de contexto no puede expresar:
que una clase esté declarada antes de usarla (el libro del dragón lo reduce al
lenguaje {wcw}, que no es libre de contexto), que la herencia no tenga ciclos, que
todo nodo de un flujo se alcance desde el inicio y llegue a un fin, que una
entidad débil dependa de otra por una relación (1,1). La semántica solo corre si
el léxico y la sintaxis están bien; si no, sus mensajes confundirían. Si una fase
falla por un defecto del propio validador, se informa como el error I01 y nunca
como una excepción; una batería de textos mutados al azar en las pruebas busca
esos defectos.

Entre las reglas hay algunas de cátedra más que de la especificación UML, como
que un caso de uso empiece con un verbo en infinitivo. Esas son avisos, no errores.

## Estructura

```text
validador_uml/
  core/              léxico, gramáticas, tabla LALR(1) y analizador
  diagrams/          un módulo por diagrama: léxico, gramática, acciones y reglas
  ejemplos/          un ejemplo correcto y uno con errores por tipo
  escritorio/
    ventana.py       ventana nativa (pywebview)
    puente.py        lo que la interfaz le pide a Python: analizar, abrir, guardar
    interfaz/        HTML, CSS, JavaScript y fuentes
  api.py             lo que usan la CLI y la aplicación
  cli.py
empaquetado/         lanzador, ícono y script de PyInstaller
tests/
.github/workflows/   pruebas y ejecutable para Windows
```

Para generar el ejecutable localmente:

```powershell
python -m pip install pywebview pyinstaller
python empaquetado/construir.py
```

El resultado queda en `dist/ValidadorUML.exe`.

Para sumar un tipo de diagrama alcanza con un módulo nuevo en `diagrams/` que
defina su `Lexer`, sus reglas gramaticales con acciones, sus reglas semánticas y
un `DiagramKind`, y registrarlo en `diagrams/__init__.py`. La prueba de
conflictos lo cubre sola.

## Límites

- Se acepta un subconjunto de PlantUML y de Mermaid. Lo que queda fuera de ese
  subconjunto se informa como error de sintaxis en lugar de ignorarse.
- La herramienta no dibuja los diagramas: para eso están PlantUML y Mermaid.
- Algunas reglas responden a criterios de cátedra más que a la especificación UML;
  por eso son avisos y no errores.

## Licencia

MIT.
