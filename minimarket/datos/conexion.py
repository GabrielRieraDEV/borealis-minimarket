"""Apertura de la base SQLite y control de transacciones."""

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from minimarket.dominio.fechas import a_iso

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
    _reparar_vencimientos(conexion)
    return conexion


def _reparar_vencimientos(conexion: sqlite3.Connection) -> None:
    """Pasa a ISO los vencimientos que se cargaron como «01-02-2027».

    Hasta 1.4.0 el campo «Vence» de la compra no validaba nada y lo tecleado
    entraba crudo. Una sola fecha asi tumbaba el arranque: la pantalla de
    Inicio calcula RN-17 sobre todos los lotes vivos. La entrada ya no lo
    permite; esto cura las bases que quedaron con el dato viejo.
    """
    for lote_id, fecha in conexion.execute(
        "SELECT id, fecha_vencimiento FROM lote"
    ).fetchall():
        try:
            date.fromisoformat(fecha)
            continue
        except ValueError:
            pass
        corregida = a_iso(fecha)
        if corregida is None:
            logging.warning("Lote %s con vencimiento ilegible: %r", lote_id, fecha)
            continue
        conexion.execute(
            "UPDATE lote SET fecha_vencimiento = ? WHERE id = ?", (corregida, lote_id)
        )
        logging.info("Lote %s: vencimiento %r corregido a %s", lote_id, fecha, corregida)


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
