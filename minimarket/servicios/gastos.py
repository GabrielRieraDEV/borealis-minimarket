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


def repetir_mes_anterior(
    conexion: sqlite3.Connection, periodo: str | None = None
) -> list[GastoOperativo]:
    """Copia al mes los gastos del mes anterior: alquiler, sueldos, servicios.

    Pedido del cliente: los gastos fijos son los mismos todos los meses y
    cargarlos uno por uno cada mes es lo que hace que no se carguen. Se copian
    con el mismo monto; el que cambio se corrige despues. Si el mes ya tiene
    gastos, no se copia nada: repetir dos veces duplicaria el alquiler.
    """
    usuario_id = usuario_actual()
    servicio_usuarios.exigir(conexion, REGISTRAR_GASTOS, usuario_id)
    periodo = (periodo or servicio_tasa.hoy()[:7]).strip()
    if not PERIODO.match(periodo):
        raise ErrorGasto("El periodo se escribe como AAAA-MM, por ejemplo 2026-08.")
    if repo_gasto.listar(conexion, periodo, periodo):
        raise ErrorGasto(
            f"El mes {periodo} ya tiene gastos cargados. Se repite solo sobre "
            "un mes vacio, para no duplicar el alquiler."
        )
    anterior = _mes_anterior(periodo)
    origen = repo_gasto.listar(conexion, anterior, anterior)
    if not origen:
        raise ErrorGasto(f"El mes {anterior} no tiene gastos para repetir.")
    hoy = servicio_tasa.hoy()
    with transaccion(conexion):
        creados = [
            repo_gasto.crear(
                conexion,
                GastoOperativo(
                    categoria=gasto.categoria,
                    descripcion=gasto.descripcion,
                    monto_usd=gasto.monto_usd,
                    periodo=periodo,
                    fecha=hoy,
                    usuario_id=usuario_id,
                ),
            )
            for gasto in origen
        ]
    return [repo_gasto.obtener(conexion, identificador) for identificador in creados]


def _mes_anterior(periodo: str) -> str:
    anio, mes = int(periodo[:4]), int(periodo[5:])
    return f"{anio - 1}-12" if mes == 1 else f"{anio}-{mes - 1:02d}"


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
