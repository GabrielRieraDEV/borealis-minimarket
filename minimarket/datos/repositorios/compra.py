"""Repositorio del agregado compra: encabezado, detalle y pagos.

RF-15 a RF-20. Las tres tablas se escriben y se leen juntas, asi que viven en
un solo modulo en vez de tres. Escalas: cantidades x1.000, costos unitarios
x10.000, totales x100.
"""

import sqlite3
from decimal import Decimal

from minimarket.dominio.compra import (
    ANULADA,
    Compra,
    LineaCompra,
    PagoProveedor,
)
from minimarket.dominio.dinero import (
    ESCALA_CANTIDAD,
    ESCALA_PRECIO,
    ESCALA_TOTAL,
    a_entero,
    desde_entero,
)

_CAMPOS = """id, proveedor_id, numero_documento, fecha, tasa_id, total_usd,
             saldo_pendiente_usd, estado, usuario_id, observacion, creado_en"""


def _entidad(fila: sqlite3.Row) -> Compra:
    return Compra(
        id=fila["id"],
        proveedor_id=fila["proveedor_id"],
        numero_documento=fila["numero_documento"],
        fecha=fila["fecha"],
        tasa_id=fila["tasa_id"],
        total_usd=desde_entero(fila["total_usd"], ESCALA_TOTAL),
        saldo_pendiente_usd=desde_entero(fila["saldo_pendiente_usd"], ESCALA_TOTAL),
        estado=fila["estado"],
        usuario_id=fila["usuario_id"],
        observacion=fila["observacion"],
        creado_en=fila["creado_en"],
    )


def _linea(fila: sqlite3.Row) -> LineaCompra:
    return LineaCompra(
        id=fila["id"],
        producto_id=fila["producto_id"],
        cant_presentacion=desde_entero(fila["cant_presentacion"], ESCALA_CANTIDAD),
        unid_x_presentacion=desde_entero(fila["unid_x_presentacion"], ESCALA_CANTIDAD),
        costo_present_usd=desde_entero(fila["costo_present_usd"], ESCALA_PRECIO),
        lote_id=fila["lote_id"],
    )


def crear(conexion: sqlite3.Connection, compra: Compra) -> int:
    """RF-15. Inserta el encabezado; el detalle entra por `agregar_linea`."""
    cursor = conexion.execute(
        """INSERT INTO compra (proveedor_id, numero_documento, fecha, tasa_id,
                               total_usd, saldo_pendiente_usd, estado,
                               usuario_id, observacion)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            compra.proveedor_id,
            compra.numero_documento or None,
            compra.fecha,
            compra.tasa_id,
            a_entero(compra.total_usd, ESCALA_TOTAL),
            a_entero(compra.saldo_pendiente_usd, ESCALA_TOTAL),
            compra.estado,
            compra.usuario_id,
            compra.observacion or None,
        ),
    )
    return cursor.lastrowid


def agregar_linea(
    conexion: sqlite3.Connection, compra_id: int, linea: LineaCompra
) -> int:
    """RF-16. `cantidad_unidades` y `costo_unitario_usd` los calcula RN-06."""
    cursor = conexion.execute(
        """INSERT INTO compra_detalle
               (compra_id, producto_id, cant_presentacion, unid_x_presentacion,
                cantidad_unidades, costo_present_usd, costo_unitario_usd, lote_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            compra_id,
            linea.producto_id,
            a_entero(linea.cant_presentacion, ESCALA_CANTIDAD),
            a_entero(linea.unid_x_presentacion, ESCALA_CANTIDAD),
            a_entero(linea.cantidad_unidades, ESCALA_CANTIDAD),
            a_entero(linea.costo_present_usd, ESCALA_PRECIO),
            a_entero(linea.costo_unitario_usd, ESCALA_PRECIO),
            linea.lote_id,
        ),
    )
    return cursor.lastrowid


