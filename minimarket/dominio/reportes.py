"""Filas y totales de los reportes (RN-27, RN-28, RN-30, RN-31).

Capa de dominio: no importa `datos/`, `ui/` ni `infra/`. El repositorio arma
estas filas con los importes en dolares y la tasa de cada operacion; la
conversion a bolivares y los porcentajes se calculan aca, una sola vez, y los
usan igual la pantalla y el PDF.
"""

from dataclasses import dataclass
from decimal import Decimal

from minimarket.dominio.dinero import (
    DECIMALES_PORCENTAJE,
    convertir_a_bs,
    redondear,
)

# --- Ventas del periodo (RF-48) ---------------------------------------------


@dataclass(frozen=True)
class TotalPorMedio:
    """RF-48. Lo cobrado por cada medio, en su moneda y en dolares."""

    medio: str
    moneda: str
    monto: Decimal
    monto_usd: Decimal


@dataclass(frozen=True)
class ResumenVentas:
    """RF-48. Las ventas anuladas no entran (RN-25)."""

    desde: str
    hasta: str
    cantidad: int
    exento_usd: Decimal
    base_imponible_usd: Decimal
    iva_usd: Decimal
    total_usd: Decimal
    por_medio: list[TotalPorMedio]


# --- Ganancia (RF-50, RN-27, RN-28) -----------------------------------------


@dataclass(frozen=True)
class FilaGanancia:
    """RN-27 / RN-28. Por producto o por categoria, segun quien la arme.

    `ingreso_usd` es base imponible + exento: el IVA se excluye porque no es
    ingreso del negocio. `costo_usd` es el CMV con el costo congelado en cada
    linea de venta (RN-19), no el costo de hoy.
    """

    id: int
    nombre: str
    cantidad: Decimal
    ingreso_usd: Decimal
    costo_usd: Decimal
    lineas_sin_costo: int = 0

    @property
    def ganancia_usd(self) -> Decimal:
        """RN-28."""
        return self.ingreso_usd - self.costo_usd

    @property
    def determinable(self) -> bool:
        """Caso limite: producto vendido antes de registrar su primera compra.

        Sin costo no hay ganancia que informar; se muestra como no
        determinable en vez de contar la venta entera como utilidad.
        """
        return self.lineas_sin_costo == 0

    @property
    def margen_pct(self) -> Decimal | None:
        """Ganancia sobre el ingreso. None si no hay con que calcularla."""
        if not self.determinable or self.ingreso_usd == 0:
            return None
        return redondear(
            self.ganancia_usd / self.ingreso_usd * 100, DECIMALES_PORCENTAJE
        )


# --- Libro de ventas (RF-52, RN-31) -----------------------------------------

# El formato definitivo lo confirma el contador del cliente (clausula 6.7 del
# contrato). Las reglas de calculo no cambian; la disposicion de las columnas
# se ajusta ACA y la siguen la pantalla y el PDF sin tocar nada mas.
COLUMNAS_LIBRO: list[tuple[str, str, int]] = [
    ("Fecha", "fecha", 0),
    ("Numero", "numero", 0),
    ("Cliente", "razon_social", 0),
    ("RIF", "rif", 0),
    ("Tasa", "tasa", 6),
    ("Exento Bs", "exento_bs", 2),
    ("Base imponible Bs", "base_imponible_bs", 2),
    ("IVA Bs", "iva_bs", 2),
    ("Total Bs", "total_bs", 2),
    ("Condicion", "condicion", 0),
]


@dataclass(frozen=True)
class FilaLibro:
    """RN-31. Una venta del libro, en bolivares a SU tasa, no a la de hoy."""

    fecha: str
    numero: int
    razon_social: str
    rif: str
    tasa: Decimal
    exento_usd: Decimal
    base_imponible_usd: Decimal
    iva_usd: Decimal
    anulada: bool = False

    def _bs(self, monto_usd: Decimal) -> Decimal:
        """RN-31. La anulada figura con importes en cero, pero figura."""
        return Decimal(0) if self.anulada else convertir_a_bs(monto_usd, self.tasa)

    @property
    def exento_bs(self) -> Decimal:
        return self._bs(self.exento_usd)

    @property
    def base_imponible_bs(self) -> Decimal:
        return self._bs(self.base_imponible_usd)

    @property
    def iva_bs(self) -> Decimal:
        return self._bs(self.iva_usd)

    @property
    def total_bs(self) -> Decimal:
        """Suma de las tres partes ya convertidas, para que la fila cierre.

        Convertir el total por separado podria diferir en un centimo del
        exento + base + IVA que declara la misma linea.
        """
        return self.exento_bs + self.base_imponible_bs + self.iva_bs

    @property
    def condicion(self) -> str:
        return "ANULADA" if self.anulada else ""


@dataclass(frozen=True)
class TotalesLibro:
    """Un subtotal del libro: de una fecha o de todo el periodo."""

    etiqueta: str
    exento_bs: Decimal
    base_imponible_bs: Decimal
    iva_bs: Decimal

    @property
    def total_bs(self) -> Decimal:
        return self.exento_bs + self.base_imponible_bs + self.iva_bs


@dataclass(frozen=True)
class Libro:
    """RF-52 / RN-31. Las filas vienen ordenadas por fecha y numero."""

    desde: str
    hasta: str
    filas: list[FilaLibro]

    def _sumar(self, etiqueta: str, filas: list[FilaLibro]) -> TotalesLibro:
        return TotalesLibro(
            etiqueta=etiqueta,
            exento_bs=sum((f.exento_bs for f in filas), Decimal(0)),
            base_imponible_bs=sum((f.base_imponible_bs for f in filas), Decimal(0)),
            iva_bs=sum((f.iva_bs for f in filas), Decimal(0)),
        )

    def por_fecha(self) -> list[TotalesLibro]:
        """RN-31. El libro agrupa por fecha; esto es esa agrupacion."""
        fechas: dict[str, list[FilaLibro]] = {}
        for fila in self.filas:
            fechas.setdefault(fila.fecha, []).append(fila)
        return [self._sumar(fecha, filas) for fecha, filas in fechas.items()]

    @property
    def totales(self) -> TotalesLibro:
        return self._sumar(f"{self.desde} a {self.hasta}", self.filas)
