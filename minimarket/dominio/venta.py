"""Entidades y aritmetica de la venta y de la caja (RN-19 a RN-26).

Capa de dominio: no importa `datos/`, `ui/` ni `infra/`.

Cada linea calcula su total, lo redondea a dos decimales y recien despues se
suma (RN-20). El IVA NO se recalcula sobre el total del documento: conviven
productos exentos y gravados y el resultado diferiria de la suma de las partes.

ponytail: la caja (`CajaSesion`, `LineaCierre`) vive en este mismo modulo. Es
una sesion que agrupa ventas y su cierre es una resta; un archivo aparte para
dos dataclases y un menos no se paga solo.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from minimarket.dominio.dinero import (
    DECIMALES_TOTAL,
    convertir_a_bs,
    redondear,
    redondear_comercial,
)
from minimarket.dominio.impuestos import desglosar_precio

COMPLETADA = "COMPLETADA"
ANULADA = "ANULADA"

ABIERTA = "ABIERTA"
CERRADA = "CERRADA"

# `venta_pago.medio`. Solo EFECTIVO genera vuelto (RN-23).
EFECTIVO = "EFECTIVO"
PAGO_MOVIL = "PAGO_MOVIL"
PUNTO = "PUNTO"
TRANSFERENCIA = "TRANSFERENCIA"
MEDIOS = [EFECTIVO, PAGO_MOVIL, PUNTO, TRANSFERENCIA]

BS = "BS"
USD = "USD"
MONEDAS = [BS, USD]


@dataclass(frozen=True)
class Cliente:
    """RF-40. Solo hace falta cuando la venta se factura a nombre de alguien."""

    razon_social: str | None = None
    rif: str | None = None
    direccion_fiscal: str | None = None
    telefono: str | None = None
    tipo: str = "CONSUMIDOR_FINAL"
    id: int | None = None


@dataclass
class LineaVenta:
    """RN-19 / RN-20. `costo_unitario_usd` queda congelado al vender.

    Tambien se copian la descripcion, el precio y la alicuota: cambiar la ficha
    del producto manana no puede alterar lo que dice esta venta.
    """

    producto_id: int
    descripcion: str
    cantidad: Decimal
    precio_unit_usd: Decimal  # con IVA incluido
    alicuota_pct: Decimal
    costo_unitario_usd: Decimal
    lote_id: int | None = None
    id: int | None = None

    @property
    def exenta(self) -> bool:
        """RN-21."""
        return self.alicuota_pct == 0

    @property
    def total_linea_usd(self) -> Decimal:
        """RN-20. Se redondea aca, antes de sumar nada."""
        return redondear(self.cantidad * self.precio_unit_usd, DECIMALES_TOTAL)

    @property
    def base_imponible_usd(self) -> Decimal:
        """RN-20. En una linea exenta coincide con el total."""
        base, _ = desglosar_precio(
            self.total_linea_usd, self.alicuota_pct, DECIMALES_TOTAL
        )
        return base

    @property
    def iva_usd(self) -> Decimal:
        """RN-20. Por resta, para que base + IVA de siempre el total exacto."""
        return self.total_linea_usd - self.base_imponible_usd

    @property
    def costo_total_usd(self) -> Decimal:
        """RN-27. Costo congelado por la cantidad vendida."""
        return redondear(self.cantidad * self.costo_unitario_usd, DECIMALES_TOTAL)

    @property
    def ganancia_usd(self) -> Decimal:
        """RN-19 / RN-27. Sobre la base imponible: el IVA no es ingreso."""
        return self.base_imponible_usd - self.costo_total_usd


@dataclass
class Pago:
    """RN-22. Se guarda en su moneda original y en su equivalente en dolares."""

    medio: str
    moneda: str
    monto: Decimal
    monto_usd: Decimal = Decimal(0)
    referencia: str | None = None
    id: int | None = None

    @property
    def es_efectivo(self) -> bool:
        return self.medio == EFECTIVO


def equivalente_usd(monto: Decimal, moneda: str, tasa: Decimal) -> Decimal:
    """RN-22. Equivalente en dolares de un pago, a la tasa de la venta."""
    if moneda == USD:
        return redondear(monto, DECIMALES_TOTAL)
    return redondear(monto / tasa, DECIMALES_TOTAL)


@dataclass
class Venta:
    """RF-34 a RF-38. Se registra entera o no se registra."""

    usuario_id: int
    tasa: Decimal
    caja_sesion_id: int | None = None
    tasa_id: int | None = None
    cliente_id: int | None = None
    lineas: list[LineaVenta] = field(default_factory=list)
    pagos: list[Pago] = field(default_factory=list)
    numero: int | None = None
    estado: str = COMPLETADA
    fecha_hora: str | None = None
    motivo_anulacion: str | None = None
    id: int | None = None

    # --- Totales del documento (RN-20, RN-21) ------------------------------

    @property
    def exento_usd(self) -> Decimal:
        return sum(
            (linea.total_linea_usd for linea in self.lineas if linea.exenta),
            Decimal(0),
        )

    @property
    def base_imponible_usd(self) -> Decimal:
        return sum(
            (linea.base_imponible_usd for linea in self.lineas if not linea.exenta),
            Decimal(0),
        )

    @property
    def iva_usd(self) -> Decimal:
        return sum(
            (linea.iva_usd for linea in self.lineas if not linea.exenta), Decimal(0)
        )

    @property
    def total_usd(self) -> Decimal:
        """Suma de los totales de linea ya redondeados (RN-20)."""
        return self.exento_usd + self.base_imponible_usd + self.iva_usd

    @property
    def total_bs(self) -> Decimal:
        """RN-03. A la tasa de la venta, no a la de hoy."""
        return convertir_a_bs(self.total_usd, self.tasa)

    @property
    def ganancia_usd(self) -> Decimal:
        """RN-19. Con los costos congelados en cada linea."""
        return sum((linea.ganancia_usd for linea in self.lineas), Decimal(0))

    # --- Cobro (RN-22, RN-23) ----------------------------------------------

    @property
    def pagado_usd(self) -> Decimal:
        return sum((p.monto_usd for p in self.pagos), Decimal(0))

    @property
    def efectivo_usd(self) -> Decimal:
        return sum((p.monto_usd for p in self.pagos if p.es_efectivo), Decimal(0))

    @property
    def falta_usd(self) -> Decimal:
        """Lo que resta cobrar; cero cuando los pagos ya alcanzan (RN-22)."""
        return max(self.total_usd - self.pagado_usd, Decimal(0))

    @property
    def vuelto_usd(self) -> Decimal:
        """RN-23."""
        return max(self.pagado_usd - self.total_usd, Decimal(0))

    @property
    def vuelto_admisible(self) -> bool:
        """RN-23. Un excedente por punto o transferencia no se devuelve."""
        return self.vuelto_usd <= self.efectivo_usd

    def vuelto_bs(self, multiplo: Decimal = Decimal(1)) -> Decimal:
        """RN-23 + RN-10. El vuelto entregado en bolivares, ya redondeado."""
        return redondear_comercial(convertir_a_bs(self.vuelto_usd, self.tasa), multiplo)


# --- Caja (RF-42 a RF-45, RN-26) --------------------------------------------


@dataclass
class CajaSesion:
    """RF-42 / RF-43. Una sola abierta a la vez; lo garantiza el esquema."""

    usuario_apertura_id: int
    inicial_bs: Decimal = Decimal(0)
    inicial_usd: Decimal = Decimal(0)
    fecha_apertura: str | None = None
    fecha_cierre: str | None = None
    usuario_cierre_id: int | None = None
    conteo_bs: Decimal | None = None
    conteo_usd: Decimal | None = None
    diferencia_bs: Decimal | None = None
    diferencia_usd: Decimal | None = None
    estado: str = ABIERTA
    id: int | None = None

    @property
    def abierta(self) -> bool:
        return self.estado == ABIERTA


@dataclass(frozen=True)
class LineaCierre:
    """RN-26. Un renglon del arqueo: lo esperado contra lo contado.

    `conteo` solo lo tienen los medios en efectivo: el resto no se cuenta en la
    gaveta, se concilia contra el banco.
    """

    medio: str
    moneda: str
    esperado: Decimal
    conteo: Decimal | None = None

    @property
    def diferencia(self) -> Decimal | None:
        """RN-26. conteo_fisico − esperado."""
        return None if self.conteo is None else self.conteo - self.esperado


@dataclass(frozen=True)
class ResumenCierre:
    """Lo que muestra la pantalla de cierre y queda en el reporte (RF-43)."""

    sesion: CajaSesion
    lineas: list[LineaCierre]
    ventas: int
    total_vendido_usd: Decimal

    def linea(self, medio: str, moneda: str) -> LineaCierre | None:
        for linea in self.lineas:
            if linea.medio == medio and linea.moneda == moneda:
                return linea
        return None
