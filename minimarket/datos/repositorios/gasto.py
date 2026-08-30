"""Repositorio de gastos operativos (RF-46).

`monto_usd` se guarda x100. `periodo` es el mes al que corresponde el gasto,
en formato AAAA-MM, y no tiene por que coincidir con `fecha`, que es cuando se
cargo o se pago.
"""

import sqlite3
from decimal import Decimal

from minimarket.dominio.dinero import ESCALA_TOTAL, a_entero, desde_entero
from minimarket.dominio.reportes import GastoOperativo

_CAMPOS = "id, categoria, descripcion, monto_usd, periodo, fecha, usuario_id"


def _entidad(fila: sqlite3.Row) -> GastoOperativo:
    return GastoOperativo(
        id=fila["id"],
        categoria=fila["categoria"],
        descripcion=fila["descripcion"],
        monto_usd=desde_entero(fila["monto_usd"], ESCALA_TOTAL),
        periodo=fila["periodo"],
        fecha=fila["fecha"],
        usuario_id=fila["usuario_id"],
    )


def crear(conexion: sqlite3.Connection, gasto: GastoOperativo) -> int:
    return conexion.execute(
        """INSERT INTO gasto_operativo (categoria, descripcion, monto_usd,
                                        periodo, fecha, usuario_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            gasto.categoria,
            gasto.descripcion,
            a_entero(gasto.monto_usd, ESCALA_TOTAL),
            gasto.periodo,
            gasto.fecha,
            gasto.usuario_id,
        ),
    ).lastrowid


def obtener(conexion: sqlite3.Connection, gasto_id: int) -> GastoOperativo | None:
    fila = conexion.execute(
        f"SELECT {_CAMPOS} FROM gasto_operativo WHERE id = ?", (gasto_id,)
    ).fetchone()
    return _entidad(fila) if fila else None


def listar(
    conexion: sqlite3.Connection,
    desde_periodo: str | None = None,
    hasta_periodo: str | None = None,
    limite: int = 500,
) -> list[GastoOperativo]:
    sql = f"SELECT {_CAMPOS} FROM gasto_operativo WHERE 1 = 1"
    parametros: list[object] = []
    if desde_periodo:
        sql += " AND periodo >= ?"
        parametros.append(desde_periodo)
    if hasta_periodo:
        sql += " AND periodo <= ?"
        parametros.append(hasta_periodo)
    sql += " ORDER BY periodo DESC, id DESC LIMIT ?"
    parametros.append(limite)
    return [_entidad(f) for f in conexion.execute(sql, parametros)]


def total_del_rango(
    conexion: sqlite3.Connection, desde_periodo: str, hasta_periodo: str
) -> Decimal:
    """RN-29. Los gastos de los meses que toca el periodo, sin prorratear."""
    fila = conexion.execute(
        """SELECT COALESCE(SUM(monto_usd), 0) FROM gasto_operativo
            WHERE periodo >= ? AND periodo <= ?""",
        (desde_periodo, hasta_periodo),
    ).fetchone()
    return desde_entero(fila[0], ESCALA_TOTAL)
