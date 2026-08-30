"""Casos de uso de inventario (RF-22 a RF-26).

La existencia nunca se escribe: se consulta como suma de los movimientos
(RN-11). Lo unico que altera el inventario desde aca es el ajuste por conteo
fisico, y solo lo puede hacer un administrador (RF-26).
"""

import sqlite3
from decimal import Decimal

from minimarket.datos.conexion import transaccion
from minimarket.datos.repositorios import inventario as repo_inventario
from minimarket.datos.repositorios import producto as repo_producto
from minimarket.datos.repositorios import usuario as repo_usuario
from minimarket.dominio.inventario import (
    AJUSTE,
    REF_AJUSTE,
    ExistenciaProducto,
    Movimiento,
    SaldoLote,
    repartir_por_lote,
)
from minimarket.servicios import USUARIO_ACTUAL


class ErrorInventario(Exception):
    """Falla previsible, con mensaje listo para mostrar en pantalla."""


def existencia(conexion: sqlite3.Connection, producto_id: int) -> Decimal:
    """RF-22 / RN-11."""
    return repo_inventario.existencia(conexion, producto_id)


def consultar(
    conexion: sqlite3.Connection,
    texto: str = "",
    solo_alerta: bool = False,
    solo_activos: bool = True,
) -> list[ExistenciaProducto]:
    """RF-22 y RF-24. `solo_alerta` deja los que estan en o bajo el minimo."""
    return repo_inventario.existencias(
        conexion,
        texto=texto.strip() or None,
        solo_alerta=solo_alerta,
        solo_activos=solo_activos,
    )


def bajo_minimo(conexion: sqlite3.Connection) -> list[ExistenciaProducto]:
    """RF-24 / RN-16. Lo que hay que reponer."""
    return consultar(conexion, solo_alerta=True)


def movimientos(
    conexion: sqlite3.Connection, producto_id: int
) -> list[Movimiento]:
    """RF-23. El kardex explica por que un producto tiene lo que tiene."""
    return repo_inventario.movimientos_de(conexion, producto_id)


def salida_por_lotes(
    conexion: sqlite3.Connection, producto_id: int, cantidad: Decimal
) -> list[tuple[int | None, Decimal]]:
    """RN-15. Reparte una salida entre lotes, el mas proximo a vencer primero.

    El producto sin control de vencimiento sale entero sin lote. La usa la
    venta (Fase 3) y la baja de lotes vencidos (Fase 5).
    """
    producto = repo_producto.obtener(conexion, producto_id)
    if producto is None:
        raise ErrorInventario("El producto ya no existe.")
    if not producto.maneja_vencimiento:
        return [(None, cantidad)]
    saldos: list[SaldoLote] = repo_inventario.saldos_por_lote(conexion, producto_id)
    return repartir_por_lote(cantidad, saldos)


def ajustar_por_conteo(
    conexion: sqlite3.Connection,
    producto_id: int,
    cantidad_fisica: Decimal,
    motivo: str,
    usuario_id: int = USUARIO_ACTUAL,
) -> Decimal:
    """RF-25 / RF-26. Conteo fisico; devuelve la diferencia aplicada.

    Solo administrador. La diferencia entra como un movimiento AJUSTE con su
    signo (RN-12); un conteo que coincide queda registrado sin movimiento,
    porque `movimiento_inventario` no admite cantidad cero.
    """
    if not repo_usuario.es_administrador(conexion, usuario_id):
        raise ErrorInventario(
            "El ajuste de inventario esta reservado al administrador."
        )
    if cantidad_fisica < 0:
        raise ErrorInventario("La cantidad contada no puede ser negativa.")
    if not motivo.strip():
        raise ErrorInventario("Indica el motivo del ajuste.")
    producto = repo_producto.obtener(conexion, producto_id)
    if producto is None:
        raise ErrorInventario("El producto ya no existe.")

    cantidad_sistema = repo_inventario.existencia(conexion, producto_id)
    diferencia = cantidad_fisica - cantidad_sistema
    costo = repo_producto.ultimo_costo(conexion, producto_id) or Decimal(0)

    with transaccion(conexion):
        ajuste_id = repo_inventario.registrar_ajuste(
            conexion,
            producto_id,
            cantidad_sistema,
            cantidad_fisica,
            motivo.strip(),
            usuario_id,
        )
        if diferencia != 0:
            repo_inventario.registrar_movimiento(
                conexion,
                Movimiento(
                    producto_id=producto_id,
                    tipo=AJUSTE,
                    cantidad=diferencia,
                    costo_unitario_usd=costo,  # RN-14
                    referencia_tipo=REF_AJUSTE,
                    referencia_id=ajuste_id,
                    usuario_id=usuario_id,
                    observacion=motivo.strip(),
                ),
            )
    return diferencia
