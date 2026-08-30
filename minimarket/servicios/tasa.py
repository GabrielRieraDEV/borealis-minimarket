"""Casos de uso de la tasa de cambio (RF-09 a RF-13).

La tasa se carga a mano o se consulta al BCV. Si la consulta falla no se
bloquea nada: se pide la carga manual y no se hereda la tasa de ayer (RN-04).
"""

import logging
import sqlite3
from datetime import date
from decimal import Decimal

from minimarket.datos.conexion import transaccion
from minimarket.datos.repositorios import configuracion as repo_configuracion
from minimarket.datos.repositorios import tasa as repo_tasa
from minimarket.dominio.tasa import BCV_AUTO, MANUAL, TasaCambio

_bitacora = logging.getLogger(__name__)


class ErrorTasa(Exception):
    """Falla previsible, con mensaje listo para mostrar en pantalla."""


def hoy() -> str:
    """Fecha local en ISO 8601 (RNF-14)."""
    return date.today().isoformat()


def tasa_del_dia(
    conexion: sqlite3.Connection, fecha: str | None = None
) -> Decimal | None:
    """RF-12. La tasa de la fecha, o None si todavia no se cargo."""
    registro = repo_tasa.obtener(conexion, fecha or hoy())
    return registro.valor if registro else None


def exigir_tasa(conexion: sqlite3.Connection, fecha: str | None = None) -> Decimal:
    """RF-12 / RN-03. Sin tasa del dia no se abre caja ni se vende."""
    valor = tasa_del_dia(conexion, fecha)
    if valor is None:
        raise ErrorTasa(
            "No hay tasa de cambio cargada para hoy. "
            "Cargala antes de abrir la caja o registrar ventas."
        )
    return valor


def registrar_manual(
    conexion: sqlite3.Connection,
    valor: Decimal,
    fecha: str | None = None,
    usuario_id: int | None = None,
) -> None:
    """RF-11 / RN-02. Reemplaza la tasa de esa fecha si ya habia una."""
    if valor <= 0:
        raise ErrorTasa("La tasa de cambio debe ser mayor que cero.")
    with transaccion(conexion):
        repo_tasa.registrar(
            conexion, TasaCambio(fecha or hoy(), valor, MANUAL, usuario_id)
        )


def actualizar_desde_bcv(
    conexion: sqlite3.Connection,
    fecha: str | None = None,
    usuario_id: int | None = None,
) -> Decimal | None:
    """RF-10. Consulta el BCV y registra la tasa; None si no se pudo.

    Devolver None no es un error: la interfaz ofrece la carga manual y la
    operacion del dia sigue.
    """
    from minimarket.infra import bcv  # import diferido: `datos/` no depende de red

    valor = bcv.consultar(repo_configuracion.leer(conexion, "bcv.url"))
    if valor is None:
        _bitacora.info("Consulta al BCV sin resultado; queda la carga manual.")
        return None
    with transaccion(conexion):
        repo_tasa.registrar(
            conexion, TasaCambio(fecha or hoy(), valor, BCV_AUTO, usuario_id)
        )
    return valor


def historico(
    conexion: sqlite3.Connection, desde: str | None = None, hasta: str | None = None
) -> list[TasaCambio]:
    """RF-13. Las operaciones pasadas conservan su tasa; aca se consulta."""
    return repo_tasa.historico(conexion, desde, hasta)


def multiplo_redondeo(conexion: sqlite3.Connection) -> Decimal:
    """RN-10. Multiplo configurado para el precio en bolivares al publico."""
    return repo_configuracion.leer_decimal(
        conexion, "precio.redondeo_bs", Decimal(1)
    )
