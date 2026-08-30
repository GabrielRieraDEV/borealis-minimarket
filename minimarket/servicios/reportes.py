"""Reportes del negocio (RF-48 a RF-52).

Ninguno de estos numeros se recalcula con datos de hoy: la ganancia usa el
costo congelado en cada linea de venta (RN-19, RN-27) y el libro de ventas usa
la tasa de cada operacion (RN-31). Cambiar un costo o cargar la tasa de manana
no puede mover un reporte de ayer.

El cajero no ve ganancias ni costos (RF-58); lo unico que le queda es el cierre
de su propia sesion.
"""

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from minimarket.datos.repositorios import caja as repo_caja
from minimarket.datos.repositorios import inventario as repo_inventario
from minimarket.datos.repositorios import reportes as repo_reportes
from minimarket.dominio.inventario import ExistenciaProducto
from minimarket.dominio.reportes import (
    FilaGanancia,
    Libro,
    ResumenVentas,
)
from minimarket.dominio.usuario import (
    REPORTE_CIERRE,
    REPORTES_GANANCIA,
    VER_REPORTES,
)
from minimarket.dominio.venta import ResumenCierre
from minimarket.servicios import ErrorServicio, caja, usuario_actual
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
