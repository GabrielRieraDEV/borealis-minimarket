"""Casos de uso de compras y proveedores (RF-14 a RF-21).

Una compra se registra entera o no se registra: encabezado, lineas, lotes y
movimientos de entrada viajan en UNA sola transaccion (RNF-06). Los errores
salen como `ErrorCompra` con el mensaje ya redactado para el usuario (RNF-09).
"""

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from minimarket.datos.conexion import transaccion
from minimarket.datos.repositorios import alicuota as repo_alicuota
from minimarket.datos.repositorios import categoria as repo_categoria
from minimarket.datos.repositorios import compra as repo_compra
from minimarket.datos.repositorios import inventario as repo_inventario
from minimarket.datos.repositorios import producto as repo_producto
from minimarket.datos.repositorios import proveedor as repo_proveedor
from minimarket.datos.repositorios import tasa as repo_tasa
from minimarket.dominio.compra import (
    CONFIRMADA,
    Compra,
    LineaCompra,
    PagoProveedor,
    Proveedor,
)
from minimarket.dominio.inventario import (
    ANULACION_COMPRA,
    COMPRA,
    REF_COMPRA,
    Movimiento,
)
from minimarket.dominio.producto import (
    Producto,
    margen_aplicable,
    margen_resultante,
    precio_sugerido,
)
from minimarket.servicios import USUARIO_ACTUAL, tasa as servicio_tasa

MEDIOS_PAGO = ["EFECTIVO", "TRANSFERENCIA", "PAGO_MOVIL", "PUNTO", "CREDITO"]


class ErrorCompra(Exception):
    """Falla previsible, con mensaje listo para mostrar en pantalla."""


@dataclass(frozen=True)
class AvisoMargen:
    """Producto cuyo precio quedo corto frente al costo recien comprado.

    No se toca el precio: se avisa. Cambiarlo es decision del administrador,
    y para eso esta el recalculo de RF-08.
    """

    producto: Producto
    costo_unitario_usd: Decimal
    margen_actual: Decimal | None  # None: el precio no cubre ni el costo
    margen_objetivo: Decimal
    precio_sugerido_usd: Decimal


@dataclass(frozen=True)
class ResultadoCompra:
    compra_id: int
    avisos: list[AvisoMargen]


# --- Proveedores (RF-14) ----------------------------------------------------


def guardar_proveedor(conexion: sqlite3.Connection, proveedor: Proveedor) -> int:
    """RF-14. Alta si no tiene id, modificacion si lo tiene."""
    if not proveedor.nombre.strip():
        raise ErrorCompra("El proveedor necesita un nombre.")
    with transaccion(conexion):
        if proveedor.id is None:
            return repo_proveedor.crear(conexion, proveedor)
        repo_proveedor.actualizar(conexion, proveedor)
        return proveedor.id


def cambiar_estado_proveedor(
    conexion: sqlite3.Connection, proveedor_id: int, activo: bool
) -> None:
    """Baja logica: las compras historicas siguen apuntando al proveedor."""
    proveedor = repo_proveedor.obtener(conexion, proveedor_id)
    if proveedor is None:
        raise ErrorCompra("El proveedor ya no existe.")
    proveedor.activo = activo
    with transaccion(conexion):
        repo_proveedor.actualizar(conexion, proveedor)


# --- Registro de compras (RF-15 a RF-18, RF-21) -----------------------------


