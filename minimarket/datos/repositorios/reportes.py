"""Consultas agregadas de los reportes (RF-48, RF-50, RF-52).

Cruzan varias tablas y no pertenecen a ningun agregado, asi que viven juntas.
Las ventas anuladas quedan fuera de todo (RN-25) salvo del libro de ventas,
donde figuran con importes en cero (RN-31).
"""

import sqlite3
from decimal import Decimal

from minimarket.dominio.dinero import (
    ESCALA_CANTIDAD,
    ESCALA_TASA,
    ESCALA_TOTAL,
    desde_entero,
)
from minimarket.dominio.reportes import (
    FilaGanancia,
    FilaLibro,
    FilaPerdida,
    ProductoVendido,
    ResumenVentas,
    TotalPorMedio,
)
from minimarket.dominio.venta import ANULADA

# RN-27. Σ redondear(cantidad × costo_unitario_congelado, 2) resuelto en SQL.
# `cantidad` viene x1.000 y `costo_unitario_usd` x10.000, asi que el producto
# queda x10.000.000 y hay que devolverlo a x100. Sumar medio paso (50.000)
# antes de la division entera es ROUND_HALF_UP: el mismo redondeo por linea
# que hace `LineaVenta.costo_total_usd`, y ambas cantidades son positivas.
_CMV = "SUM((d.cantidad * d.costo_unitario_usd + 50000) / 100000)"

# El detalle guarda la base imponible de CADA linea; en una linea exenta esa
# base es el total de la linea. Sumarlas todas da base imponible + exento, que
# es el ingreso de RN-28.
_INGRESO = "SUM(d.base_imponible_usd)"

_RANGO = "AND v.fecha_hora >= ? AND v.fecha_hora <= ?"


def _limites(desde: str, hasta: str) -> list[object]:
    """El encabezado guarda fecha y hora; el filtro llega como fecha."""
    return [desde, f"{hasta} 23:59:59"]


def resumen_ventas(
    conexion: sqlite3.Connection, desde: str, hasta: str
) -> ResumenVentas:
    """RF-48. Totales del periodo y desglose por medio de pago."""
    fila = conexion.execute(
        f"""SELECT COUNT(*) AS cantidad,
                   COALESCE(SUM(v.exento_usd), 0)         AS exento,
                   COALESCE(SUM(v.base_imponible_usd), 0) AS base,
                   COALESCE(SUM(v.iva_usd), 0)            AS iva,
                   COALESCE(SUM(v.total_usd), 0)          AS total
              FROM venta v
             WHERE v.estado <> ? {_RANGO}""",
        [ANULADA, *_limites(desde, hasta)],
    ).fetchone()
    return ResumenVentas(
        desde=desde,
        hasta=hasta,
        cantidad=fila["cantidad"],
        exento_usd=desde_entero(fila["exento"], ESCALA_TOTAL),
        base_imponible_usd=desde_entero(fila["base"], ESCALA_TOTAL),
        iva_usd=desde_entero(fila["iva"], ESCALA_TOTAL),
        total_usd=desde_entero(fila["total"], ESCALA_TOTAL),
        por_medio=totales_por_medio(conexion, desde, hasta),
    )


def totales_por_medio(
    conexion: sqlite3.Connection,
    desde: str = "",
    hasta: str = "",
    sesion_id: int | None = None,
) -> list[TotalPorMedio]:
    """RF-48. Agrupado por medio y moneda: el efectivo convive en Bs y USD.

    Por rango de fechas, o por sesion de caja (para la venta del dia al
    cerrar); las dos cosas a la vez tambien sirven.
    """
    filtro, parametros = _filtro(desde, hasta, sesion_id)
    return [
        TotalPorMedio(
            medio=f["medio"],
            moneda=f["moneda"],
            monto=desde_entero(f["monto"], ESCALA_TOTAL),
            monto_usd=desde_entero(f["monto_usd"], ESCALA_TOTAL),
        )
        for f in conexion.execute(
            f"""SELECT p.medio, p.moneda,
                       SUM(p.monto) AS monto, SUM(p.monto_usd) AS monto_usd
                  FROM venta_pago p JOIN venta v ON v.id = p.venta_id
                 WHERE v.estado <> ? {filtro}
                 GROUP BY p.medio, p.moneda
                 ORDER BY p.medio, p.moneda""",
            [ANULADA, *parametros],
        )
    ]


