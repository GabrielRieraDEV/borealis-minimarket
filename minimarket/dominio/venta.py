"""Entidades y aritmetica de la venta y de la caja (RN-19 a RN-26).

Capa de dominio: no importa `datos/`, `ui/` ni `infra/`.

Cada linea calcula su total, lo redondea a dos decimales y recien despues se
suma (RN-20). El IVA NO se recalcula sobre el total del documento: conviven
productos exentos y gravados y el resultado diferiria de la suma de las partes.

Bolivares (1.4.0): el total en Bs NO es el total en USD por la tasa. Es la suma
de precio al publico (RN-10) × cantidad, lo mismo que dice el anaquel. Con la
tasa en 842, un centavo de dolar son 8,42 Bs, y convertir el total ya
redondeado a centavos cobraba 1.398,06 por un cafe exhibido a 1.400. Por eso
el cobro mide cada pago en su moneda (`_cobertura`).

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
# En que puede salir el vuelto (RN-23): por punto no se devuelve nada.
MEDIOS_VUELTO = [EFECTIVO, PAGO_MOVIL, TRANSFERENCIA]

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

    def precio_unit_bs(self, tasa: Decimal, multiplo: Decimal = Decimal(1)) -> Decimal:
        """RN-03 + RN-10. El precio al publico, el mismo de la ficha del producto."""
        return redondear_comercial(convertir_a_bs(self.precio_unit_usd, tasa), multiplo)

    def total_linea_bs(self, tasa: Decimal, multiplo: Decimal = Decimal(1)) -> Decimal:
        """Precio al publico × cantidad: dos cafes de 1.400 son 2.800."""
        return redondear(self.cantidad * self.precio_unit_bs(tasa, multiplo), DECIMALES_TOTAL)

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

    def monto_bs(self, tasa: Decimal) -> Decimal:
        return self.monto if self.moneda == BS else convertir_a_bs(self.monto, tasa)


@dataclass
class Vuelto:
    """RN-23 (1.3.0). En que salio el vuelto: la moneda la indica el cajero.

    Efectivo en bolivares, efectivo en dolares, o pago movil / transferencia
    cuando el cliente paga con un billete grande y el vuelto se le manda.
    `monto` va en la moneda entregada; `monto_usd` es lo que vale a la tasa
    de la venta, y la suma de todos los vueltos tiene que dar `vuelto_usd`.
    """

    medio: str
    moneda: str
    monto: Decimal
    monto_usd: Decimal
    id: int | None = None

    @property
    def es_efectivo(self) -> bool:
        return self.medio == EFECTIVO

    def monto_bs(self, tasa: Decimal) -> Decimal:
        return self.monto if self.moneda == BS else convertir_a_bs(self.monto, tasa)


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
    vueltos: list[Vuelto] = field(default_factory=list)  # vacio: efectivo Bs
    multiplo: Decimal = Decimal(1)  # RN-10 del dia: arma el total en Bs
    total_bs_guardado: Decimal | None = None  # el de la base, si ya se registro
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
        """Suma de precio al publico × cantidad, a la tasa de la venta.

        Una venta ya registrada devuelve lo que se guardo: las anteriores a
        1.4.0 guardaron total_usd × tasa y asi tienen que seguir diciendo.
        """
        if self.total_bs_guardado is not None:
            return self.total_bs_guardado
        return sum(
            (linea.total_linea_bs(self.tasa, self.multiplo) for linea in self.lineas),
            Decimal(0),
        )

    @property
    def ganancia_usd(self) -> Decimal:
        """RN-19. Con los costos congelados en cada linea."""
        return sum((linea.ganancia_usd for linea in self.lineas), Decimal(0))

    # --- Cobro (RN-22, RN-23) ----------------------------------------------

    def _cobertura(self) -> tuple[Decimal, Decimal, Decimal]:
        """RN-22 / RN-23 (1.4.0): (falta en Bs, falta en USD, vuelto en Bs), sin redondear.

        Cada pago cubre la venta en su moneda: los bolivares contra el total en
        Bs y los dolares contra el total en USD. Quien paga 1.400 Bs o 1,66 USD
        por el cafe paga justo, y 1 USD paga una harina de 1 USD aunque al
        publico diga 843 Bs. Primero cuentan los bolivares; lo que falte se
        cubre en proporcion con dolares, y lo que sobre de ellos se devuelve a
        la tasa. Se compara multiplicando en cruz: dividir primero dejaria
        1,66 USD a una diezmillonesima de alcanzar.
        """
        total_bs, total_usd = self.total_bs, self.total_usd
        pagado_bs = sum((p.monto for p in self.pagos if p.moneda == BS), Decimal(0))
        pagado_usd = sum((p.monto for p in self.pagos if p.moneda == USD), Decimal(0))
        cero = Decimal(0)
        if pagado_bs >= total_bs:
            return cero, cero, pagado_bs - total_bs + pagado_usd * self.tasa
        faltan_bs = total_bs - pagado_bs
        # Todo en «dolares × total_bs», para no dividir hasta el final.
        cubierto, necesario = pagado_usd * total_bs, faltan_bs * total_usd
        if cubierto >= necesario:
            return cero, cero, (cubierto - necesario) / total_bs * self.tasa
        resto_usd = (necesario - cubierto) / total_bs
        return (necesario - cubierto) / total_usd, resto_usd, cero

    @property
    def falta_bs(self) -> Decimal:
        """Lo que resta cobrar si se paga en bolivares; cero si ya alcanza (RN-22)."""
        return redondear(self._cobertura()[0], DECIMALES_TOTAL)

    @property
    def falta_usd(self) -> Decimal:
        """Lo mismo si se paga en dolares, al centavo de arriba para que alcance."""
        return redondear_comercial(self._cobertura()[1], Decimal("0.01"))

    @property
    def vuelto_bs(self) -> Decimal:
        """RN-23. Lo que hay que devolver, en bolivares exactos, sin el sencillo."""
        return redondear(self._cobertura()[2], DECIMALES_TOTAL)

    @property
    def vuelto_usd(self) -> Decimal:
        """RN-23. El vuelto en dolares a la tasa; es lo que se guarda en la venta."""
        return equivalente_usd(self.vuelto_bs, BS, self.tasa)

    @property
    def vuelto_admisible(self) -> bool:
        """RN-23. Un excedente por punto o transferencia no se devuelve."""
        efectivo = sum((p.monto_bs(self.tasa) for p in self.pagos if p.es_efectivo), Decimal(0))
        return self.vuelto_bs <= efectivo

    def vuelto_en_efectivo_bs(self, resto: Decimal | None = None) -> Vuelto:
        """RN-23 + RN-10. Efectivo en bolivares, redondeado al sencillo.

        Sin `resto`, es todo el vuelto: asi salio siempre antes de 1.3.0.
        """
        resto = self.vuelto_bs if resto is None else resto
        return Vuelto(
            medio=EFECTIVO,
            moneda=BS,
            monto=redondear_comercial(resto, self.multiplo),
            monto_usd=equivalente_usd(resto, BS, self.tasa),
        )

    def vuelto_declarado(self, medio: str, moneda: str, monto: Decimal) -> Vuelto:
        """Una parte del vuelto que el cajero entrega por un medio concreto.

        «10 USD en efectivo y el resto en bolivares»: esta es la parte de los
        10 USD. El equivalente en dolares sale a la tasa de la venta (RN-22).
        """
        return Vuelto(
            medio=medio,
            moneda=moneda,
            monto=monto,
            monto_usd=equivalente_usd(monto, moneda, self.tasa),
        )

    @property
    def vuelto_declarado_bs(self) -> Decimal:
        return sum((v.monto_bs(self.tasa) for v in self.vueltos), Decimal(0))

    @property
    def vuelto_por_declarar_bs(self) -> Decimal:
        """Lo que falta repartir; sale en efectivo en Bs si nadie dice otra cosa."""
        return self.vuelto_bs - self.vuelto_declarado_bs

    def completar_vuelto(self) -> None:
        """RN-23. Lo no declarado sale en efectivo en bolivares, redondeado."""
        resto = self.vuelto_por_declarar_bs
        if resto > 0:
            self.vueltos.append(self.vuelto_en_efectivo_bs(resto))

    @property
    def vuelto_cuadra(self) -> bool:
        """Los vueltos suman el vuelto de la venta.

        El efectivo en Bs se redondea hacia arriba (RN-10), asi que puede pasar
        por menos de un multiplo; nada mas.
        """
        diferencia = self.vuelto_declarado_bs - self.vuelto_bs
        hay_sencillo = any(v.es_efectivo and v.moneda == BS for v in self.vueltos)
        return diferencia == 0 or (hay_sencillo and 0 < diferencia < self.multiplo)


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
