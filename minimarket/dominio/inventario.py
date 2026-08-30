"""Kardex: la existencia es la suma de los movimientos, nunca un campo.

Capa de dominio: no importa `datos/`, `ui/` ni `infra/`. Los importes llegan
aca como `Decimal`; la conversion desde el entero escalado ocurre en `datos/`.

Reglas RN-06, RN-11 a RN-18 de docs/reglas-de-negocio.md.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from minimarket.dominio.dinero import (
    DECIMALES_CANTIDAD,
    DECIMALES_PRECIO,
    DECIMALES_TOTAL,
    redondear,
)

# RN-12. Tipos de movimiento. El signo lo lleva la cantidad, no el tipo.
INICIAL = "INICIAL"
COMPRA = "COMPRA"
VENTA = "VENTA"
ANULACION_VENTA = "ANULACION_VENTA"
ANULACION_COMPRA = "ANULACION_COMPRA"
PERDIDA = "PERDIDA"
AJUSTE = "AJUSTE"

# `movimiento_inventario.referencia_tipo`: la operacion que origino el movimiento.
# Una anulacion referencia la operacion original, no a si misma (RN-13).
REF_INICIAL = "INICIAL"
REF_COMPRA = "COMPRA"
REF_VENTA = "VENTA"
REF_PERDIDA = "PERDIDA"
REF_AJUSTE = "AJUSTE"


@dataclass(frozen=True)
class Lote:
    """RF-21. Solo lo tienen los productos con control de vencimiento."""

    producto_id: int
    fecha_vencimiento: str  # AAAA-MM-DD
    codigo: str | None = None
    id: int | None = None


@dataclass(frozen=True)
class Movimiento:
    """RF-23. Cantidad con signo: positiva entra, negativa sale.

    `costo_unitario_usd` queda congelado en el instante del movimiento (RN-14)
    y no se recalcula nunca.
    """

    producto_id: int
    tipo: str
    cantidad: Decimal
    costo_unitario_usd: Decimal
    referencia_tipo: str
    referencia_id: int
    usuario_id: int
    lote_id: int | None = None
    observacion: str | None = None
    fecha_hora: str | None = None
    id: int | None = None


@dataclass(frozen=True)
class SaldoLote:
    """Existencia disponible de un lote, para repartir una salida (RN-15)."""

    lote_id: int
    fecha_vencimiento: str
    cantidad: Decimal


@dataclass(frozen=True)
class ExistenciaProducto:
    """Fila de la consulta de existencias (RF-22, RF-24)."""

    producto_id: int
    nombre: str
    existencia: Decimal
    existencia_minima: Decimal
    ultimo_costo: Decimal | None

    @property
    def en_alerta(self) -> bool:
        """RN-16."""
        return hay_alerta_minimo(self.existencia, self.existencia_minima)

    @property
    def valorizacion(self) -> Decimal:
        """Existencia valorizada al ultimo costo conocido (RN-07)."""
        return redondear(self.existencia * (self.ultimo_costo or 0), DECIMALES_TOTAL)


@dataclass(frozen=True)
class MotivoPerdida:
    """RF-29. Los cinco de fabrica los siembra `esquema.sql`; se pueden sumar."""

    codigo: str
    nombre: str
    activo: bool = True
    id: int | None = None


@dataclass(frozen=True)
class Perdida:
    """RF-28 / RN-18. `costo_unitario_usd` es el vigente EN LA FECHA de la baja.

    ponytail: vive en este modulo y no en `dominio/perdida.py`. Una perdida es
    una salida de inventario que se valoriza con `valorizar`, que ya esta aca;
    un archivo para dos dataclases duplicaria los imports sin agregar nada.
    """

    producto_id: int
    motivo_id: int
    cantidad: Decimal
    costo_unitario_usd: Decimal
    fecha: str
    usuario_id: int
    lote_id: int | None = None
    observacion: str | None = None
    # Solo los completa la consulta; el alta no los necesita.
    producto: str | None = None
    motivo: str | None = None
    id: int | None = None

    @property
    def costo_total_usd(self) -> Decimal:
        """RN-18. Lo que la perdida le resta al resultado del periodo."""
        return valorizar(self.cantidad, self.costo_unitario_usd)

    @property
    def determinable(self) -> bool:
        """El producto sin compra previa a la fecha se valoriza en cero."""
        return self.costo_unitario_usd > 0


@dataclass(frozen=True)
class SaldoLoteProducto:
    """RF-31 / RF-54. Un lote con existencia viva y su producto."""

    lote_id: int
    producto_id: int
    producto: str
    codigo: str | None
    fecha_vencimiento: str
    cantidad: Decimal
    dias_alerta: int
    ultimo_costo: Decimal | None = None

    def dias_para_vencer(self, hoy: str | None = None) -> int:
        """Negativo si ya vencio."""
        referencia = date.fromisoformat(hoy) if hoy else date.today()
        return (date.fromisoformat(self.fecha_vencimiento) - referencia).days

    def en_alerta(self, hoy: str | None = None) -> bool:
        """RN-17, con los dias configurados para ESE producto."""
        return en_alerta_vencimiento(self.fecha_vencimiento, self.dias_alerta, hoy)

    def vencido(self, hoy: str | None = None) -> bool:
        return self.dias_para_vencer(hoy) < 0

    @property
    def valorizacion(self) -> Decimal:
        """Lo que se pierde si el lote se da de baja entero (RN-18)."""
        return valorizar(self.cantidad, self.ultimo_costo or Decimal(0))


def costo_unitario(costo_presentacion: Decimal, unidades: Decimal) -> Decimal:
    """RN-06. Costo de la presentacion dividido sus unidades.

    Las unidades por presentacion se capturan POR LINEA de compra: el mismo
    producto puede venir en bulto de 20 hoy y de 24 la proxima vez.
    """
    if unidades <= 0:
        raise ValueError("Las unidades por presentacion deben ser mayores que cero.")
    return redondear(costo_presentacion / unidades, DECIMALES_PRECIO)


def cantidad_unidades(presentaciones: Decimal, unidades: Decimal) -> Decimal:
    """Unidades sueltas que entran por una linea de compra."""
    return redondear(presentaciones * unidades, DECIMALES_CANTIDAD)


def existencia(movimientos: list[Movimiento]) -> Decimal:
    """RN-11. La existencia es la suma de los movimientos y nada mas."""
    total = sum((m.cantidad for m in movimientos), Decimal(0))
    return redondear(total, DECIMALES_CANTIDAD)


def hay_alerta_minimo(existencia_actual: Decimal, minima: Decimal) -> bool:
    """RN-16. Alerta cuando la existencia es igual o inferior a la minima."""
    return existencia_actual <= minima


def en_alerta_vencimiento(
    fecha_vencimiento: str, dias_alerta: int, hoy: str | None = None
) -> bool:
    """RN-17. Alerta cuando faltan `dias_alerta` dias o menos para vencer.

    Un lote ya vencido tambien alerta: la diferencia es negativa.
    """
    referencia = date.fromisoformat(hoy) if hoy else date.today()
    return (date.fromisoformat(fecha_vencimiento) - referencia).days <= dias_alerta


def repartir_por_lote(
    cantidad: Decimal, saldos: list[SaldoLote]
) -> list[tuple[int | None, Decimal]]:
    """RN-15. Reparte una salida entre lotes, vencimiento mas proximo primero.

    Si la cantidad excede lo disponible en lotes, el sobrante sale como
    `(None, cantidad)`: el reparto no decide si la venta procede. Esa decision
    es de RF-27, que compara contra la existencia total y admite la
    autorizacion del administrador.
    """
    if cantidad <= 0:
        raise ValueError("La cantidad a repartir debe ser mayor que cero.")
    reparto: list[tuple[int | None, Decimal]] = []
    restante = cantidad
    for saldo in sorted(saldos, key=lambda s: (s.fecha_vencimiento, s.lote_id)):
        if restante <= 0:
            break
        if saldo.cantidad <= 0:
            continue
        tomado = min(saldo.cantidad, restante)
        reparto.append((saldo.lote_id, tomado))
        restante -= tomado
    if restante > 0:
        reparto.append((None, restante))
    return reparto


def valorizar(cantidad: Decimal, costo_unitario_usd: Decimal) -> Decimal:
    """RN-18. Valoriza una cantidad al costo vigente indicado."""
    return redondear(abs(cantidad) * costo_unitario_usd, DECIMALES_TOTAL)