def obtener(conexion: sqlite3.Connection, compra_id: int) -> Compra | None:
    """Devuelve la compra con su detalle cargado."""
    fila = conexion.execute(
        f"SELECT {_CAMPOS} FROM compra WHERE id = ?", (compra_id,)
    ).fetchone()
    if fila is None:
        return None
    compra = _entidad(fila)
    compra.lineas = lineas_de(conexion, compra_id)
    return compra


def lineas_de(conexion: sqlite3.Connection, compra_id: int) -> list[LineaCompra]:
    return [
        _linea(f)
        for f in conexion.execute(
            """SELECT id, producto_id, cant_presentacion, unid_x_presentacion,
                      costo_present_usd, lote_id
                 FROM compra_detalle WHERE compra_id = ? ORDER BY id""",
            (compra_id,),
        )
    ]


def listar(
    conexion: sqlite3.Connection,
    desde: str | None = None,
    hasta: str | None = None,
    proveedor_id: int | None = None,
    limite: int = 200,
) -> list[Compra]:
    """Encabezados sin detalle: la pantalla lo pide al abrir una compra."""
    sql = f"SELECT {_CAMPOS} FROM compra WHERE 1 = 1"
    parametros: list[object] = []
    if desde:
        sql += " AND fecha >= ?"
        parametros.append(desde)
    if hasta:
        sql += " AND fecha <= ?"
        parametros.append(hasta)
    if proveedor_id is not None:
        sql += " AND proveedor_id = ?"
        parametros.append(proveedor_id)
    sql += " ORDER BY fecha DESC, id DESC LIMIT ?"
    parametros.append(limite)
    return [_entidad(f) for f in conexion.execute(sql, parametros)]


def anular(conexion: sqlite3.Connection, compra_id: int, motivo: str | None) -> None:
    """RF-20 / RN-13. El registro se conserva; solo cambia de estado.

    El saldo pendiente queda en cero porque la deuda deja de existir; los
    movimientos inversos los genera el servicio.
    """
    conexion.execute(
        """UPDATE compra
              SET estado = ?, saldo_pendiente_usd = 0,
                  observacion = TRIM(COALESCE(observacion, '') || ?)
            WHERE id = ?""",
        (ANULADA, f"\n[ANULADA] {motivo}" if motivo else "\n[ANULADA]", compra_id),
    )


def registrar_pago(conexion: sqlite3.Connection, pago: PagoProveedor) -> int:
    """RF-19."""
    cursor = conexion.execute(
        """INSERT INTO pago_proveedor
               (compra_id, fecha, monto_usd, tasa_id, medio, referencia)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            pago.compra_id,
            pago.fecha,
            a_entero(pago.monto_usd, ESCALA_TOTAL),
            pago.tasa_id,
            pago.medio,
            pago.referencia or None,
        ),
    )
    return cursor.lastrowid


def pagos_de(conexion: sqlite3.Connection, compra_id: int) -> list[PagoProveedor]:
    return [
        PagoProveedor(
            id=f["id"],
            compra_id=f["compra_id"],
            fecha=f["fecha"],
            monto_usd=desde_entero(f["monto_usd"], ESCALA_TOTAL),
            tasa_id=f["tasa_id"],
            medio=f["medio"],
            referencia=f["referencia"],
        )
        for f in conexion.execute(
            """SELECT id, compra_id, fecha, monto_usd, tasa_id, medio, referencia
                 FROM pago_proveedor WHERE compra_id = ? ORDER BY fecha, id""",
            (compra_id,),
        )
    ]


def actualizar_saldo(
    conexion: sqlite3.Connection, compra_id: int, saldo_usd: Decimal
) -> None:
    """RF-19. Saldo pendiente tras imputar un pago."""
    conexion.execute(
        "UPDATE compra SET saldo_pendiente_usd = ? WHERE id = ?",
        (a_entero(saldo_usd, ESCALA_TOTAL), compra_id),
    )
