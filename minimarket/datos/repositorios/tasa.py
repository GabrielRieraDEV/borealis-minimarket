"""Repositorio de tasas de cambio (RF-09, RF-13).

La tasa se guarda x1.000.000 (seis decimales).
"""

import sqlite3

from minimarket.dominio.dinero import ESCALA_TASA, a_entero, desde_entero
from minimarket.dominio.tasa import TasaCambio

_CAMPOS = "id, fecha, valor, origen, usuario_id, registrado_en"


def _entidad(fila: sqlite3.Row) -> TasaCambio:
    return TasaCambio(
        id=fila["id"],
        fecha=fila["fecha"],
        valor=desde_entero(fila["valor"], ESCALA_TASA),
        origen=fila["origen"],
        usuario_id=fila["usuario_id"],
        registrado_en=fila["registrado_en"],
    )


def registrar(conexion: sqlite3.Connection, tasa: TasaCambio) -> None:
    """RN-02. Una sola tasa por fecha: la segunda reemplaza a la primera.

    Las operaciones ya registradas apuntan a `tasa_cambio.id`, que el UPSERT
    conserva, de modo que ninguna se recalcula sola.
    """
    conexion.execute(
        """INSERT INTO tasa_cambio (fecha, valor, origen, usuario_id)
                VALUES (?, ?, ?, ?)
           ON CONFLICT(fecha) DO UPDATE SET
                valor = excluded.valor,
                origen = excluded.origen,
                usuario_id = excluded.usuario_id,
                registrado_en = datetime('now','localtime')""",
        (tasa.fecha, a_entero(tasa.valor, ESCALA_TASA), tasa.origen, tasa.usuario_id),
    )


def obtener(conexion: sqlite3.Connection, fecha: str) -> TasaCambio | None:
    fila = conexion.execute(
        f"SELECT {_CAMPOS} FROM tasa_cambio WHERE fecha = ?", (fecha,)
    ).fetchone()
    return _entidad(fila) if fila else None


def historico(
    conexion: sqlite3.Connection, desde: str | None = None, hasta: str | None = None
) -> list[TasaCambio]:
    """RF-13. El historico completo, o el tramo pedido."""
    sql = f"SELECT {_CAMPOS} FROM tasa_cambio WHERE 1 = 1"
    parametros: list[str] = []
    if desde:
        sql += " AND fecha >= ?"
        parametros.append(desde)
    if hasta:
        sql += " AND fecha <= ?"
        parametros.append(hasta)
    sql += " ORDER BY fecha DESC"
    return [_entidad(f) for f in conexion.execute(sql, parametros)]
