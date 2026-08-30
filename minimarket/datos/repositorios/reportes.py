"""Consultas agregadas de los reportes (RF-48, RF-50, RF-52).

Cruzan varias tablas y no pertenecen a ningun agregado, asi que viven juntas.
Las ventas anuladas quedan fuera de todo (RN-25) salvo del libro de ventas,
donde figuran con importes en cero (RN-31).
"""

import sqlite3

from minimarket.dominio.dinero import (
    ESCALA_CANTIDAD,
    ESCALA_TASA,
    ESCALA_TOTAL,
    desde_entero,
)
from minimarket.dominio.reportes import (
    FilaGanancia,
    FilaLibro,
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
    conexion: sqlite3.Connection, desde: str, hasta: str
) -> list[TotalPorMedio]:
    """RF-48. Agrupado por medio y moneda: el efectivo convive en Bs y USD."""
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
                 WHERE v.estado <> ? {_RANGO}
                 GROUP BY p.medio, p.moneda
                 ORDER BY p.medio, p.moneda""",
            [ANULADA, *_limites(desde, hasta)],
        )
    ]


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

# RF-49 / RN-30 no tiene consulta propia: `repositorios.inventario.existencias`
# ya devuelve existencia y ultimo costo por producto, y `ExistenciaProducto`
# sabe valorizarse. Duplicar el SUM en SQL solo agregaria una segunda verdad.
