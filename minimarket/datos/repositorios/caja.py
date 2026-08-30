"""Repositorio de sesiones de caja (RF-42 a RF-45, RN-26).

Los montos de la caja se guardan x100. La unicidad de la sesion abierta la
impone el indice `ux_caja_una_abierta` del esquema, no este modulo.
"""

import sqlite3
from decimal import Decimal

from minimarket.dominio.dinero import (
    ESCALA_TASA,
    ESCALA_TOTAL,
    a_entero,
    desde_entero,
)
from minimarket.dominio.venta import ABIERTA, ANULADA, CERRADA, CajaSesion

_CAMPOS = """id, usuario_apertura_id, fecha_apertura, inicial_bs, inicial_usd,
             fecha_cierre, usuario_cierre_id, conteo_bs, conteo_usd,
             diferencia_bs, diferencia_usd, estado"""


def _opcional(entero: int | None) -> Decimal | None:
    return None if entero is None else desde_entero(entero, ESCALA_TOTAL)


def _entidad(fila: sqlite3.Row) -> CajaSesion:
    return CajaSesion(
        id=fila["id"],
        usuario_apertura_id=fila["usuario_apertura_id"],
        fecha_apertura=fila["fecha_apertura"],
        inicial_bs=desde_entero(fila["inicial_bs"], ESCALA_TOTAL),
        inicial_usd=desde_entero(fila["inicial_usd"], ESCALA_TOTAL),
        fecha_cierre=fila["fecha_cierre"],
        usuario_cierre_id=fila["usuario_cierre_id"],
        conteo_bs=_opcional(fila["conteo_bs"]),
        conteo_usd=_opcional(fila["conteo_usd"]),
        diferencia_bs=_opcional(fila["diferencia_bs"]),
        diferencia_usd=_opcional(fila["diferencia_usd"]),
        estado=fila["estado"],
    )


def abrir(conexion: sqlite3.Connection, sesion: CajaSesion) -> int:
    """RF-42. Monto inicial en cada moneda."""
    return conexion.execute(
        """INSERT INTO caja_sesion (usuario_apertura_id, inicial_bs, inicial_usd)
           VALUES (?, ?, ?)""",
        (
            sesion.usuario_apertura_id,
            a_entero(sesion.inicial_bs, ESCALA_TOTAL),
            a_entero(sesion.inicial_usd, ESCALA_TOTAL),
        ),
    ).lastrowid


def sesion_abierta(conexion: sqlite3.Connection) -> CajaSesion | None:
    """RF-44. La unica sesion abierta, si la hay."""
    fila = conexion.execute(
        f"SELECT {_CAMPOS} FROM caja_sesion WHERE estado = ?", (ABIERTA,)
    ).fetchone()
    return _entidad(fila) if fila else None


def obtener(conexion: sqlite3.Connection, sesion_id: int) -> CajaSesion | None:
    fila = conexion.execute(
        f"SELECT {_CAMPOS} FROM caja_sesion WHERE id = ?", (sesion_id,)
    ).fetchone()
    return _entidad(fila) if fila else None


def listar(conexion: sqlite3.Connection, limite: int = 100) -> list[CajaSesion]:
    return [
        _entidad(f)
        for f in conexion.execute(
            f"SELECT {_CAMPOS} FROM caja_sesion ORDER BY id DESC LIMIT ?", (limite,)
        )
    ]


def cerrar(
    conexion: sqlite3.Connection,
    sesion_id: int,
    usuario_id: int,
    conteo_bs: Decimal,
    conteo_usd: Decimal,
    diferencia_bs: Decimal,
    diferencia_usd: Decimal,
) -> None:
    """RF-43 / RN-26. Una diferencia distinta de cero no impide cerrar."""
    conexion.execute(
        """UPDATE caja_sesion
              SET estado = ?, usuario_cierre_id = ?,
                  fecha_cierre = datetime('now','localtime'),
                  conteo_bs = ?, conteo_usd = ?,
                  diferencia_bs = ?, diferencia_usd = ?
            WHERE id = ?""",
        (
            CERRADA,
            usuario_id,
            a_entero(conteo_bs, ESCALA_TOTAL),
            a_entero(conteo_usd, ESCALA_TOTAL),
            a_entero(diferencia_bs, ESCALA_TOTAL),
            a_entero(diferencia_usd, ESCALA_TOTAL),
            sesion_id,
        ),
    )


def cobrado_por_medio(
    conexion: sqlite3.Connection, sesion_id: int
) -> dict[tuple[str, str], Decimal]:
    """RN-26. Suma de los pagos de la sesion por medio y moneda.

    Las ventas anuladas quedan fuera: su dinero se devolvio y no esta en la
    gaveta (RN-25).
    """
    return {
        (f["medio"], f["moneda"]): desde_entero(f["monto"], ESCALA_TOTAL)
        for f in conexion.execute(
            """SELECT p.medio, p.moneda, SUM(p.monto) AS monto
                 FROM venta_pago p
                 JOIN venta v ON v.id = p.venta_id
                WHERE v.caja_sesion_id = ? AND v.estado <> ?
                GROUP BY p.medio, p.moneda""",
            (sesion_id, ANULADA),
        )
    }


def vueltos_de(
    conexion: sqlite3.Connection, sesion_id: int
) -> list[tuple[Decimal, Decimal]]:
    """El vuelto entregado en cada venta, con la tasa de esa venta.

    Sale de la gaveta, asi que el arqueo lo resta. Se devuelve la tasa junto al
    monto porque el vuelto se entrega en bolivares (RN-23) y la conversion es
    del dia de la venta, no del dia del cierre.
    """
    return [
        (
            desde_entero(f["vuelto_usd"], ESCALA_TOTAL),
            desde_entero(f["valor"], ESCALA_TASA),
        )
        for f in conexion.execute(
            """SELECT v.vuelto_usd, t.valor
                 FROM venta v JOIN tasa_cambio t ON t.id = v.tasa_id
                WHERE v.caja_sesion_id = ? AND v.estado <> ? AND v.vuelto_usd > 0""",
            (sesion_id, ANULADA),
        )
    ]


def resumen_ventas(
    conexion: sqlite3.Connection, sesion_id: int
) -> tuple[int, Decimal]:
    """Cantidad de ventas validas de la sesion y lo vendido en dolares."""
    fila = conexion.execute(
        """SELECT COUNT(*) AS cantidad, COALESCE(SUM(total_usd), 0) AS total
             FROM venta WHERE caja_sesion_id = ? AND estado <> ?""",
        (sesion_id, ANULADA),
    ).fetchone()
    return fila["cantidad"], desde_entero(fila["total"], ESCALA_TOTAL)
