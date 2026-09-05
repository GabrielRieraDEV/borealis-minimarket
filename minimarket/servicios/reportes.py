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
from datetime import date
from decimal import Decimal

from minimarket.datos.repositorios import caja as repo_caja
from minimarket.datos.repositorios import inventario as repo_inventario
from minimarket.datos.repositorios import reportes as repo_reportes
from minimarket.dominio.inventario import ExistenciaProducto, SaldoLoteProducto
from minimarket.dominio.reportes import (
    Equilibrio,
    FilaGanancia,
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
