"""Dibuja el ícono de la aplicación (la misma matriz de puntos del favicon).

Genera un .ico con imágenes PNG de varios tamaños, sin dependencias: los
píxeles se calculan con supermuestreo y se codifican a mano.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

PAPEL = (0xEE, 0xF2, 0xF5)
TINTA = (0x13, 0x23, 0x3A)
COBALTO = (0x2A, 0x5B, 0xA6)
CELESTE = (0x8D, 0xB4, 0xDE)

# (columna, fila, color) en una grilla de 3 x 3, como favicon.svg
PUNTOS = [(0, 0, TINTA), (1, 0, TINTA), (2, 0, TINTA),
          (0, 1, TINTA), (1, 1, COBALTO), (2, 1, CELESTE),
          (0, 2, TINTA), (1, 2, TINTA), (2, 2, TINTA)]


def _pixeles(n: int) -> bytes:
    centros = [((c + 1) * n / 4, (f + 1) * n / 4, color) for c, f, color in PUNTOS]
    radio = n * 0.105
    muestras = [(i + 0.5) / 4 for i in range(4)]
    filas = []
    for y in range(n):
        fila = bytearray(b"\x00")          # filtro PNG «ninguno»
        for x in range(n):
            r, g, b = PAPEL
            for cx, cy, color in centros:
                if abs(x + 0.5 - cx) > radio + 1 or abs(y + 0.5 - cy) > radio + 1:
                    continue
                dentro = sum((x + sx - cx) ** 2 + (y + sy - cy) ** 2 <= radio * radio
                             for sx in muestras for sy in muestras) / 16
                if dentro:
                    r = round(r + (color[0] - r) * dentro)
                    g = round(g + (color[1] - g) * dentro)
                    b = round(b + (color[2] - b) * dentro)
            fila += bytes((r, g, b, 255))
        filas.append(bytes(fila))
    return b"".join(filas)


def _png(n: int) -> bytes:
    def bloque(tipo: bytes, datos: bytes) -> bytes:
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos))
    cabecera = struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + bloque(b"IHDR", cabecera)
            + bloque(b"IDAT", zlib.compress(_pixeles(n), 9)) + bloque(b"IEND", b""))


def escribir_ico(destino: Path, tamanos: tuple[int, ...] = (16, 32, 48, 64, 256)) -> Path:
    imagenes = [_png(n) for n in tamanos]
    salida = struct.pack("<HHH", 0, 1, len(imagenes))
    desplazamiento = 6 + 16 * len(imagenes)
    for n, datos in zip(tamanos, imagenes):
        lado = 0 if n >= 256 else n
        salida += struct.pack("<BBBBHHII", lado, lado, 0, 0, 1, 32, len(datos), desplazamiento)
        desplazamiento += len(datos)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(salida + b"".join(imagenes))
    return destino


if __name__ == "__main__":
    print(escribir_ico(Path("build/ValidadorUML.ico")))