def registrar_compra(conexion: sqlite3.Connection, compra: Compra) -> ResultadoCompra:
    """RF-15 a RF-18. Confirma la compra y genera las entradas de inventario.

    Devuelve los productos que, con el costo recien cargado, quedaron por
    debajo de su margen objetivo, para que la pantalla los ofrezca a revision.
    """
    productos = _validar(conexion, compra)
    compra.tasa_id = _tasa_id(conexion, compra.fecha)
    compra.total_usd = compra.total_calculado
    compra.saldo_pendiente_usd = compra.total_usd
    compra.estado = CONFIRMADA

    with transaccion(conexion):
        compra.id = repo_compra.crear(conexion, compra)
        for linea in compra.lineas:
            if productos[linea.producto_id].maneja_vencimiento:
                # RF-21: el lote nace de la fecha de vencimiento de la linea.
                linea.lote_id = repo_inventario.obtener_o_crear_lote(
                    conexion, linea.producto_id, linea.fecha_vencimiento
                )
            repo_compra.agregar_linea(conexion, compra.id, linea)
            repo_inventario.registrar_movimiento(
                conexion,
                Movimiento(
                    producto_id=linea.producto_id,
                    lote_id=linea.lote_id,
                    tipo=COMPRA,
                    cantidad=linea.cantidad_unidades,  # RN-12: entrada, positiva
                    costo_unitario_usd=linea.costo_unitario_usd,  # RN-14
                    referencia_tipo=REF_COMPRA,
                    referencia_id=compra.id,
                    usuario_id=compra.usuario_id,
                ),
            )

    # Fuera de la transaccion: `v_ultimo_costo` ya ve la compra confirmada.
    return ResultadoCompra(compra.id, revisar_margenes(conexion, productos.values()))


def revisar_margenes(
    conexion: sqlite3.Connection, productos: Iterable[Producto]
) -> list[AvisoMargen]:
    """RN-08 / RN-09. Productos cuyo precio no alcanza el margen objetivo."""
    alicuotas = {a.id: a.porcentaje for a in repo_alicuota.listar(conexion)}
    avisos = []
    for producto in productos:
        costo = repo_producto.ultimo_costo(conexion, producto.id)
        if costo is None or costo == 0:
            continue
        categoria = repo_categoria.obtener(conexion, producto.categoria_id)
        if categoria is None:
            continue
        alicuota_pct = alicuotas.get(producto.alicuota_iva_id, Decimal(0))
        objetivo = margen_aplicable(producto, categoria)
        actual = margen_resultante(producto.precio_venta_usd, alicuota_pct, costo)
        if actual is not None and actual >= objetivo:
            continue
        avisos.append(
            AvisoMargen(
                producto=producto,
                costo_unitario_usd=costo,
                margen_actual=actual,
                margen_objetivo=objetivo,
                precio_sugerido_usd=precio_sugerido(
                    costo, producto, categoria, alicuota_pct
                ),
            )
        )
    return avisos


def anular_compra(
    conexion: sqlite3.Connection,
    compra_id: int,
    motivo: str,
    usuario_id: int = USUARIO_ACTUAL,
) -> None:
    """RF-20 / RN-13. Movimientos inversos; el registro original se conserva."""
    compra = repo_compra.obtener(conexion, compra_id)
    if compra is None:
        raise ErrorCompra("La compra ya no existe.")
    if compra.estado != CONFIRMADA:
        raise ErrorCompra("Esta compra ya fue anulada.")
    if repo_compra.pagos_de(conexion, compra_id):
        raise ErrorCompra(
            "La compra tiene pagos registrados. Anula primero los pagos con el "
            "proveedor o registra la devolucion como una perdida."
        )

    entradas = [
        movimiento
        for movimiento in repo_inventario.movimientos_de_referencia(
            conexion, REF_COMPRA, compra_id
        )
        if movimiento.tipo == COMPRA
    ]
    for entrada in entradas:
        disponible = repo_inventario.existencia(conexion, entrada.producto_id)
        if disponible < entrada.cantidad:
            producto = repo_producto.obtener(conexion, entrada.producto_id)
            raise ErrorCompra(
                f"No se puede anular: de «{producto.nombre}» quedan {disponible} "
                f"unidades y la compra ingreso {entrada.cantidad}. Parte de la "
                "mercancia ya salio. Corregilo con un ajuste de inventario."
            )

    with transaccion(conexion):
        for entrada in entradas:
            repo_inventario.registrar_movimiento(
                conexion,
                Movimiento(
                    producto_id=entrada.producto_id,
                    lote_id=entrada.lote_id,
                    tipo=ANULACION_COMPRA,
                    cantidad=-entrada.cantidad,
                    costo_unitario_usd=entrada.costo_unitario_usd,  # RN-14
                    referencia_tipo=REF_COMPRA,
                    referencia_id=compra_id,
                    usuario_id=usuario_id,
                    observacion=motivo,
                ),
            )
        repo_compra.anular(conexion, compra_id, motivo)


