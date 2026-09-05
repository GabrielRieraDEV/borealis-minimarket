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
from minimarket.datos.repositorios import reportes as repo_reportes
from minimarket.dominio.reportes import (
    CATEGORIAS_GASTO,
    FIJO,
    PORCENTAJE,
    GastoOperativo,
    GastoRecurrente,
    RenglonGasto,
)
from minimarket.dominio.venta import MEDIOS
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

    Suma lo cargado a mano mas los recurrentes de cada mes (1.2.0): los fijos
    por su monto y los porcentuales sobre lo cobrado en ese mes. No se
    materializan: asi no hay duplicados ni «ya lo copie o no».
    """
    total = repo_gasto.total_del_rango(conexion, desde[:7], hasta[:7])
    for periodo in _meses(desde[:7], hasta[:7]):
        total += _recurrentes_del_mes(conexion, periodo)
    return total


def desglose_del_mes(conexion: sqlite3.Connection, periodo: str) -> list[RenglonGasto]:
    """Todo lo que pesa en un mes, ya valuado, para la pantalla."""
    servicio_usuarios.exigir(conexion, REGISTRAR_GASTOS)
    renglones = [
        RenglonGasto(g.periodo, g.categoria, g.descripcion, g.monto_usd, "cargado")
        for g in repo_gasto.listar(conexion, periodo, periodo)
    ]
    cobrado = _cobrado_por_medio(conexion, periodo)
    for gasto in repo_gasto.listar_recurrentes(conexion, periodo):
        renglones.append(
            RenglonGasto(
                periodo,
                gasto.categoria,
                gasto.descripcion,
                gasto.valuar(cobrado),
                describir_recurrente(gasto),
            )
        )
    return renglones


def describir_recurrente(gasto: GastoRecurrente) -> str:
    if gasto.tipo == FIJO:
        return "fijo mensual"
    medio = "todo lo cobrado" if gasto.medio is None else f"lo cobrado por {gasto.medio.lower().replace('_', ' ')}"
    return f"{gasto.porcentaje.normalize()} % de {medio}"


def gastos_del_mes_para_margen(
    conexion: sqlite3.Connection, periodo: str
) -> tuple[Decimal, list[GastoRecurrente]]:
    """Para el margen sugerido: (fijos del mes en USD, porcentuales vigentes).

    Los fijos son lo cargado a mano mas los recurrentes FIJO. Los porcentuales
    se devuelven sin valuar: su peso depende de cuanto se venda, que es lo que
    el margen sugerido pone como incognita.
    """
    fijos = repo_gasto.total_del_rango(conexion, periodo, periodo)
    porcentuales = []
    for gasto in repo_gasto.listar_recurrentes(conexion, periodo):
        if gasto.tipo == FIJO:
            fijos += gasto.monto_usd
        else:
            porcentuales.append(gasto)
    return fijos, porcentuales


# --- Recurrentes (1.2.0) ----------------------------------------------------


def registrar_recurrente(
    conexion: sqlite3.Connection,
    categoria: str,
    descripcion: str,
    tipo: str,
    monto_usd: Decimal = Decimal(0),
    porcentaje: Decimal = Decimal(0),
    medio: str | None = None,
    desde_periodo: str | None = None,
) -> GastoRecurrente:
    """Un gasto que rige todos los meses desde `desde_periodo` hasta que se de de baja."""
    usuario_id = usuario_actual()
    servicio_usuarios.exigir(conexion, REGISTRAR_GASTOS, usuario_id)
    desde_periodo = (desde_periodo or servicio_tasa.hoy()[:7]).strip()
    if categoria not in CATEGORIAS_GASTO:
        raise ErrorGasto("Elegi una categoria de gasto valida.")
    if not descripcion.strip():
        raise ErrorGasto("El gasto necesita una descripcion.")
    if not PERIODO.match(desde_periodo):
        raise ErrorGasto("El mes desde el que rige se escribe como AAAA-MM.")
    if tipo == FIJO:
        if monto_usd <= 0:
            raise ErrorGasto("El monto mensual debe ser mayor que cero.")
        porcentaje, medio = Decimal(0), None
    elif tipo == PORCENTAJE:
        if porcentaje <= 0 or porcentaje >= 100:
            raise ErrorGasto("El porcentaje tiene que estar entre 0 y 100.")
        if medio is not None and medio not in MEDIOS:
            raise ErrorGasto("Elegi un medio de pago valido, o todos.")
        monto_usd = Decimal(0)
    else:
        raise ErrorGasto("El gasto recurrente es fijo o por porcentaje.")
    gasto = GastoRecurrente(
        categoria=categoria,
        descripcion=descripcion.strip(),
        tipo=tipo,
        monto_usd=monto_usd,
        porcentaje=porcentaje,
        medio=medio,
        desde_periodo=desde_periodo,
        usuario_id=usuario_id,
    )
    with transaccion(conexion):
        identificador = repo_gasto.crear_recurrente(conexion, gasto)
    return repo_gasto.obtener_recurrente(conexion, identificador)


def listar_recurrentes(conexion: sqlite3.Connection) -> list[GastoRecurrente]:
    servicio_usuarios.exigir(conexion, REGISTRAR_GASTOS)
    return repo_gasto.listar_recurrentes(conexion)


def dar_de_baja_recurrente(
    conexion: sqlite3.Connection, gasto_id: int, ultimo_periodo: str | None = None
) -> None:
    """Deja de regir despues de `ultimo_periodo` (por defecto, el mes actual).

    El mes en curso lo sigue contando: si el alquiler se pago en septiembre,
    septiembre lo lleva aunque se de de baja el 20.
    """
    servicio_usuarios.exigir(conexion, REGISTRAR_GASTOS)
    ultimo_periodo = (ultimo_periodo or servicio_tasa.hoy()[:7]).strip()
    gasto = repo_gasto.obtener_recurrente(conexion, gasto_id)
    if gasto is None:
        raise ErrorGasto("Ese gasto recurrente no existe.")
    if not PERIODO.match(ultimo_periodo) or ultimo_periodo < gasto.desde_periodo:
        raise ErrorGasto("El ultimo mes no puede ser anterior al primero.")
    with transaccion(conexion):
        repo_gasto.cerrar_recurrente(conexion, gasto_id, ultimo_periodo)


def _recurrentes_del_mes(conexion: sqlite3.Connection, periodo: str) -> Decimal:
    vigentes = repo_gasto.listar_recurrentes(conexion, periodo)
    if not vigentes:
        return Decimal(0)
    cobrado = _cobrado_por_medio(conexion, periodo)
    return sum((g.valuar(cobrado) for g in vigentes), Decimal(0))


def _cobrado_por_medio(conexion: sqlite3.Connection, periodo: str) -> dict[str, Decimal]:
    """Lo cobrado en el mes por cada medio, en dolares, sumando las monedas."""
    cobrado: dict[str, Decimal] = {}
    for linea in repo_reportes.totales_por_medio(
        conexion, f"{periodo}-01", f"{periodo}-31"
    ):
        cobrado[linea.medio] = cobrado.get(linea.medio, Decimal(0)) + linea.monto_usd
    return cobrado


def _meses(desde: str, hasta: str) -> list[str]:
    """Los AAAA-MM entre dos, inclusive."""
    anio, mes = int(desde[:4]), int(desde[5:])
    meses = []
    while f"{anio}-{mes:02d}" <= hasta:
        meses.append(f"{anio}-{mes:02d}")
        anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    return meses
