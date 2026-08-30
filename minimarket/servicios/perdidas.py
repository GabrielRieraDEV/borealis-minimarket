"""Perdidas y vencimientos (RF-28 a RF-33, RN-15, RN-17, RN-18).

Una perdida es una salida de inventario: el registro y el movimiento viajan en
UNA sola transaccion (RNF-06). Si algo falla no puede quedar la perdida
anotada sin descontar, ni al reves.

La valorizacion es la de RN-18: el ultimo costo vigente EN LA FECHA de la
perdida, no el de hoy. Una perdida de marzo no se encarece porque en julio se
compro mas caro.
"""

import sqlite3
import unicodedata
from decimal import Decimal

from minimarket.datos.conexion import transaccion
from minimarket.datos.repositorios import inventario as repo_inventario
from minimarket.datos.repositorios import perdida as repo_perdida
from minimarket.datos.repositorios import producto as repo_producto
from minimarket.dominio.inventario import (
    PERDIDA,
    REF_PERDIDA,
    MotivoPerdida,
    Movimiento,
    Perdida,
    SaldoLoteProducto,
)
from minimarket.dominio.usuario import REGISTRAR_PERDIDAS
from minimarket.infra import auditoria
from minimarket.servicios import ErrorServicio, usuario_actual
from minimarket.servicios import inventario as servicio_inventario
from minimarket.servicios import tasa as servicio_tasa
from minimarket.servicios import usuarios as servicio_usuarios

CODIGO_VENCIDO = "VENCIDO"


class ErrorPerdida(ErrorServicio):
    """Falla previsible, con mensaje listo para mostrar en pantalla."""


# --- Motivos (RF-29) --------------------------------------------------------


def motivos(conexion: sqlite3.Connection) -> list[MotivoPerdida]:
    """RF-29. Los cinco de fabrica mas los que se hayan agregado."""
    return repo_perdida.listar_motivos(conexion)


def crear_motivo(conexion: sqlite3.Connection, nombre: str) -> int:
    """RF-29. El codigo sale del nombre; lo unico que se pide es el nombre."""
    servicio_usuarios.exigir(conexion, REGISTRAR_PERDIDAS)
    nombre = nombre.strip()
    if not nombre:
        raise ErrorPerdida("El motivo necesita un nombre.")
    codigo = _codigo(nombre)
    with transaccion(conexion):
        try:
            return repo_perdida.crear_motivo(
                conexion, MotivoPerdida(codigo=codigo, nombre=nombre)
            )
        except sqlite3.IntegrityError as error:
            raise ErrorPerdida(f"Ya existe un motivo «{nombre}».") from error


# --- Registro (RF-28, RF-30, RN-18) -----------------------------------------


def registrar(
    conexion: sqlite3.Connection,
    producto_id: int,
    cantidad: Decimal,
    motivo_id: int,
    fecha: str | None = None,
    observacion: str | None = None,
    lote_id: int | None = None,
    usuario_id: int | None = None,
) -> Perdida:
    """RF-28 / RF-30. Registra la perdida y descuenta el inventario.

    Si no se indica lote y el producto lleva control de vencimiento, la salida
    se reparte por RN-15: primero el lote mas proximo a vencer.
    """
    usuario_id = usuario_id if usuario_id is not None else usuario_actual()
    servicio_usuarios.exigir(conexion, REGISTRAR_PERDIDAS, usuario_id)
    fecha = fecha or servicio_tasa.hoy()

    if cantidad <= 0:
        raise ErrorPerdida("La cantidad perdida debe ser mayor que cero.")
    producto = repo_producto.obtener(conexion, producto_id)
    if producto is None:
        raise ErrorPerdida("El producto ya no existe.")
    if repo_perdida.obtener_motivo(conexion, motivo_id) is None:
        raise ErrorPerdida("Elegi un motivo de perdida valido.")

    disponible = repo_inventario.existencia(conexion, producto_id)
    if cantidad > disponible:
        raise ErrorPerdida(
            f"No se puede dar de baja {cantidad} de «{producto.nombre}»: hay "
            f"{disponible}. Corregi la existencia con un ajuste antes."
        )

    # RN-18: el costo vigente en la fecha de la perdida. Sin compra previa a
    # esa fecha queda en cero y el reporte lo informa como no determinable,
    # igual que el margen de un producto sin costo.
    costo = repo_producto.ultimo_costo_a_fecha(conexion, producto_id, fecha) or Decimal(
        0
    )
    if lote_id is not None:
        _validar_lote(conexion, lote_id, producto_id, cantidad)
        reparto = [(lote_id, cantidad)]
    else:
        # RN-15: sin lote indicado, sale primero el mas proximo a vencer.
        reparto = servicio_inventario.salida_por_lotes(
            conexion, producto_id, cantidad
        )
    perdida = Perdida(
        producto_id=producto_id,
        motivo_id=motivo_id,
        cantidad=cantidad,
        costo_unitario_usd=costo,
        fecha=fecha,
        usuario_id=usuario_id,
        # Un solo lote lo guarda la cabecera; si la salida toca dos, queda en
        # NULL y el reparto real vive en los movimientos, igual que la venta.
        lote_id=reparto[0][0] if len(reparto) == 1 else None,
        observacion=observacion,
    )

    with transaccion(conexion):
        identificador = repo_perdida.crear(conexion, perdida)
        for lote, parcial in reparto:
            repo_inventario.registrar_movimiento(
                conexion,
                Movimiento(
                    producto_id=producto_id,
                    lote_id=lote,
                    tipo=PERDIDA,
                    cantidad=-parcial,  # RN-12: salida, negativa
                    costo_unitario_usd=costo,  # RN-14 / RN-18
                    referencia_tipo=REF_PERDIDA,
                    referencia_id=identificador,
                    usuario_id=usuario_id,
                    observacion=observacion,
                ),
            )
        auditoria.registrar(  # RF-59: la perdida saca mercancia del negocio
            conexion,
            usuario_id,
            auditoria.PERDIDA,
            "producto",
            producto_id,
            despues={
                "perdida_id": identificador,
                "cantidad": cantidad,
                "costo_unitario_usd": costo,
                "fecha": fecha,
            },
        )
    return repo_perdida.obtener(conexion, identificador)


