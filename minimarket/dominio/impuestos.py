"""IVA y margenes de ganancia.

El precio exhibido incluye el IVA, pero el margen se calcula sobre la base
imponible. Comparar el precio con IVA contra el costo infla el margen y lleva a
fijar precios por debajo de lo necesario. El IVA no es ingreso del negocio.

Reglas RN-05, RN-08 y RN-09 de docs/reglas-de-negocio.md.
"""

from decimal import Decimal

from minimarket.dominio.dinero import (
    DECIMALES_PORCENTAJE,
    DECIMALES_PRECIO,
    redondear,
)

CIEN = Decimal(100)


def desglosar_precio(
    precio_con_iva: Decimal,
    alicuota_pct: Decimal,
    decimales: int = DECIMALES_PRECIO,
) -> tuple[Decimal, Decimal]:
    """RN-05. Separa un precio con IVA incluido en (base imponible, IVA).

    En los productos exentos la alicuota es cero: la base coincide con el precio
    y el IVA es cero, sin tratamiento especial.

    `decimales` es 4 al desglosar un precio de catalogo y 2 al desglosar el
    total de una linea de venta (RN-20). El IVA sale por resta para que base e
    IVA sumen siempre el precio exacto.
    """
    base = redondear(precio_con_iva / (1 + alicuota_pct / CIEN), decimales)
    return base, precio_con_iva - base


def margen_sobre_costo(
    base_imponible: Decimal, costo_unitario: Decimal
) -> Decimal | None:
    """RN-08. Margen porcentual sobre el costo.

    Devuelve None cuando el producto no tiene costo registrado: la
    especificacion pide informar el margen como no determinable en vez de
    inventar un valor (seccion 7 de docs/reglas-de-negocio.md).
    """
    if costo_unitario == 0:
        return None
    margen = (base_imponible - costo_unitario) / costo_unitario * CIEN
    return redondear(margen, DECIMALES_PORCENTAJE)


def precio_desde_margen(
    costo_unitario: Decimal, margen_pct: Decimal, alicuota_pct: Decimal
) -> Decimal:
    """RN-09. Precio de venta con IVA incluido a partir del margen objetivo.

    Se calcula por pasos, redondeando la base y el IVA a cuatro decimales antes
    de sumarlos, tal como lo hacen los ejemplos trabajados A y B. El resultado
    todavia no paso por el redondeo comercial de RN-10, que se aplica sobre el
    importe en bolivares al mostrarlo.
    """
    base = redondear(costo_unitario * (1 + margen_pct / CIEN), DECIMALES_PRECIO)
    iva = redondear(base * alicuota_pct / CIEN, DECIMALES_PRECIO)
    return base + iva
