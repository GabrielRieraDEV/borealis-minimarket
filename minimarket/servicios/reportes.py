"""Reportes del negocio (RF-48 a RF-52).

Ninguno de estos numeros se recalcula con datos de hoy: la ganancia usa el
costo congelado en cada linea de venta (RN-19, RN-27) y el libro de ventas usa
la tasa de cada operacion (RN-31). Cambiar un costo o cargar la tasa de manana
no puede mover un reporte de ayer.

El cajero no ve ganancias ni costos (RF-58); lo unico que le queda es el cierre
de su propia sesion.
"""

import calendar
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from minimarket.datos.repositorios import caja as repo_caja
from minimarket.datos.repositorios import configuracion as repo_configuracion
from minimarket.datos.repositorios import inventario as repo_inventario
from minimarket.datos.repositorios import reportes as repo_reportes
from minimarket.dominio.dinero import redondear
from minimarket.dominio.inventario import ExistenciaProducto, SaldoLoteProducto
from minimarket.dominio.reportes import (
    Equilibrio,
    FilaGanancia,
    MargenSugerido,
    VentaDelDia,
    FilaPerdida,
    Libro,
    ResultadoPeriodo,
    ResumenVentas,
)
from minimarket.dominio.usuario import (
    REPORTE_CIERRE,
    REPORTES_GANANCIA,
    VER_EXISTENCIAS,
    VER_REPORTES,
)
from minimarket.dominio.venta import ResumenCierre
from minimarket.servicios import ErrorServicio, caja, usuario_actual
from minimarket.servicios import gastos as servicio_gastos
from minimarket.servicios import perdidas as servicio_perdidas
from minimarket.servicios import tasa as servicio_tasa
from minimarket.servicios import usuarios as servicio_usuarios


class ErrorReporte(ErrorServicio):
    """Falla previsible, con mensaje listo para mostrar en pantalla."""


@dataclass(frozen=True)
class InventarioValorizado:
    """RF-49 / RN-30. El detalle y su total."""

    filas: list[ExistenciaProducto]

    @property
    def total_usd(self) -> Decimal:
        return sum((f.valorizacion for f in self.filas), Decimal(0))


def ventas_por_periodo(
    conexion: sqlite3.Connection, desde: str, hasta: str
) -> ResumenVentas:
    """RF-48. Totales del periodo con el desglose por medio de pago."""
    servicio_usuarios.exigir(conexion, VER_REPORTES)
    _validar_rango(desde, hasta)
    return repo_reportes.resumen_ventas(conexion, desde, hasta)


def inventario_valorizado(conexion: sqlite3.Connection) -> InventarioValorizado:
    """RF-49 / RN-30. Existencia por ultimo costo, sin los productos en cero."""
    servicio_usuarios.exigir(conexion, VER_REPORTES)
    filas = repo_inventario.existencias(conexion, limite=1_000_000)
    return InventarioValorizado([f for f in filas if f.existencia != 0])


def ganancia_por_producto(
    conexion: sqlite3.Connection, desde: str, hasta: str
) -> list[FilaGanancia]:
    """RF-50 / RN-27 / RN-28."""
    servicio_usuarios.exigir(conexion, REPORTES_GANANCIA)
    _validar_rango(desde, hasta)
    return repo_reportes.ganancia_por_producto(conexion, desde, hasta)


def ganancia_por_categoria(
    conexion: sqlite3.Connection, desde: str, hasta: str
) -> list[FilaGanancia]:
    """RF-50. La categoria es la que tiene el producto hoy, no la de la venta.

    `venta_detalle` congela precio, alicuota y costo, no la categoria: una
    recategorizacion mueve el producto de renglon en los reportes viejos. Es lo
    que se espera de un reporte por categoria, y lo que igual da la suma total.
    """
    servicio_usuarios.exigir(conexion, REPORTES_GANANCIA)
    _validar_rango(desde, hasta)
    return repo_reportes.ganancia_por_categoria(conexion, desde, hasta)


def libro_de_ventas(conexion: sqlite3.Connection, desde: str, hasta: str) -> Libro:
    """RF-52 / RN-31. Incluye las anuladas, en cero y marcadas como tales."""
    servicio_usuarios.exigir(conexion, VER_REPORTES)
    _validar_rango(desde, hasta)
    return Libro(desde, hasta, repo_reportes.libro_de_ventas(conexion, desde, hasta))


