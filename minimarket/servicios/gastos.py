"""Gastos operativos (RF-46).

El alquiler, los servicios y los sueldos no tocan el inventario ni la caja:
solo entran en el resultado del periodo (RN-29), y ahi se restan del total sin
prorratearse entre productos.
"""

import re
import sqlite3
from decimal import Decimal

from minimarket.datos.conexion import transaccion
from minimarket.datos.repositorios import gasto as repo_gasto
from minimarket.dominio.reportes import CATEGORIAS_GASTO, GastoOperativo
from minimarket.dominio.usuario import REGISTRAR_GASTOS
from minimarket.servicios import ErrorServicio, usuario_actual
from minimarket.servicios import tasa as servicio_tasa
from minimarket.servicios import usuarios as servicio_usuarios

PERIODO = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class ErrorGasto(ErrorServicio):
    """Falla previsible, con mensaje listo para mostrar en pantalla."""


def registrar(
    conexion: sqlite3.Connection,
    categoria: str,
    descripcion: str,
    monto_usd: Decimal,
    periodo: str | None = None,
    fecha: str | None = None,
    usuario_id: int | None = None,
) -> GastoOperativo:
    """RF-46. `periodo` es el mes al que corresponde, no el dia de la carga."""
    usuario_id = usuario_id if usuario_id is not None else usuario_actual()
    servicio_usuarios.exigir(conexion, REGISTRAR_GASTOS, usuario_id)
    fecha = fecha or servicio_tasa.hoy()
    periodo = (periodo or fecha[:7]).strip()

    if categoria not in CATEGORIAS_GASTO:
        raise ErrorGasto("Elegi una categoria de gasto valida.")
    if not descripcion.strip():
        raise ErrorGasto("El gasto necesita una descripcion.")
    if monto_usd <= 0:
        raise ErrorGasto("El monto del gasto debe ser mayor que cero.")
    if not PERIODO.match(periodo):
        raise ErrorGasto("El periodo se escribe como AAAA-MM, por ejemplo 2026-08.")

    gasto = GastoOperativo(
        categoria=categoria,
        descripcion=descripcion.strip(),
        monto_usd=monto_usd,
        periodo=periodo,
        fecha=fecha,
        usuario_id=usuario_id,
    )
    with transaccion(conexion):
        identificador = repo_gasto.crear(conexion, gasto)
    return repo_gasto.obtener(conexion, identificador)


def listar(
    conexion: sqlite3.Connection,
    desde_periodo: str | None = None,
    hasta_periodo: str | None = None,
) -> list[GastoOperativo]:
    servicio_usuarios.exigir(conexion, REGISTRAR_GASTOS)
    return repo_gasto.listar(conexion, desde_periodo, hasta_periodo)


def total(conexion: sqlite3.Connection, desde: str, hasta: str) -> Decimal:
    """RN-29. Gastos de los meses que toca el rango, sin prorratear.

    Un rango que arranca a mitad de agosto se lleva el alquiler de agosto
    entero: la regla dice expresamente que los gastos no se prorratean.
    """
    return repo_gasto.total_del_rango(conexion, desde[:7], hasta[:7])
