"""Apertura de la base SQLite y control de transacciones."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ESQUEMA = Path(__file__).with_name("esquema.sql")


def abrir(ruta: str | Path) -> sqlite3.Connection:
    """Abre la base, la deja en modo WAL y crea el esquema si falta.

    WAL sostiene la interrupcion abrupta del equipo sin corromper la base
    (RNF-07). `foreign_keys` es por conexion: SQLite lo trae apagado por
    compatibilidad y sin el las claves foraneas del esquema son decorativas.

    `isolation_level=None` desactiva las transacciones implicitas de sqlite3
    para que el unico lugar donde empieza y termina una transaccion sea
    `transaccion()`.
    """
    conexion = sqlite3.connect(str(ruta), isolation_level=None)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA journal_mode=WAL")
    conexion.execute("PRAGMA foreign_keys=ON")
    conexion.executescript(ESQUEMA.read_text(encoding="utf-8"))
    return conexion


@contextmanager
def transaccion(conexion: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Ejecuta el bloque dentro de una transaccion unica (RNF-06).

    Si algo falla no queda nada a medias: un corte durante una venta no puede
    dejar inventario descontado sin venta registrada.
    """
    conexion.execute("BEGIN IMMEDIATE")
    try:
        yield conexion
    except BaseException:
        conexion.execute("ROLLBACK")
        raise
    conexion.execute("COMMIT")