def perdidas_por_motivo(
    conexion: sqlite3.Connection, desde: str, hasta: str
) -> list[FilaPerdida]:
    """RF-53 / RN-18. Valorizadas al costo vigente en la fecha de cada baja."""
    servicio_usuarios.exigir(conexion, REPORTES_GANANCIA)
    _validar_rango(desde, hasta)
    return repo_reportes.perdidas_por_motivo(conexion, desde, hasta)


def proximos_a_vencer(
    conexion: sqlite3.Connection, hoy: str | None = None
) -> list[SaldoLoteProducto]:
    """RF-54 / RN-17. Lotes con existencia dentro del plazo de aviso.

    Se pide con `VER_EXISTENCIAS` y no con `VER_REPORTES`: quien atiende el
    mostrador tiene que poder ver que se le esta por vencer. La valorizacion
    de cada lote va aparte, en el reporte de perdidas.
    """
    servicio_usuarios.exigir(conexion, VER_EXISTENCIAS)
    return servicio_perdidas.proximos_a_vencer(conexion, hoy)


def ganancia_real(
    conexion: sqlite3.Connection, desde: str, hasta: str
) -> ResultadoPeriodo:
    """RF-47 / RF-55 / RN-29. Lo que queda despues de perdidas y gastos."""
    servicio_usuarios.exigir(conexion, REPORTES_GANANCIA)
    _validar_rango(desde, hasta)
    ingreso, costo = repo_reportes.ingreso_y_cmv(conexion, desde, hasta)
    return ResultadoPeriodo(
        desde=desde,
        hasta=hasta,
        ingreso_usd=ingreso,
        costo_usd=costo,
        perdidas_usd=repo_reportes.total_perdidas(conexion, desde, hasta),
        gastos_usd=servicio_gastos.total(conexion, desde, hasta),
    )


def equilibrio_del_mes(
    conexion: sqlite3.Connection, hoy: str | None = None
) -> Equilibrio:
    """Con lo vendido hasta hoy, ¿el mes cierra cubriendo los gastos?

    Es RN-29 del 1 del mes a hoy, mas los dias para proyectar. Los gastos
    salen del mes entero por la propia regla (no se prorratean).
    """
    hoy = hoy or servicio_tasa.hoy()
    fecha = date.fromisoformat(hoy)
    return Equilibrio(
        resultado=ganancia_real(conexion, hoy[:8] + "01", hoy),
        dias_transcurridos=fecha.day,
        dias_del_mes=calendar.monthrange(fecha.year, fecha.month)[1],
    )


DIAS_REFERENCIA = 30


def margen_sugerido(
    conexion: sqlite3.Connection, hoy: str | None = None
) -> MargenSugerido | None:
    """A que margen vender para pagar los gastos y ganar (1.2.0).

    El volumen de referencia son las ventas de los ultimos 30 dias. Si el
    negocio tiene menos de 30 dias vendiendo, se proyectan a 30 desde la
    primera venta. Sin ventas, se usan las «ventas esperadas» de la
    configuracion, si el dueno las cargo. Sin nada de eso, no hay sugerencia:
    devolver un margen inventado seria peor que no devolver ninguno.

    Los porcentuales (comisiones) entran como fraccion de las ventas, asi que
    no dependen del volumen; los fijos si, y por eso el sugerido baja cuando
    el negocio vende mas.
    """
    servicio_usuarios.exigir(conexion, REPORTES_GANANCIA)
    hoy = hoy or servicio_tasa.hoy()
    fecha = date.fromisoformat(hoy)
    desde = (fecha - timedelta(days=DIAS_REFERENCIA - 1)).isoformat()
    ingreso, _ = repo_reportes.ingreso_y_cmv(conexion, desde, hoy)
    primera = repo_reportes.primera_venta(conexion)

    if ingreso > 0 and primera is not None:
        dias = min(DIAS_REFERENCIA, (fecha - date.fromisoformat(primera)).days + 1)
        if dias >= DIAS_REFERENCIA:
            ventas, origen = ingreso, "real"
        else:
            ventas = redondear(ingreso / dias * DIAS_REFERENCIA, 2)
            origen = "proyectado"
    else:
        dias = 0
        ventas = repo_configuracion.leer_decimal(
            conexion, "equilibrio.ventas_esperadas_usd", Decimal(0)
        )
        origen = "esperado"
        if ventas <= 0:
            return None

    fijos, porcentuales = servicio_gastos.gastos_del_mes_para_margen(conexion, hoy[:7])
    # Cada porcentual pesa sobre lo cobrado por su medio. Se reparte segun el
    # peso real de cada medio en el periodo de referencia; sin historial, se
    # asume que todo se cobra por ese medio (peor caso, margen mas prudente).
    cobrado = {}
    for linea in repo_reportes.totales_por_medio(conexion, desde, hoy):
        cobrado[linea.medio] = cobrado.get(linea.medio, Decimal(0)) + linea.monto_usd
    total_cobrado = sum(cobrado.values(), Decimal(0))
    tasa_variable = Decimal(0)
    for gasto in porcentuales:
        if gasto.medio is None or total_cobrado <= 0:
            peso = Decimal(1)
        else:
            peso = cobrado.get(gasto.medio, Decimal(0)) / total_cobrado
        tasa_variable += gasto.porcentaje / 100 * peso

    return MargenSugerido(
        ventas_mes_usd=ventas,
        gastos_fijos_usd=fijos,
        tasa_variable=tasa_variable,
        ganancia_pct=repo_configuracion.leer_decimal(
            conexion, "equilibrio.ganancia_pct", Decimal(10)
        ),
        origen_ventas=origen,
        dias_de_ventas=dias,
    )


