"""Apertura, arqueo y cierre de la caja (RF-42 a RF-45, RN-26).

Una sola sesion abierta a la vez, y sin sesion abierta no se vende (RF-44).
El cierre calcula el esperado por medio de pago y la diferencia contra el
conteo fisico; una diferencia distinta de cero no impide cerrar, queda
registrada.
"""

import sqlite3
from decimal import Decimal

from minimarket.datos.conexion import transaccion
from minimarket.datos.repositorios import caja as repo_caja
from minimarket.dominio.dinero import convertir_a_bs, redondear_comercial
from minimarket.dominio.usuario import OPERAR_CAJA
from minimarket.dominio.venta import (
    BS,
    EFECTIVO,
    USD,
    CajaSesion,
    LineaCierre,
    ResumenCierre,
)
from minimarket.servicios import ErrorServicio, usuario_actual
from minimarket.servicios import tasa as servicio_tasa
from minimarket.servicios import usuarios as servicio_usuarios


class ErrorCaja(ErrorServicio):
    """Falla previsible, con mensaje listo para mostrar en pantalla."""


def sesion_abierta(conexion: sqlite3.Connection) -> CajaSesion | None:
    """RF-44. La sesion en curso, o None si la caja esta cerrada."""
    return repo_caja.sesion_abierta(conexion)


def exigir_sesion(conexion: sqlite3.Connection) -> CajaSesion:
    """RF-44. Sin caja abierta no se registra ninguna venta."""
    sesion = repo_caja.sesion_abierta(conexion)
    if sesion is None:
        raise ErrorCaja(
            "No hay una caja abierta. Abri la caja antes de registrar ventas."
        )
    return sesion


def abrir(
    conexion: sqlite3.Connection,
    inicial_bs: Decimal = Decimal(0),
    inicial_usd: Decimal = Decimal(0),
    usuario_id: int | None = None,
) -> CajaSesion:
    """RF-42. Monto inicial en cada moneda.

    Se exige la tasa del dia aca y no al vender: si falta, el cajero se entera
    al abrir y no con el cliente enfrente (RN-04).
    """
    usuario_id = usuario_id if usuario_id is not None else usuario_actual()
    servicio_usuarios.exigir(conexion, OPERAR_CAJA, usuario_id)
    if inicial_bs < 0 or inicial_usd < 0:
        raise ErrorCaja("Los montos iniciales no pueden ser negativos.")
    if repo_caja.sesion_abierta(conexion) is not None:
        raise ErrorCaja("Ya hay una caja abierta. Cerrala antes de abrir otra.")
    servicio_tasa.exigir_tasa(conexion)
    with transaccion(conexion):
        identificador = repo_caja.abrir(
            conexion,
            CajaSesion(
                usuario_apertura_id=usuario_id,
                inicial_bs=inicial_bs,
                inicial_usd=inicial_usd,
            ),
        )
    return repo_caja.obtener(conexion, identificador)


def arqueo(
    conexion: sqlite3.Connection,
    sesion_id: int,
    conteo_bs: Decimal | None = None,
    conteo_usd: Decimal | None = None,
) -> ResumenCierre:
    """RN-26. Lo esperado por medio y moneda, y la diferencia si ya hay conteo.

    Se puede pedir con la caja abierta para revisar como va el turno; el cierre
    lo vuelve a calcular antes de guardar.
    """
    sesion = repo_caja.obtener(conexion, sesion_id)
    if sesion is None:
        raise ErrorCaja("La sesion de caja ya no existe.")

    cobrado = repo_caja.cobrado_por_medio(conexion, sesion_id)
    multiplo = servicio_tasa.multiplo_redondeo(conexion)
    # RN-23: el vuelto se entrega en bolivares y sale de la gaveta.
    vuelto_bs = sum(
        (
            redondear_comercial(convertir_a_bs(monto, tasa), multiplo)
            for monto, tasa in repo_caja.vueltos_de(conexion, sesion_id)
        ),
        Decimal(0),
    )

    lineas = [
        LineaCierre(
            medio=EFECTIVO,
            moneda=BS,
            esperado=sesion.inicial_bs + cobrado.get((EFECTIVO, BS), Decimal(0))
            - vuelto_bs,
            conteo=conteo_bs,
        ),
        LineaCierre(
            medio=EFECTIVO,
            moneda=USD,
            esperado=sesion.inicial_usd + cobrado.get((EFECTIVO, USD), Decimal(0)),
            conteo=conteo_usd,
        ),
    ]
    # Los medios electronicos no se cuentan en la gaveta: se concilian contra
    # el banco. Van sin conteo, solo con lo que deberia haber entrado.
    lineas += [
        LineaCierre(medio=medio, moneda=moneda, esperado=monto)
        for (medio, moneda), monto in sorted(cobrado.items())
        if medio != EFECTIVO
    ]

    ventas, vendido = repo_caja.resumen_ventas(conexion, sesion_id)
    return ResumenCierre(sesion, lineas, ventas, vendido)


def cerrar(
    conexion: sqlite3.Connection,
    conteo_bs: Decimal,
    conteo_usd: Decimal,
    usuario_id: int | None = None,
) -> ResumenCierre:
    """RF-43 / RN-26. Cierra la sesion abierta y registra las diferencias."""
    usuario_id = usuario_id if usuario_id is not None else usuario_actual()
    servicio_usuarios.exigir(conexion, OPERAR_CAJA, usuario_id)
    if conteo_bs < 0 or conteo_usd < 0:
        raise ErrorCaja("Los montos contados no pueden ser negativos.")
    sesion = exigir_sesion(conexion)
    resumen = arqueo(conexion, sesion.id, conteo_bs, conteo_usd)
    diferencia_bs = resumen.linea(EFECTIVO, BS).diferencia
    diferencia_usd = resumen.linea(EFECTIVO, USD).diferencia
    with transaccion(conexion):
        repo_caja.cerrar(
            conexion,
            sesion.id,
            usuario_id,
            conteo_bs,
            conteo_usd,
            diferencia_bs,
            diferencia_usd,
        )
    return ResumenCierre(
        repo_caja.obtener(conexion, sesion.id),
        resumen.lineas,
        resumen.ventas,
        resumen.total_vendido_usd,
    )
