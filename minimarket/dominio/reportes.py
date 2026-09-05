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


# --- Perdidas y gastos (RF-46, RF-53, RN-18, RN-29) -------------------------


@dataclass(frozen=True)
class GastoOperativo:
    """RF-46. `periodo` es el mes al que corresponde, en formato AAAA-MM.

    La fecha de carga y el periodo son cosas distintas: el alquiler de agosto
    se paga en septiembre y sigue siendo un gasto de agosto.
    """

    categoria: str
    descripcion: str
    monto_usd: Decimal
    periodo: str
    fecha: str
    usuario_id: int
    id: int | None = None


# `gasto_operativo.categoria`. La lista la fija el CHECK del esquema.
ALQUILER = "ALQUILER"
SERVICIOS = "SERVICIOS"
SUELDOS = "SUELDOS"
OTROS = "OTROS"
CATEGORIAS_GASTO = [ALQUILER, SERVICIOS, SUELDOS, OTROS]

# `gasto_recurrente.tipo`
FIJO = "FIJO"
PORCENTAJE = "PORCENTAJE"


@dataclass(frozen=True)
class GastoRecurrente:
    """Un gasto que se repite todos los meses sin volver a cargarlo (1.2.0).

    FIJO: `monto_usd` por mes (alquiler, sueldos). PORCENTAJE: `porcentaje` de
    lo cobrado en el mes por `medio` (o por todos si es None): la comision del
    punto de venta. Vigente desde `desde_periodo` hasta `hasta_periodo`
    inclusive; None es «sigue vigente».
    """

    categoria: str
    descripcion: str
    tipo: str
    desde_periodo: str
    usuario_id: int
    monto_usd: Decimal = Decimal(0)
    porcentaje: Decimal = Decimal(0)
    medio: str | None = None
    hasta_periodo: str | None = None
    id: int | None = None

    def vigente_en(self, periodo: str) -> bool:
        return self.desde_periodo <= periodo and (
            self.hasta_periodo is None or periodo <= self.hasta_periodo
        )

    def valuar(self, cobrado_por_medio: dict[str, Decimal]) -> Decimal:
        """Cuanto pesa este gasto en un mes, dado lo cobrado en ese mes."""
        if self.tipo == FIJO:
            return self.monto_usd
        base = (
            sum(cobrado_por_medio.values(), Decimal(0))
            if self.medio is None
            else cobrado_por_medio.get(self.medio, Decimal(0))
        )
        return redondear(base * self.porcentaje / 100, 2)


@dataclass(frozen=True)
class RenglonGasto:
    """Un gasto de un mes ya valuado, venga de donde venga, para la pantalla."""

    periodo: str
    categoria: str
    descripcion: str
    monto_usd: Decimal
    origen: str  # "cargado" | "fijo mensual" | "3 % de lo cobrado por punto"


@dataclass(frozen=True)
class FilaPerdida:
    """RF-53. Perdidas agrupadas por motivo en un periodo."""

    motivo_id: int
    motivo: str
    cantidad: Decimal
    costo_usd: Decimal


@dataclass(frozen=True)
class ResultadoPeriodo:
    """RF-47 / RN-29. La ganancia real, con todo lo que la come.

    `gastos_usd` NO se prorratea entre productos: se resta del resultado global
    del periodo, que es lo que la regla pide expresamente.
    """

    desde: str
    hasta: str
    ingreso_usd: Decimal  # base imponible + exento
    costo_usd: Decimal  # CMV (RN-27)
    perdidas_usd: Decimal  # RN-18
    gastos_usd: Decimal

    @property
    def ganancia_bruta_usd(self) -> Decimal:
        """RN-28. El IVA queda afuera: no es ingreso del negocio."""
        return self.ingreso_usd - self.costo_usd

    @property
    def ganancia_real_usd(self) -> Decimal:
        """RN-29."""
        return self.ganancia_bruta_usd - self.perdidas_usd - self.gastos_usd

    @property
    def margen_real_pct(self) -> Decimal | None:
        if self.ingreso_usd == 0:
            return None
        return redondear(
            self.ganancia_real_usd / self.ingreso_usd * 100, DECIMALES_PORCENTAJE
        )