def ventas_del_dia(conexion: sqlite3.Connection, fecha: str) -> VentaDelDia:
    """Que se vendio y por que medio se cobro, en un dia (1.2.0)."""
    servicio_usuarios.exigir(conexion, VER_REPORTES)
    _validar_rango(fecha, fecha)
    resumen = repo_reportes.resumen_ventas(conexion, fecha, fecha)
    return VentaDelDia(
        titulo=f"Ventas del {fecha}",
        productos=repo_reportes.productos_vendidos(conexion, fecha, fecha),
        por_medio=resumen.por_medio,
        ventas=resumen.cantidad,
        total_usd=resumen.total_usd,
    )


def resumen_de_sesion(conexion: sqlite3.Connection, sesion_id: int) -> VentaDelDia:
    """Lo mismo, para la sesion de caja: lo ve el cajero al cerrar la suya."""
    servicio_usuarios.exigir(conexion, REPORTE_CIERRE)
    sesion = repo_caja.obtener(conexion, sesion_id)
    if sesion is None:
        raise ErrorReporte("La sesion de caja no existe.")
    if not servicio_usuarios.tiene_permiso(conexion, REPORTES_GANANCIA):
        if sesion.usuario_apertura_id != usuario_actual():
            raise servicio_usuarios.ErrorPermiso(
                "Solo se puede consultar el cierre de la caja propia."
            )
    ventas, total = repo_reportes.ventas_de_sesion(conexion, sesion_id)
    return VentaDelDia(
        titulo=f"Caja #{sesion_id}",
        productos=repo_reportes.productos_vendidos(conexion, sesion_id=sesion_id),
        por_medio=repo_reportes.totales_por_medio(conexion, sesion_id=sesion_id),
        ventas=ventas,
        total_usd=total,
    )


def cierre_de_caja(conexion: sqlite3.Connection, sesion_id: int) -> ResumenCierre:
    """RF-51. El cajero ve el cierre de SU sesion; el administrador, cualquiera."""
    servicio_usuarios.exigir(conexion, REPORTE_CIERRE)
    sesion = repo_caja.obtener(conexion, sesion_id)
    if sesion is None:
        raise ErrorReporte("La sesion de caja no existe.")
    if not servicio_usuarios.tiene_permiso(conexion, REPORTES_GANANCIA):
        # Sin permiso de administrador, solo la sesion propia (seccion 6).
        if sesion.usuario_apertura_id != usuario_actual():
            raise servicio_usuarios.ErrorPermiso(
                "Solo se puede consultar el cierre de la caja propia."
            )
    return caja.arqueo(conexion, sesion_id, sesion.conteo_bs, sesion.conteo_usd)


def sesiones(conexion: sqlite3.Connection, limite: int = 60):
    """RF-51. Las sesiones que se pueden elegir para el reporte de cierre."""
    servicio_usuarios.exigir(conexion, REPORTE_CIERRE)
    todas = repo_caja.listar(conexion, limite=limite)
    if servicio_usuarios.tiene_permiso(conexion, REPORTES_GANANCIA):
        return todas
    propio = usuario_actual()
    return [s for s in todas if s.usuario_apertura_id == propio]


def _validar_rango(desde: str, hasta: str) -> None:
    if not desde or not hasta:
        raise ErrorReporte("Indica la fecha de inicio y la de fin del periodo.")
    if desde > hasta:
        raise ErrorReporte("La fecha de inicio no puede ser posterior a la de fin.")
