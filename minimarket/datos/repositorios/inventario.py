"""Repositorio de lotes, movimientos y ajustes de inventario.

RF-18, RF-21 a RF-25. La existencia NO se guarda: se consulta a la vista
`v_existencia`, que suma los movimientos (RN-11).
"""

import sqlite3
from decimal import Decimal

from minimarket.dominio.dinero import (
    ESCALA_CANTIDAD,
    ESCALA_PRECIO,
    a_entero,
    desde_entero,
)
from minimarket.dominio.inventario import (
    ExistenciaProducto,
    Lote,
    Movimiento,
    SaldoLote,
    SaldoLoteProducto,
)


# --- Lotes (RF-21) ----------------------------------------------------------


def obtener_o_crear_lote(
    conexion: sqlite3.Connection,
    producto_id: int,
    fecha_vencimiento: str,
    codigo: str | None = None,
) -> int:
    """Reutiliza el lote del producto con esa fecha; si no existe, lo crea.

    Dos compras del mismo producto con el mismo vencimiento son el mismo lote:
    duplicarlo partiria la existencia sin motivo.
    """
    fila = conexion.execute(
        "SELECT id FROM lote WHERE producto_id = ? AND fecha_vencimiento = ?",
        (producto_id, fecha_vencimiento),
    ).fetchone()
    if fila is not None:
        return fila[0]
    return conexion.execute(
        "INSERT INTO lote (producto_id, codigo, fecha_vencimiento) VALUES (?, ?, ?)",
        (producto_id, codigo or None, fecha_vencimiento),
    ).lastrowid


def lotes_de(conexion: sqlite3.Connection, producto_id: int) -> list[Lote]:
    return [
        Lote(
            id=f["id"],
            producto_id=f["producto_id"],
            codigo=f["codigo"],
            fecha_vencimiento=f["fecha_vencimiento"],
        )
        for f in conexion.execute(
            """SELECT id, producto_id, codigo, fecha_vencimiento FROM lote
                WHERE producto_id = ? ORDER BY fecha_vencimiento""",
            (producto_id,),
        )
    ]


def obtener_lote(conexion: sqlite3.Connection, lote_id: int) -> Lote | None:
    fila = conexion.execute(
        "SELECT id, producto_id, codigo, fecha_vencimiento FROM lote WHERE id = ?",
        (lote_id,),
    ).fetchone()
    return (
        Lote(
            id=fila["id"],
            producto_id=fila["producto_id"],
            codigo=fila["codigo"],
            fecha_vencimiento=fila["fecha_vencimiento"],
        )
        if fila
        else None
    )


def saldos_por_lote(conexion: sqlite3.Connection, producto_id: int) -> list[SaldoLote]:
    """RN-15. Existencia viva de cada lote, la mas proxima a vencer primero."""
    return [
        SaldoLote(
            lote_id=f["lote_id"],
            fecha_vencimiento=f["fecha_vencimiento"],
            cantidad=desde_entero(f["cantidad"], ESCALA_CANTIDAD),
        )
        for f in conexion.execute(
            """SELECT m.lote_id AS lote_id,
                      l.fecha_vencimiento AS fecha_vencimiento,
                      SUM(m.cantidad) AS cantidad
                 FROM movimiento_inventario m
                 JOIN lote l ON l.id = m.lote_id
                WHERE m.producto_id = ? AND m.lote_id IS NOT NULL
                GROUP BY m.lote_id, l.fecha_vencimiento
               HAVING SUM(m.cantidad) > 0
                ORDER BY l.fecha_vencimiento, m.lote_id""",
            (producto_id,),
        )
    ]


def saldo_de_lote(conexion: sqlite3.Connection, lote_id: int) -> Decimal:
    """RF-32. Lo que queda vivo de un lote, para darlo de baja entero."""
    fila = conexion.execute(
        """SELECT COALESCE(SUM(cantidad), 0) FROM movimiento_inventario
            WHERE lote_id = ?""",
        (lote_id,),
    ).fetchone()
    return desde_entero(fila[0], ESCALA_CANTIDAD)


