"""Casos de uso del catalogo (RF-01 a RF-08).

La interfaz no habla con `datos/`: entra por aca. Los errores salen como
`ErrorCatalogo` con un mensaje ya redactado para el usuario final (RNF-09).
"""

import sqlite3
from decimal import Decimal

from minimarket.datos.conexion import transaccion
from minimarket.datos.repositorios import alicuota as repo_alicuota
from minimarket.datos.repositorios import categoria as repo_categoria
from minimarket.datos.repositorios import producto as repo_producto
from minimarket.dominio.producto import (
    Categoria,
    Producto,
    margen_resultante,
    precio_sugerido,
)
from minimarket.dominio.usuario import MODIFICAR_PRECIOS, VER_COSTOS
from minimarket.infra import auditoria
from minimarket.servicios import ErrorServicio, usuario_actual
from minimarket.servicios import usuarios as servicio_usuarios


class ErrorCatalogo(ErrorServicio):
    """Falla previsible, con mensaje listo para mostrar en pantalla."""


def crear_producto(conexion: sqlite3.Connection, producto: Producto) -> int:
    """RF-01. Alta de catalogo: fija un precio, asi que es de administrador."""
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    _validar(conexion, producto)
    with transaccion(conexion):
        try:
            return repo_producto.crear(conexion, producto)
        except sqlite3.IntegrityError as error:
            raise _error_codigo_repetido(producto, error) from error


def modificar_producto(conexion: sqlite3.Connection, producto: Producto) -> None:
    """RF-01 / RF-58. El cambio de precio queda en la bitacora (RF-59)."""
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    if producto.id is None:
        raise ErrorCatalogo("No se puede modificar un producto que no fue guardado.")
    _validar(conexion, producto)
    anterior = repo_producto.obtener(conexion, producto.id)
    autor = usuario_actual()
    with transaccion(conexion):
        try:
            repo_producto.actualizar(conexion, producto)
        except sqlite3.IntegrityError as error:
            raise _error_codigo_repetido(producto, error) from error
        cambio_de_precio = (
            anterior is not None
            and anterior.precio_venta_usd != producto.precio_venta_usd
        )
        if cambio_de_precio:
            auditoria.registrar(
                conexion,
                autor,
                auditoria.CAMBIO_PRECIO,
                "producto",
                producto.id,
                antes={"precio_venta_usd": anterior.precio_venta_usd},
                despues={"precio_venta_usd": producto.precio_venta_usd},
            )


def desactivar_producto(conexion: sqlite3.Connection, producto_id: int) -> None:
    """RF-02. Baja logica siempre: el producto con movimientos no se borra."""
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    with transaccion(conexion):
        repo_producto.cambiar_estado(conexion, producto_id, activo=False)


def reactivar_producto(conexion: sqlite3.Connection, producto_id: int) -> None:
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    with transaccion(conexion):
        repo_producto.cambiar_estado(conexion, producto_id, activo=True)


def buscar(
    conexion: sqlite3.Connection, texto: str, solo_activos: bool = True
) -> list[Producto]:
    """RF-04. Codigo de barras exacto primero; si no, nombre parcial.

    El lector de codigo de barras entrega el codigo completo, asi que la
    coincidencia exacta corta la busqueda antes de recorrer nombres.
    """
    texto = texto.strip()
    if not texto:
        return repo_producto.listar(conexion, solo_activos=solo_activos)
    exacto = repo_producto.por_codigo_barras(conexion, texto)
    if exacto is not None and (exacto.activo or not solo_activos):
        return [exacto]
    return repo_producto.buscar_por_nombre(conexion, texto, solo_activos=solo_activos)


def listado_completo(
    conexion: sqlite3.Connection, solo_activos: bool = True
) -> list[Producto]:
    """Todo el catalogo, para los selectores de producto de la interfaz.

    `buscar` esta limitada a 200 filas porque responde a cada tecla; un
    selector con autocompletado necesita el catalogo entero cargado.
    """
    return repo_producto.listar(
        conexion, solo_activos=solo_activos, limite=1_000_000
    )


def calcular_precio(
    conexion: sqlite3.Connection, producto: Producto
) -> Decimal | None:
    """RF-07. Precio con IVA sugerido por el margen objetivo aplicable.

    Devuelve None si el producto no tiene costo de compra todavia: sin costo,
    RN-09 no tiene de donde partir.
    """
    servicio_usuarios.exigir(conexion, VER_COSTOS)  # RF-58
    costo = repo_producto.ultimo_costo(conexion, producto.id) if producto.id else None
    if costo is None:
        return None
    categoria = _categoria(conexion, producto.categoria_id)
    return precio_sugerido(
        costo, producto, categoria, _porcentaje(conexion, producto.alicuota_iva_id)
    )