@dataclass(frozen=True)
class Equilibrio:
    """¿Los margenes puestos alcanzan para pagar los gastos del mes?

    Pedido del cliente despues de la entrega. RN-29 responde DESPUES de cerrar
    el mes; esto responde durante: con lo vendido hasta hoy y su margen, al
    mismo ritmo, ¿el mes cierra cubriendo los gastos? Y si no, ¿cuanto mas hay
    que vender, o a que margen hay que llevar los precios?

    `resultado` es el del 1 del mes a hoy. Sus gastos son los del mes entero,
    porque RN-29 no prorratea: el alquiler de septiembre se debe completo
    aunque sea 4 de septiembre. Lo que se proyecta es lo que las ventas
    dejan (ganancia bruta menos perdidas), no los gastos.

    La proyeccion es lineal, dias transcurridos contra dias del mes. Un
    minimarket vende parecido todos los dias; si un dia cambia el ritmo, el
    numero se mueve solo al dia siguiente.
    """

    resultado: ResultadoPeriodo
    dias_transcurridos: int
    dias_del_mes: int

    @property
    def contribucion_usd(self) -> Decimal:
        """Lo que las ventas dejaron para pagar gastos: bruta menos perdidas."""
        return self.resultado.ganancia_bruta_usd - self.resultado.perdidas_usd

    @property
    def margen_bruto_pct(self) -> Decimal | None:
        """Cuanto de cada dolar vendido queda para gastos y ganancia."""
        if self.resultado.ingreso_usd <= 0:
            return None
        return redondear(
            self.contribucion_usd / self.resultado.ingreso_usd * 100,
            DECIMALES_PORCENTAJE,
        )

    def _proyectar(self, monto: Decimal) -> Decimal:
        return redondear(monto / self.dias_transcurridos * self.dias_del_mes, 2)

    @property
    def ingreso_proyectado_usd(self) -> Decimal:
        return self._proyectar(self.resultado.ingreso_usd)

    @property
    def contribucion_proyectada_usd(self) -> Decimal:
        return self._proyectar(self.contribucion_usd)

    @property
    def resultado_proyectado_usd(self) -> Decimal:
        """Con lo que va del mes, asi cerraria. Negativo: no cubre."""
        return self.contribucion_proyectada_usd - self.resultado.gastos_usd

    @property
    def cubre(self) -> bool:
        return self.resultado_proyectado_usd >= 0

    @property
    def ventas_necesarias_usd(self) -> Decimal | None:
        """Cuanto hay que vender en el mes, con el margen actual, para empatar."""
        margen = self.margen_bruto_pct
        if margen is None or margen <= 0:
            return None
        return redondear(self.resultado.gastos_usd / margen * 100, 2)

    @property
    def margen_necesario_pct(self) -> Decimal | None:
        """A que margen bruto hay que llevar los precios, vendiendo lo mismo."""
        if self.ingreso_proyectado_usd <= 0:
            return None
        return redondear(
            self.resultado.gastos_usd / self.ingreso_proyectado_usd * 100,
            DECIMALES_PORCENTAJE,
        )


@dataclass(frozen=True)
class MargenSugerido:
    """A que margen vender para que las ventas paguen los gastos y dejen ganancia.

    Pedido del cliente (1.2.0): es un negocio nuevo y no sabe que margen poner.
    Lo que el sistema SI puede calcular es el piso: con estas ventas y estos
    gastos, debajo de tal margen se pierde plata. Y ese piso baja solo cuando
    el volumen sube, que es lo que el cliente intuye («compro poco, margen
    alto; cuando venda mas, bajo el margen»).

    Lo que el sistema NO sabe es que la harina tiene que ir mas barata que la
    mayonesa para competir. Eso lo sabe el dueno y ya tiene donde decirlo (el
    margen objetivo por categoria y por producto). El sugerido se aplica como
    piso a lo que este por debajo; lo que el dueno puso mas alto se respeta.

    Todo sobre ventas sin IVA. `tasa_variable` es la fraccion de las ventas
    que se van en gastos por porcentaje (comisiones), ya valuadas.
    """

    ventas_mes_usd: Decimal
    gastos_fijos_usd: Decimal
    tasa_variable: Decimal  # fraccion, 0.018 = 1,8 % de las ventas
    ganancia_pct: Decimal  # sobre ventas, la que el dueno quiere
    origen_ventas: str  # "real" | "proyectado" | "esperado"
    dias_de_ventas: int = 0

    def _margen_sobre_costo(self, sobre_ventas: Decimal) -> Decimal | None:
        """RN-08 mide el margen sobre el costo; el piso sale sobre ventas.

        Si de cada dolar vendido tiene que quedar `s` para gastos y ganancia,
        el costo es (1 - s) y el margen sobre ese costo es s / (1 - s).
        Con s >= 1 no hay margen que alcance: los gastos superan las ventas.
        """
        if sobre_ventas >= 1:
            return None
        return redondear(
            sobre_ventas / (1 - sobre_ventas) * 100, DECIMALES_PORCENTAJE
        )

    def _sobre_ventas(self, ventas: Decimal, con_ganancia: bool) -> Decimal:
        if ventas <= 0:
            return Decimal(1)
        fraccion = self.gastos_fijos_usd / ventas + self.tasa_variable
        if con_ganancia:
            fraccion += self.ganancia_pct / 100
        return fraccion

    @property
    def piso_pct(self) -> Decimal | None:
        """Debajo de esto se pierde plata, aunque se venda lo mismo."""
        return self._margen_sobre_costo(
            self._sobre_ventas(self.ventas_mes_usd, con_ganancia=False)
        )

    @property
    def sugerido_pct(self) -> Decimal | None:
        """El piso mas la ganancia que el dueno quiere."""
        return self._margen_sobre_costo(
            self._sobre_ventas(self.ventas_mes_usd, con_ganancia=True)
        )

    def sugerido_si_vendiera(self, ventas_mes_usd: Decimal) -> Decimal | None:
        """El mismo sugerido con otro volumen: para mostrar que baja al vender mas."""
        return self._margen_sobre_costo(
            self._sobre_ventas(ventas_mes_usd, con_ganancia=True)
        )


@dataclass(frozen=True)
class ProductoVendido:
    """Una linea de la venta del dia: que se vendio y cuanto."""

    producto_id: int
    nombre: str
    cantidad: Decimal
    total_usd: Decimal


@dataclass(frozen=True)
class VentaDelDia:
    """Pedido del cliente (1.2.0): «se vendieron tantas harinas y son 23 de
    pago movil». Los productos y lo cobrado por cada medio, de un dia o de
    una sesion de caja."""

    titulo: str
    productos: list[ProductoVendido]
    por_medio: list[TotalPorMedio]
    ventas: int
    total_usd: Decimal


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
