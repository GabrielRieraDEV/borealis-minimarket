"""Entidades de compra y su aritmetica (RF-14 a RF-21, RN-06).

Capa de dominio: no importa `datos/`, `ui/` ni `infra/`.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from minimarket.dominio.dinero import DECIMALES_TOTAL, redondear
from minimarket.dominio.inventario import cantidad_unidades, costo_unitario

CONFIRMADA = "CONFIRMADA"
ANULADA = "ANULADA"


@dataclass
class Proveedor:
    """RF-14."""

    nombre: str
    rif: str | None = None
    telefono: str | None = None
    contacto: str | None = None
    activo: bool = True
    id: int | None = None


@dataclass
class LineaCompra:
    """RF-16 / RF-17. La presentacion se captura aca, no en la ficha.

    `fecha_vencimiento` solo se completa en productos con control de
    vencimiento (RF-21); el servicio crea el lote a partir de ella.
    """

    producto_id: int
    cant_presentacion: Decimal
    unid_x_presentacion: Decimal
    costo_present_usd: Decimal
    fecha_vencimiento: str | None = None
    lote_id: int | None = None
    id: int | None = None

    @property
    def cantidad_unidades(self) -> Decimal:
        return cantidad_unidades(self.cant_presentacion, self.unid_x_presentacion)

    @property
    def costo_unitario_usd(self) -> Decimal:
        """RN-06."""
        return costo_unitario(self.costo_present_usd, self.unid_x_presentacion)

    @property
    def total_usd(self) -> Decimal:
        return redondear(
            self.cant_presentacion * self.costo_present_usd, DECIMALES_TOTAL
        )


@dataclass
class Compra:
    """RF-15. Encabezado con su detalle; se confirma entera o no se registra."""

    proveedor_id: int
    fecha: str  # AAAA-MM-DD
    usuario_id: int
    numero_documento: str | None = None
    observacion: str | None = None
    lineas: list[LineaCompra] = field(default_factory=list)
    tasa_id: int | None = None
    total_usd: Decimal = Decimal(0)
    saldo_pendiente_usd: Decimal = Decimal(0)
    estado: str = CONFIRMADA
    creado_en: str | None = None
    id: int | None = None

    @property
    def total_calculado(self) -> Decimal:
        """Cada linea redondea a dos decimales y recien despues se suma."""
        return sum((linea.total_usd for linea in self.lineas), Decimal(0))


@dataclass(frozen=True)
class PagoProveedor:
    """RF-19. Pago parcial o total contra una compra."""

    compra_id: int
    fecha: str
    monto_usd: Decimal
    medio: str
    tasa_id: int | None = None
    referencia: str | None = None
    id: int | None = None