# --- Pagos a proveedores (RF-19) --------------------------------------------


def registrar_pago(
    conexion: sqlite3.Connection,
    compra_id: int,
    monto_usd: Decimal,
    medio: str,
    fecha: str | None = None,
    referencia: str | None = None,
) -> None:
    """RF-19. Imputa el pago y baja el saldo pendiente de la compra."""
    compra = repo_compra.obtener(conexion, compra_id)
    if compra is None:
        raise ErrorCompra("La compra ya no existe.")
    if compra.estado != CONFIRMADA:
        raise ErrorCompra("No se pueden registrar pagos de una compra anulada.")
    if monto_usd <= 0:
        raise ErrorCompra("El monto del pago debe ser mayor que cero.")
    if monto_usd > compra.saldo_pendiente_usd:
        raise ErrorCompra(
            f"El pago supera el saldo pendiente, que es de "
            f"{compra.saldo_pendiente_usd} USD."
        )
    fecha = fecha or servicio_tasa.hoy()
    with transaccion(conexion):
        repo_compra.registrar_pago(
            conexion,
            PagoProveedor(
                compra_id=compra_id,
                fecha=fecha,
                monto_usd=monto_usd,
                medio=medio,
                tasa_id=_tasa_id(conexion, fecha),
                referencia=referencia,
            ),
        )
        repo_compra.actualizar_saldo(
            conexion, compra_id, compra.saldo_pendiente_usd - monto_usd
        )


# --- Validacion -------------------------------------------------------------


def _validar(
    conexion: sqlite3.Connection, compra: Compra
) -> dict[int, Producto]:
    """Devuelve los productos de la compra, ya verificados, indexados por id."""
    if repo_proveedor.obtener(conexion, compra.proveedor_id) is None:
        raise ErrorCompra("Elegi un proveedor valido.")
    if not compra.lineas:
        raise ErrorCompra("La compra no tiene ninguna linea cargada.")

    productos: dict[int, Producto] = {}
    for numero, linea in enumerate(compra.lineas, start=1):
        producto = productos.get(linea.producto_id) or repo_producto.obtener(
            conexion, linea.producto_id
        )
        if producto is None:
            raise ErrorCompra(f"La linea {numero} apunta a un producto inexistente.")
        productos[linea.producto_id] = producto
        _validar_linea(numero, linea, producto)
    return productos


def _validar_linea(numero: int, linea: LineaCompra, producto: Producto) -> None:
    if linea.cant_presentacion <= 0:
        raise ErrorCompra(
            f"Linea {numero} ({producto.nombre}): la cantidad de presentaciones "
            "debe ser mayor que cero."
        )
    if linea.unid_x_presentacion <= 0:
        raise ErrorCompra(
            f"Linea {numero} ({producto.nombre}): las unidades por presentacion "
            "deben ser mayores que cero."
        )
    if linea.costo_present_usd < 0:
        raise ErrorCompra(
            f"Linea {numero} ({producto.nombre}): el costo no puede ser negativo."
        )
    # RF-21: sin fecha no hay lote, y sin lote no se puede aplicar RN-15.
    if producto.maneja_vencimiento and not linea.fecha_vencimiento:
        raise ErrorCompra(
            f"Linea {numero} ({producto.nombre}): el producto controla "
            "vencimiento, cargá la fecha de vencimiento del lote."
        )


def _tasa_id(conexion: sqlite3.Connection, fecha: str) -> int:
    """RN-04. La tasa no se hereda: si falta la del dia, no se registra nada."""
    registro = repo_tasa.obtener(conexion, fecha)
    if registro is None:
        raise ErrorCompra(
            f"No hay tasa de cambio cargada para el {fecha}. Cargala antes de "
            "registrar la operacion."
        )
    return registro.id
