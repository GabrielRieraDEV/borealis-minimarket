"""Entidades del catalogo y logica de precios.

Capa de dominio: no importa `datos/`, `ui/` ni `infra/`. Los importes ya llegan
aca como `Decimal`; la conversion desde el entero escalado ocurre en `datos/`.

Requisitos RF-05, RF-06 y RF-07; reglas RN-05, RN-08, RN-09 y RN-10.
"""

from dataclasses import dataclass
from decimal import Decimal

from minimarket.dominio.dinero import convertir_a_bs, redondear_comercial
from minimarket.dominio.impuestos import (
    desglosar_precio,
    margen_sobre_costo,
    precio_desde_margen,
)


@dataclass(frozen=True)
class Categoria:
    """RF-05. Agrupa productos y les presta su margen objetivo."""

    id: int | None
    nombre: str
    margen_objetivo: Decimal
    activo: bool = True


@dataclass(frozen=True)
class AlicuotaIva:
    """RF-06. Exento (0,00 %) o gravado con su porcentaje."""

    id: int | None
    codigo: str
    nombre: str
    porcentaje: Decimal
    activo: bool = True


@dataclass
class Producto:
    """RF-01. `precio_venta_usd` YA INCLUYE IVA; no es la base imponible."""

    nombre: str
    categoria_id: int
    alicuota_iva_id: int
    precio_venta_usd: Decimal = Decimal(0)
    codigo_barras: str | None = None  # RF-03: opcional
    margen_objetivo: Decimal | None = None  # None: se usa el de la categoria
    existencia_minima: Decimal = Decimal(0)
    maneja_vencimiento: bool = False
    dias_alerta_venc: int = 15
    activo: bool = True
    id: int | None = None


def margen_aplicable(producto: Producto, categoria: Categoria) -> Decimal:
    """RN-09. El margen del producto si lo tiene; si no, el de su categoria."""
    if producto.margen_objetivo is not None:
        return producto.margen_objetivo
    return categoria.margen_objetivo


def precio_sugerido(
    costo_unitario: Decimal,
    producto: Producto,
    categoria: Categoria,
    alicuota_pct: Decimal,
) -> Decimal:
    """RF-07 / RN-09. Precio con IVA a partir del margen objetivo aplicable."""
    return precio_desde_margen(
        costo_unitario, margen_aplicable(producto, categoria), alicuota_pct
    )


def margen_resultante(
    precio_con_iva: Decimal, alicuota_pct: Decimal, costo_unitario: Decimal
) -> Decimal | None:
    """RF-07 / RN-08. Margen que deja un precio introducido a mano.

    Devuelve None si el producto todavia no tiene costo: el margen no es
    determinable y no se inventa un valor.
    """
    base, _ = desglosar_precio(precio_con_iva, alicuota_pct)
    return margen_sobre_costo(base, costo_unitario)


def precio_publico_bs(
    precio_usd: Decimal, tasa: Decimal, multiplo: Decimal = Decimal(1)
) -> Decimal:
    """RN-03 + RN-10. Precio en bolivares ya redondeado para exhibir.

    El redondeo comercial toca solo el importe en bolivares que ve el publico;
    `precio_venta_usd` se guarda sin tocar.
    """
    return redondear_comercial(convertir_a_bs(precio_usd, tasa), multiplo)
