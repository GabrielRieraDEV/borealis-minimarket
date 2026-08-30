"""Repositorio de la tabla `configuracion` (RF-64).

Pares clave/valor de texto. Quien lee sabe que tipo espera; no hay conversion
automatica salvo `leer_decimal`, que existe porque el multiplo de redondeo
comercial (RN-10) es dinero y no puede pasar por `float`.
"""

import sqlite3
from decimal import Decimal, InvalidOperation


def leer(conexion: sqlite3.Connection, clave: str, defecto: str = "") -> str:
    fila = conexion.execute(
        "SELECT valor FROM configuracion WHERE clave = ?", (clave,)
    ).fetchone()
    return fila[0] if fila and fila[0] != "" else defecto


def leer_decimal(
    conexion: sqlite3.Connection, clave: str, defecto: Decimal
) -> Decimal:
    try:
        return Decimal(leer(conexion, clave, str(defecto)))
    except InvalidOperation:
        # Un valor corrompido en configuracion no puede tumbar una pantalla.
        return defecto


def escribir(conexion: sqlite3.Connection, clave: str, valor: str) -> None:
    conexion.execute(
        """INSERT INTO configuracion (clave, valor) VALUES (?, ?)
           ON CONFLICT(clave) DO UPDATE SET
               valor = excluded.valor,
               actualizado_en = datetime('now','localtime')""",
        (clave, valor),
    )
