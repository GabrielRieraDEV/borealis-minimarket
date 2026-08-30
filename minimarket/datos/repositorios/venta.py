"""Repositorio del agregado venta: encabezado, detalle, pagos y cliente.

RF-34 a RF-41. Las tres tablas de la venta se escriben y se leen juntas, asi
que viven en un solo modulo, igual que el agregado compra. El cliente (RF-40)
entra aca por lo mismo: se crea al facturar y no tiene pantalla propia.

Escalas: cantidades x1.000, precios y costos x10.000, totales x100.
"""

import sqlite3
from decimal import Decimal

from minimarket.dominio.dinero import (
    ESCALA_CANTIDAD,
    ESCALA_PORCENTAJE,
    ESCALA_PRECIO,
    ESCALA_TASA,
    ESCALA_TOTAL,
    a_entero,
    desde_entero,
)
from minimarket.dominio.venta import (
    ANULADA,
    Cliente,
    LineaVenta,
    Pago,
    Venta,
)

_CAMPOS = """id, numero, caja_sesion_id, usuario_id, cliente_id, tasa_id,
             fecha_hora, exento_usd, base_imponible_usd, iva_usd, total_usd,
             total_bs, vuelto_usd, estado, motivo_anulacion"""


def _entidad(fila: sqlite3.Row, tasa: Decimal) -> Venta:
    return Venta(
        id=fila["id"],
        numero=fila["numero"],
        caja_sesion_id=fila["caja_sesion_id"],
        usuario_id=fila["usuario_id"],
        cliente_id=fila["cliente_id"],
        tasa_id=fila["tasa_id"],
        tasa=tasa,
        fecha_hora=fila["fecha_hora"],
        estado=fila["estado"],
        motivo_anulacion=fila["motivo_anulacion"],
    )


def _linea(fila: sqlite3.Row) -> LineaVenta:
    return LineaVenta(
        id=fila["id"],
        producto_id=fila["producto_id"],
        lote_id=fila["lote_id"],
        descripcion=fila["descripcion"],
        cantidad=desde_entero(fila["cantidad"], ESCALA_CANTIDAD),
        precio_unit_usd=desde_entero(fila["precio_unit_usd"], ESCALA_PRECIO),
        alicuota_pct=desde_entero(fila["alicuota_pct"], ESCALA_PORCENTAJE),
        costo_unitario_usd=desde_entero(fila["costo_unitario_usd"], ESCALA_PRECIO),
    )


def siguiente_numero(conexion: sqlite3.Connection) -> int:
    """RN-24. Consecutivo que no se reutiliza ni se reinicia por periodo.

    Se toma el maximo, no la cantidad de filas: una venta anulada conserva su
    numero y no libera el hueco. Va dentro de la transaccion de la venta, que
    abre en modo IMMEDIATE y deja un solo escritor a la vez.
    """
    return conexion.execute("SELECT COALESCE(MAX(numero), 0) + 1 FROM venta").fetchone()[
        0
    ]


def crear(conexion: sqlite3.Connection, venta: Venta) -> int:
    """RF-38. Encabezado con los totales ya calculados por el dominio."""
    return conexion.execute(
        """INSERT INTO venta (numero, caja_sesion_id, usuario_id, cliente_id,
                              tasa_id, exento_usd, base_imponible_usd, iva_usd,
                              total_usd, total_bs, vuelto_usd, estado)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            venta.numero,
            venta.caja_sesion_id,
            venta.usuario_id,
            venta.cliente_id,
            venta.tasa_id,
            a_entero(venta.exento_usd, ESCALA_TOTAL),
            a_entero(venta.base_imponible_usd, ESCALA_TOTAL),
            a_entero(venta.iva_usd, ESCALA_TOTAL),
            a_entero(venta.total_usd, ESCALA_TOTAL),
            a_entero(venta.total_bs, ESCALA_TOTAL),
            a_entero(venta.vuelto_usd, ESCALA_TOTAL),
            venta.estado,
        ),
    ).lastrowid


def agregar_linea(
    conexion: sqlite3.Connection, venta_id: int, linea: LineaVenta
) -> int:
    """RN-19. Guarda la copia del costo, del precio y de la alicuota."""
    return conexion.execute(
        """INSERT INTO venta_detalle
               (venta_id, producto_id, lote_id, descripcion, cantidad,
                precio_unit_usd, alicuota_pct, base_imponible_usd, iva_usd,
                total_linea_usd, costo_unitario_usd)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            venta_id,
            linea.producto_id,
            linea.lote_id,
            linea.descripcion,
            a_entero(linea.cantidad, ESCALA_CANTIDAD),
            a_entero(linea.precio_unit_usd, ESCALA_PRECIO),
            a_entero(linea.alicuota_pct, ESCALA_PORCENTAJE),
            a_entero(linea.base_imponible_usd, ESCALA_TOTAL),
            a_entero(linea.iva_usd, ESCALA_TOTAL),
            a_entero(linea.total_linea_usd, ESCALA_TOTAL),
            a_entero(linea.costo_unitario_usd, ESCALA_PRECIO),
        ),
    ).lastrowid