def lotes_con_saldo(conexion: sqlite3.Connection) -> list[SaldoLoteProducto]:
    """RF-31 / RF-54. Todos los lotes con existencia viva, con su producto.

    ponytail: devuelve TODOS y el filtro por proximidad lo hace RN-17 en
    `dominio/inventario.en_alerta_vencimiento`, que es donde esta escrita la
    regla una sola vez. Solo los productos con control de vencimiento tienen
    lotes, asi que son unos pocos cientos. Si algun dia pesa, el limite entra
    aca como `l.fecha_vencimiento <= date('now','localtime','+N days')` y la
    regla sigue viviendo en el dominio.
    """
    return [
        SaldoLoteProducto(
            lote_id=f["lote_id"],
            producto_id=f["producto_id"],
            producto=f["producto"],
            codigo=f["codigo"],
            fecha_vencimiento=f["fecha_vencimiento"],
            cantidad=desde_entero(f["cantidad"], ESCALA_CANTIDAD),
            dias_alerta=f["dias_alerta_venc"],
            ultimo_costo=(
                None
                if f["ultimo_costo"] is None
                else desde_entero(f["ultimo_costo"], ESCALA_PRECIO)
            ),
        )
        for f in conexion.execute(
            """SELECT l.id AS lote_id, l.codigo, l.fecha_vencimiento,
                      p.id AS producto_id, p.nombre AS producto,
                      p.dias_alerta_venc,
                      uc.costo_unitario_usd AS ultimo_costo,
                      SUM(m.cantidad) AS cantidad
                 FROM movimiento_inventario m
                 JOIN lote l     ON l.id = m.lote_id
                 JOIN producto p ON p.id = l.producto_id
                 LEFT JOIN v_ultimo_costo uc ON uc.producto_id = p.id
                WHERE p.activo = 1
                GROUP BY l.id
               HAVING SUM(m.cantidad) > 0
                ORDER BY l.fecha_vencimiento, p.nombre"""
        )
    ]


# --- Movimientos (RF-18, RF-23) ---------------------------------------------