def dar_de_baja_lote(
    conexion: sqlite3.Connection,
    lote_id: int,
    motivo_id: int | None = None,
    observacion: str | None = None,
    fecha: str | None = None,
) -> Perdida:
    """RF-32. Da de baja TODO lo que queda de un lote como perdida.

    El motivo por defecto es «vencido», que es para lo que existe el atajo;
    igual se puede indicar otro (un lote roto en el deposito, por ejemplo).
    """
    servicio_usuarios.exigir(conexion, REGISTRAR_PERDIDAS)
    lote = repo_inventario.obtener_lote(conexion, lote_id)
    if lote is None:
        raise ErrorPerdida("El lote ya no existe.")
    saldo = repo_inventario.saldo_de_lote(conexion, lote_id)
    if saldo <= 0:
        raise ErrorPerdida("Ese lote ya no tiene existencia que dar de baja.")
    if motivo_id is None:
        vencido = repo_perdida.motivo_por_codigo(conexion, CODIGO_VENCIDO)
        if vencido is None:
            raise ErrorPerdida(
                "No esta cargado el motivo «vencido». Crealo antes de dar de "
                "baja el lote."
            )
        motivo_id = vencido.id
    return registrar(
        conexion,
        producto_id=lote.producto_id,
        cantidad=saldo,
        motivo_id=motivo_id,
        fecha=fecha,
        observacion=observacion or f"Baja del lote vencido el {lote.fecha_vencimiento}",
        lote_id=lote_id,
    )


# --- Consultas --------------------------------------------------------------


def listar(
    conexion: sqlite3.Connection,
    desde: str | None = None,
    hasta: str | None = None,
    motivo_id: int | None = None,
) -> list[Perdida]:
    """RF-53 en detalle. Ver los costos es de administrador (RF-58)."""
    servicio_usuarios.exigir(conexion, REGISTRAR_PERDIDAS)
    return repo_perdida.listar(conexion, desde, hasta, motivo_id)


def costo_a_fecha(
    conexion: sqlite3.Connection, producto_id: int, fecha: str
) -> Decimal | None:
    """RN-18. En cuanto se valorizaria una perdida de ese dia; None si no hay.

    La pantalla lo muestra antes de confirmar, para que no sorprenda despues
    en el resultado del periodo.
    """
    servicio_usuarios.exigir(conexion, REGISTRAR_PERDIDAS)
    return repo_producto.ultimo_costo_a_fecha(conexion, producto_id, fecha)


def proximos_a_vencer(
    conexion: sqlite3.Connection, hoy: str | None = None, solo_alerta: bool = True
) -> list[SaldoLoteProducto]:
    """RF-31 / RF-54 / RN-17. Lotes con existencia dentro del plazo de aviso.

    Un lote vencido con existencia NO bloquea la venta: aparece aca y la
    decision de darlo de baja es del negocio.
    """
    lotes = repo_inventario.lotes_con_saldo(conexion)
    if not solo_alerta:
        return lotes
    return [lote for lote in lotes if lote.en_alerta(hoy)]


def _validar_lote(
    conexion: sqlite3.Connection,
    lote_id: int,
    producto_id: int,
    cantidad: Decimal,
) -> None:
    lote = repo_inventario.obtener_lote(conexion, lote_id)
    if lote is None:
        raise ErrorPerdida("El lote ya no existe.")
    if lote.producto_id != producto_id:
        raise ErrorPerdida("Ese lote es de otro producto.")
    saldo = repo_inventario.saldo_de_lote(conexion, lote_id)
    if cantidad > saldo:
        raise ErrorPerdida(
            f"El lote que vence el {lote.fecha_vencimiento} tiene {saldo} "
            f"unidades y se quieren dar de baja {cantidad}."
        )


def _codigo(nombre: str) -> str:
    """Un codigo legible a partir del nombre: MERMA_CHARCUTERIA y similares."""
    sin_tildes = "".join(
        c
        for c in unicodedata.normalize("NFD", nombre.upper())
        if unicodedata.category(c) != "Mn"
    )
    limpio = "".join(c if c.isalnum() else " " for c in sin_tildes)
    return "_".join(limpio.split())[:40]