def registrar_pago(conexion: sqlite3.Connection, venta_id: int, pago: Pago) -> int:
    """RN-22. Monto en su moneda y equivalente en dolares a la tasa del dia."""
    return conexion.execute(
        """INSERT INTO venta_pago (venta_id, medio, moneda, monto, monto_usd,
                                   referencia)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            venta_id,
            pago.medio,
            pago.moneda,
            a_entero(pago.monto, ESCALA_TOTAL),
            a_entero(pago.monto_usd, ESCALA_TOTAL),
            pago.referencia or None,
        ),
    ).lastrowid


def obtener(conexion: sqlite3.Connection, venta_id: int) -> Venta | None:
    """Venta completa: encabezado, lineas y pagos."""
    fila = conexion.execute(
        f"""SELECT {_CAMPOS}, (SELECT valor FROM tasa_cambio t WHERE t.id = tasa_id)
                   AS tasa_valor
              FROM venta WHERE id = ?""",
        (venta_id,),
    ).fetchone()
    if fila is None:
        return None
    venta = _entidad(fila, desde_entero(fila["tasa_valor"], ESCALA_TASA))
    venta.lineas = lineas_de(conexion, venta_id)
    venta.pagos = pagos_de(conexion, venta_id)
    return venta


def por_numero(conexion: sqlite3.Connection, numero: int) -> Venta | None:
    fila = conexion.execute("SELECT id FROM venta WHERE numero = ?", (numero,)).fetchone()
    return obtener(conexion, fila[0]) if fila else None


def lineas_de(conexion: sqlite3.Connection, venta_id: int) -> list[LineaVenta]:
    return [
        _linea(f)
        for f in conexion.execute(
            """SELECT id, producto_id, lote_id, descripcion, cantidad,
                      precio_unit_usd, alicuota_pct, costo_unitario_usd
                 FROM venta_detalle WHERE venta_id = ? ORDER BY id""",
            (venta_id,),
        )
    ]


def pagos_de(conexion: sqlite3.Connection, venta_id: int) -> list[Pago]:
    return [
        Pago(
            id=f["id"],
            medio=f["medio"],
            moneda=f["moneda"],
            monto=desde_entero(f["monto"], ESCALA_TOTAL),
            monto_usd=desde_entero(f["monto_usd"], ESCALA_TOTAL),
            referencia=f["referencia"],
        )
        for f in conexion.execute(
            """SELECT id, medio, moneda, monto, monto_usd, referencia
                 FROM venta_pago WHERE venta_id = ? ORDER BY id""",
            (venta_id,),
        )
    ]


def listar(
    conexion: sqlite3.Connection,
    desde: str | None = None,
    hasta: str | None = None,
    caja_sesion_id: int | None = None,
    incluir_anuladas: bool = True,
    limite: int = 200,
) -> list[Venta]:
    """Encabezados sin detalle: la pantalla lo pide al abrir una venta."""
    sql = f"""SELECT {_CAMPOS},
                     (SELECT valor FROM tasa_cambio t WHERE t.id = tasa_id)
                     AS tasa_valor
                FROM venta WHERE 1 = 1"""
    parametros: list[object] = []
    if desde:
        sql += " AND fecha_hora >= ?"
        parametros.append(desde)
    if hasta:
        # `hasta` llega como fecha; el encabezado guarda fecha y hora.
        sql += " AND fecha_hora <= ?"
        parametros.append(f"{hasta} 23:59:59")
    if caja_sesion_id is not None:
        sql += " AND caja_sesion_id = ?"
        parametros.append(caja_sesion_id)
    if not incluir_anuladas:
        sql += f" AND estado <> '{ANULADA}'"
    sql += " ORDER BY numero DESC LIMIT ?"
    parametros.append(limite)
    return [
        _entidad(f, desde_entero(f["tasa_valor"], ESCALA_TASA))
        for f in conexion.execute(sql, parametros)
    ]


def anular(
    conexion: sqlite3.Connection, venta_id: int, usuario_id: int, motivo: str
) -> None:
    """RF-41 / RN-25. El documento se conserva; solo cambia de estado."""
    conexion.execute(
        """UPDATE venta
              SET estado = ?, anulada_por = ?, motivo_anulacion = ?,
                  anulada_en = datetime('now','localtime')
            WHERE id = ?""",
        (ANULADA, usuario_id, motivo, venta_id),
    )


# --- Clientes (RF-40) -------------------------------------------------------


def obtener_cliente(conexion: sqlite3.Connection, cliente_id: int) -> Cliente | None:
    fila = conexion.execute(
        """SELECT id, tipo, razon_social, rif, direccion_fiscal, telefono
             FROM cliente WHERE id = ?""",
        (cliente_id,),
    ).fetchone()
    return _cliente(fila) if fila else None


def cliente_por_rif(conexion: sqlite3.Connection, rif: str) -> Cliente | None:
    fila = conexion.execute(
        """SELECT id, tipo, razon_social, rif, direccion_fiscal, telefono
             FROM cliente WHERE rif = ?""",
        (rif,),
    ).fetchone()
    return _cliente(fila) if fila else None


def crear_cliente(conexion: sqlite3.Connection, cliente: Cliente) -> int:
    return conexion.execute(
        """INSERT INTO cliente (tipo, razon_social, rif, direccion_fiscal, telefono)
           VALUES (?, ?, ?, ?, ?)""",
        (
            cliente.tipo,
            cliente.razon_social,
            cliente.rif or None,
            cliente.direccion_fiscal,
            cliente.telefono,
        ),
    ).lastrowid


def _cliente(fila: sqlite3.Row) -> Cliente:
    return Cliente(
        id=fila["id"],
        tipo=fila["tipo"],
        razon_social=fila["razon_social"],
        rif=fila["rif"],
        direccion_fiscal=fila["direccion_fiscal"],
        telefono=fila["telefono"],
    )