def productos_vendidos(
    conexion: sqlite3.Connection,
    desde: str = "",
    hasta: str = "",
    sesion_id: int | None = None,
) -> list[ProductoVendido]:
    """La venta del dia (1.2.0): que se vendio y cuanto, de mas a menos.

    `descripcion` es la congelada en la linea, no el nombre actual del
    producto: es lo que salio en la nota.
    """
    filtro, parametros = _filtro(desde, hasta, sesion_id)
    return [
        ProductoVendido(
            producto_id=f["producto_id"],
            nombre=f["nombre"],
            cantidad=desde_entero(f["cantidad"], ESCALA_CANTIDAD),
            total_usd=desde_entero(f["total"], ESCALA_TOTAL),
        )
        for f in conexion.execute(
            f"""SELECT d.producto_id, MAX(d.descripcion) AS nombre,
                       SUM(d.cantidad) AS cantidad, SUM(d.total_linea_usd) AS total
                  FROM venta_detalle d JOIN venta v ON v.id = d.venta_id
                 WHERE v.estado <> ? {filtro}
                 GROUP BY d.producto_id
                 ORDER BY cantidad DESC, nombre""",
            [ANULADA, *parametros],
        )
    ]


def ventas_de_sesion(conexion: sqlite3.Connection, sesion_id: int) -> tuple[int, Decimal]:
    fila = conexion.execute(
        """SELECT COUNT(*) AS cantidad, COALESCE(SUM(total_usd), 0) AS total
             FROM venta WHERE caja_sesion_id = ? AND estado <> ?""",
        (sesion_id, ANULADA),
    ).fetchone()
    return fila["cantidad"], desde_entero(fila["total"], ESCALA_TOTAL)


def primera_venta(conexion: sqlite3.Connection) -> str | None:
    """La fecha de la primera venta valida; None si todavia no se vendio."""
    fila = conexion.execute(
        "SELECT MIN(fecha_hora) FROM venta WHERE estado <> ?", (ANULADA,)
    ).fetchone()
    return fila[0][:10] if fila and fila[0] else None


def _filtro(desde: str, hasta: str, sesion_id: int | None) -> tuple[str, list]:
    filtro, parametros = "", []
    if desde and hasta:
        filtro += _RANGO
        parametros += _limites(desde, hasta)
    if sesion_id is not None:
        filtro += " AND v.caja_sesion_id = ?"
        parametros.append(sesion_id)
    return filtro, parametros


def ganancia_por_producto(
    conexion: sqlite3.Connection, desde: str, hasta: str
) -> list[FilaGanancia]:
    """RF-50 / RN-27 / RN-28, con el costo congelado en la linea (RN-19)."""
    return _ganancia(
        conexion,
        """SELECT d.producto_id AS id, MAX(d.descripcion) AS nombre""",
        "GROUP BY d.producto_id",
        desde,
        hasta,
    )


def ganancia_por_categoria(
    conexion: sqlite3.Connection, desde: str, hasta: str
) -> list[FilaGanancia]:
    """RF-50. Misma cuenta, agrupada por la categoria actual del producto."""
    return _ganancia(
        conexion,
        "SELECT c.id AS id, c.nombre AS nombre",
        "GROUP BY c.id",
        desde,
        hasta,
        union="""JOIN producto pr ON pr.id = d.producto_id
                 JOIN categoria c ON c.id = pr.categoria_id""",
    )


def _ganancia(
    conexion: sqlite3.Connection,
    seleccion: str,
    agrupacion: str,
    desde: str,
    hasta: str,
    union: str = "",
) -> list[FilaGanancia]:
    filas = conexion.execute(
        f"""{seleccion},
                   SUM(d.cantidad)      AS cantidad,
                   {_INGRESO}           AS ingreso,
                   {_CMV}               AS costo,
                   SUM(CASE WHEN d.costo_unitario_usd = 0 THEN 1 ELSE 0 END)
                                        AS sin_costo
              FROM venta_detalle d
              JOIN venta v ON v.id = d.venta_id
              {union}
             WHERE v.estado <> ? {_RANGO}
             {agrupacion}
             ORDER BY nombre""",
        [ANULADA, *_limites(desde, hasta)],
    )
    return [
        FilaGanancia(
            id=f["id"],
            nombre=f["nombre"],
            cantidad=desde_entero(f["cantidad"], ESCALA_CANTIDAD),
            ingreso_usd=desde_entero(f["ingreso"], ESCALA_TOTAL),
            costo_usd=desde_entero(f["costo"], ESCALA_TOTAL),
            lineas_sin_costo=f["sin_costo"],
        )
        for f in filas
    ]