def calcular_margen(
    conexion: sqlite3.Connection, producto: Producto
) -> Decimal | None:
    """RF-07, camino inverso: margen que deja el precio cargado a mano."""
    servicio_usuarios.exigir(conexion, VER_COSTOS)  # RF-58
    costo = repo_producto.ultimo_costo(conexion, producto.id) if producto.id else None
    if costo is None:
        return None
    return margen_resultante(
        producto.precio_venta_usd,
        _porcentaje(conexion, producto.alicuota_iva_id),
        costo,
    )


def previsualizar_recalculo(
    conexion: sqlite3.Connection, categoria_id: int
) -> list[tuple[Producto, Decimal]]:
    """RF-08. Que precio quedaria en cada producto, sin tocar nada todavia.

    Se muestra al administrador para que confirme; recien despues corre
    `aplicar_recalculo`. Los productos sin costo de compra quedan fuera: no hay
    con que recalcularlos.
    """
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    categoria = _categoria(conexion, categoria_id)
    costos = repo_producto.ultimos_costos(conexion, categoria_id)
    alicuotas = {a.id: a.porcentaje for a in repo_alicuota.listar(conexion)}
    cambios = []
    for producto in repo_producto.listar(
        conexion, categoria_id=categoria_id, limite=1_000_000
    ):
        costo = costos.get(producto.id)
        if costo is None:
            continue
        nuevo = precio_sugerido(
            costo, producto, categoria, alicuotas[producto.alicuota_iva_id]
        )
        if nuevo != producto.precio_venta_usd:
            cambios.append((producto, nuevo))
    return cambios


def aplicar_recalculo(
    conexion: sqlite3.Connection, cambios: list[tuple[Producto, Decimal]]
) -> int:
    """RF-08. Aplica lo previsualizado; todo o nada (RNF-06)."""
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    autor = usuario_actual()
    with transaccion(conexion):
        for producto, precio in cambios:
            repo_producto.actualizar_precio(conexion, producto.id, precio)
            auditoria.registrar(  # RF-59
                conexion,
                autor,
                auditoria.RECALCULO_PRECIOS,
                "producto",
                producto.id,
                antes={"precio_venta_usd": producto.precio_venta_usd},
                despues={"precio_venta_usd": precio},
            )
    return len(cambios)


def guardar_categoria(conexion: sqlite3.Connection, categoria: Categoria) -> int:
    """RF-05. Alta si no tiene id, modificacion si lo tiene.

    Es de administrador: el margen objetivo de la categoria decide el precio
    sugerido de todos sus productos (RN-09).
    """
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    if not categoria.nombre.strip():
        raise ErrorCatalogo("La categoria necesita un nombre.")
    if categoria.margen_objetivo < 0:
        raise ErrorCatalogo("El margen objetivo no puede ser negativo.")
    with transaccion(conexion):
        try:
            if categoria.id is None:
                return repo_categoria.crear(conexion, categoria)
            repo_categoria.actualizar(conexion, categoria)
            return categoria.id
        except sqlite3.IntegrityError as error:
            raise ErrorCatalogo(
                f"Ya existe una categoria llamada «{categoria.nombre}»."
            ) from error


def _validar(conexion: sqlite3.Connection, producto: Producto) -> None:
    if not producto.nombre.strip():
        raise ErrorCatalogo("El producto necesita un nombre.")
    if producto.precio_venta_usd < 0:
        raise ErrorCatalogo("El precio de venta no puede ser negativo.")
    if producto.existencia_minima < 0:
        raise ErrorCatalogo("La existencia minima no puede ser negativa.")
    if repo_categoria.obtener(conexion, producto.categoria_id) is None:
        raise ErrorCatalogo("Elegi una categoria valida.")
    if repo_alicuota.obtener(conexion, producto.alicuota_iva_id) is None:
        raise ErrorCatalogo("Elegi una alicuota de IVA valida.")


def _categoria(conexion: sqlite3.Connection, categoria_id: int) -> Categoria:
    categoria = repo_categoria.obtener(conexion, categoria_id)
    if categoria is None:
        raise ErrorCatalogo("La categoria del producto ya no existe.")
    return categoria


def _porcentaje(conexion: sqlite3.Connection, alicuota_id: int) -> Decimal:
    alicuota = repo_alicuota.obtener(conexion, alicuota_id)
    if alicuota is None:
        raise ErrorCatalogo("La alicuota de IVA del producto ya no existe.")
    return alicuota.porcentaje


def _error_codigo_repetido(
    producto: Producto, error: sqlite3.IntegrityError
) -> ErrorCatalogo:
    if "codigo_barras" in str(error):
        return ErrorCatalogo(
            f"El codigo de barras «{producto.codigo_barras}» ya esta en uso "
            "por otro producto."
        )
    return ErrorCatalogo("No se pudo guardar el producto: revisa los datos cargados.")