def registrar_movimiento(conexion: sqlite3.Connection, movimiento: Movimiento) -> int:
    """RF-23 / RN-14. El costo unitario queda congelado en este instante."""
    return conexion.execute(
        """INSERT INTO movimiento_inventario
               (producto_id, lote_id, tipo, cantidad, costo_unitario_usd,
                referencia_tipo, referencia_id, usuario_id, observacion)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            movimiento.producto_id,
            movimiento.lote_id,
            movimiento.tipo,
            a_entero(movimiento.cantidad, ESCALA_CANTIDAD),
            a_entero(movimiento.costo_unitario_usd, ESCALA_PRECIO),
            movimiento.referencia_tipo,
            movimiento.referencia_id,
            movimiento.usuario_id,
            movimiento.observacion or None,
        ),
    ).lastrowid


def movimientos_de(
    conexion: sqlite3.Connection, producto_id: int, limite: int = 500
) -> list[Movimiento]:
    """Kardex del producto, del mas reciente al mas viejo."""
    return [
        Movimiento(
            id=f["id"],
            producto_id=f["producto_id"],
            lote_id=f["lote_id"],
            tipo=f["tipo"],
            cantidad=desde_entero(f["cantidad"], ESCALA_CANTIDAD),
            costo_unitario_usd=desde_entero(f["costo_unitario_usd"], ESCALA_PRECIO),
            referencia_tipo=f["referencia_tipo"],
            referencia_id=f["referencia_id"],
            usuario_id=f["usuario_id"],
            observacion=f["observacion"],
            fecha_hora=f["fecha_hora"],
        )
        for f in conexion.execute(
            """SELECT id, producto_id, lote_id, tipo, cantidad, costo_unitario_usd,
                      referencia_tipo, referencia_id, usuario_id, observacion,
                      fecha_hora
                 FROM movimiento_inventario
                WHERE producto_id = ?
                ORDER BY fecha_hora DESC, id DESC LIMIT ?""",
            (producto_id, limite),
        )
    ]


def movimientos_de_referencia(
    conexion: sqlite3.Connection, referencia_tipo: str, referencia_id: int
) -> list[Movimiento]:
    """Los movimientos que origino una operacion. RF-20 los invierte."""
    return [
        Movimiento(
            id=f["id"],
            producto_id=f["producto_id"],
            lote_id=f["lote_id"],
            tipo=f["tipo"],
            cantidad=desde_entero(f["cantidad"], ESCALA_CANTIDAD),
            costo_unitario_usd=desde_entero(f["costo_unitario_usd"], ESCALA_PRECIO),
            referencia_tipo=f["referencia_tipo"],
            referencia_id=f["referencia_id"],
            usuario_id=f["usuario_id"],
        )
        for f in conexion.execute(
            """SELECT id, producto_id, lote_id, tipo, cantidad, costo_unitario_usd,
                      referencia_tipo, referencia_id, usuario_id
                 FROM movimiento_inventario
                WHERE referencia_tipo = ? AND referencia_id = ?
                ORDER BY id""",
            (referencia_tipo, referencia_id),
        )
    ]


# --- Existencias (RF-22, RF-24) ---------------------------------------------


def existencia(conexion: sqlite3.Connection, producto_id: int) -> Decimal:
    """RF-22 / RN-11. Suma de los movimientos del producto."""
    fila = conexion.execute(
        "SELECT existencia FROM v_existencia WHERE producto_id = ?", (producto_id,)
    ).fetchone()
    return desde_entero(fila[0] if fila else 0, ESCALA_CANTIDAD)


def existencias(
    conexion: sqlite3.Connection,
    texto: str | None = None,
    solo_alerta: bool = False,
    solo_activos: bool = True,
    limite: int = 2000,
) -> list[ExistenciaProducto]:
    """RF-22 y RF-24 en una sola consulta, con el ultimo costo para valorizar."""
    sql = """SELECT p.id, p.nombre, p.existencia_minima,
                    COALESCE(e.existencia, 0) AS existencia,
                    uc.costo_unitario_usd     AS ultimo_costo
               FROM producto p
               JOIN v_existencia e   ON e.producto_id = p.id
               LEFT JOIN v_ultimo_costo uc ON uc.producto_id = p.id
              WHERE 1 = 1"""
    parametros: list[object] = []
    if solo_activos:
        sql += " AND p.activo = 1"
    if texto:
        sql += " AND (LOWER(p.nombre) LIKE ? OR p.codigo_barras = ?)"
        parametros += [f"%{texto.lower()}%", texto]
    if solo_alerta:
        sql += " AND COALESCE(e.existencia, 0) <= p.existencia_minima"
    sql += " ORDER BY p.nombre LIMIT ?"
    parametros.append(limite)
    return [
        ExistenciaProducto(
            producto_id=f["id"],
            nombre=f["nombre"],
            existencia=desde_entero(f["existencia"], ESCALA_CANTIDAD),
            existencia_minima=desde_entero(f["existencia_minima"], ESCALA_CANTIDAD),
            ultimo_costo=(
                None
                if f["ultimo_costo"] is None
                else desde_entero(f["ultimo_costo"], ESCALA_PRECIO)
            ),
        )
        for f in conexion.execute(sql, parametros)
    ]


# --- Ajustes por conteo fisico (RF-25) --------------------------------------


def registrar_ajuste(
    conexion: sqlite3.Connection,
    producto_id: int,
    cantidad_sistema: Decimal,
    cantidad_fisica: Decimal,
    motivo: str,
    usuario_id: int,
) -> int:
    """RF-25. Deja constancia del conteo aunque la diferencia sea cero."""
    return conexion.execute(
        """INSERT INTO ajuste_inventario
               (producto_id, cantidad_sistema, cantidad_fisica, diferencia,
                motivo, usuario_id, fecha)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now','localtime'))""",
        (
            producto_id,
            a_entero(cantidad_sistema, ESCALA_CANTIDAD),
            a_entero(cantidad_fisica, ESCALA_CANTIDAD),
            a_entero(cantidad_fisica - cantidad_sistema, ESCALA_CANTIDAD),
            motivo,
            usuario_id,
        ),
    ).lastrowid