def libro_de_ventas(
    conexion: sqlite3.Connection, desde: str, hasta: str
) -> list[FilaLibro]:
    """RF-52 / RN-31. Incluye las anuladas: la fila las pone en cero.

    Se devuelve la tasa de CADA venta, no la de hoy; la conversion la hace
    `FilaLibro`.
    """
    return [
        FilaLibro(
            fecha=f["fecha_hora"][:10],
            numero=f["numero"],
            razon_social=f["razon_social"] or "Consumidor final",
            rif=f["rif"] or "",
            tasa=desde_entero(f["tasa"], ESCALA_TASA),
            exento_usd=desde_entero(f["exento_usd"], ESCALA_TOTAL),
            base_imponible_usd=desde_entero(f["base_imponible_usd"], ESCALA_TOTAL),
            iva_usd=desde_entero(f["iva_usd"], ESCALA_TOTAL),
            anulada=f["estado"] == ANULADA,
        )
        for f in conexion.execute(
            f"""SELECT v.fecha_hora, v.numero, v.estado, v.exento_usd,
                       v.base_imponible_usd, v.iva_usd, t.valor AS tasa,
                       cl.razon_social, cl.rif
                  FROM venta v
                  JOIN tasa_cambio t ON t.id = v.tasa_id
                  LEFT JOIN cliente cl ON cl.id = v.cliente_id
                 WHERE 1 = 1 {_RANGO}
                 ORDER BY v.fecha_hora, v.numero""",
            _limites(desde, hasta),
        )
    ]

# --- Perdidas del periodo (RF-53, RN-18) ------------------------------------

# Misma cuenta que _CMV pero sobre `perdida`: Σ redondear(cantidad × costo, 2)
# con enteros y ROUND_HALF_UP, igual que `Perdida.costo_total_usd`.
_COSTO_PERDIDA = "SUM((pe.cantidad * pe.costo_unitario_usd + 50000) / 100000)"


def perdidas_por_motivo(
    conexion: sqlite3.Connection, desde: str, hasta: str
) -> list[FilaPerdida]:
    """RF-53. Agrupadas por motivo, valorizadas al costo congelado (RN-18)."""
    return [
        FilaPerdida(
            motivo_id=f["motivo_id"],
            motivo=f["motivo"],
            cantidad=desde_entero(f["cantidad"], ESCALA_CANTIDAD),
            costo_usd=desde_entero(f["costo"], ESCALA_TOTAL),
        )
        for f in conexion.execute(
            f"""SELECT m.id AS motivo_id, m.nombre AS motivo,
                       SUM(pe.cantidad) AS cantidad,
                       {_COSTO_PERDIDA}  AS costo
                  FROM perdida pe
                  JOIN motivo_perdida m ON m.id = pe.motivo_id
                 WHERE pe.fecha >= ? AND pe.fecha <= ?
                 GROUP BY m.id
                 ORDER BY costo DESC""",
            (desde, hasta),
        )
    ]


def total_perdidas(conexion: sqlite3.Connection, desde: str, hasta: str) -> Decimal:
    """RN-29. Lo que las perdidas del periodo le restan al resultado."""
    fila = conexion.execute(
        f"""SELECT COALESCE({_COSTO_PERDIDA}, 0) AS costo
              FROM perdida pe WHERE pe.fecha >= ? AND pe.fecha <= ?""",
        (desde, hasta),
    ).fetchone()
    return desde_entero(fila["costo"], ESCALA_TOTAL)


def ingreso_y_cmv(
    conexion: sqlite3.Connection, desde: str, hasta: str
) -> tuple[Decimal, Decimal]:
    """RN-27 / RN-28. Ingreso sin IVA y costo de la mercancia vendida.

    Es la misma cuenta que `ganancia_por_producto` sin agrupar; se separa para
    que RF-47 no tenga que sumar filas que no va a mostrar.
    """
    fila = conexion.execute(
        f"""SELECT COALESCE({_INGRESO}, 0) AS ingreso,
                   COALESCE({_CMV}, 0)     AS costo
              FROM venta_detalle d
              JOIN venta v ON v.id = d.venta_id
             WHERE v.estado <> ? {_RANGO}""",
        [ANULADA, *_limites(desde, hasta)],
    ).fetchone()
    return (
        desde_entero(fila["ingreso"], ESCALA_TOTAL),
        desde_entero(fila["costo"], ESCALA_TOTAL),
    )


# RF-49 / RN-30 no tiene consulta propia: `repositorios.inventario.existencias`
# ya devuelve existencia y ultimo costo por producto, y `ExistenciaProducto`
# sabe valorizarse. Duplicar el SUM en SQL solo agregaria una segunda verdad.
