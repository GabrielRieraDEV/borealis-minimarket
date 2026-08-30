"""Repositorio de productos (RF-01 a RF-04).

`precio_venta_usd` se guarda x10.000 e INCLUYE IVA. `existencia_minima` x1.000.
La existencia real no vive aca: es la suma de `movimiento_inventario` (RN-11).
"""

import sqlite3
from decimal import Decimal

from minimarket.dominio.dinero import (
    ESCALA_CANTIDAD,
    ESCALA_PORCENTAJE,
    ESCALA_PRECIO,
    a_entero,
    desde_entero,
)
from minimarket.dominio.producto import Producto

_CAMPOS = """id, codigo_barras, nombre, categoria_id, alicuota_iva_id,
             precio_venta_usd, margen_objetivo, existencia_minima,
             maneja_vencimiento, dias_alerta_venc, activo"""


def _entidad(fila: sqlite3.Row) -> Producto:
    margen = fila["margen_objetivo"]
    return Producto(
        id=fila["id"],
        codigo_barras=fila["codigo_barras"],
        nombre=fila["nombre"],
        categoria_id=fila["categoria_id"],
        alicuota_iva_id=fila["alicuota_iva_id"],
        precio_venta_usd=desde_entero(fila["precio_venta_usd"], ESCALA_PRECIO),
        margen_objetivo=(
            None if margen is None else desde_entero(margen, ESCALA_PORCENTAJE)
        ),
        existencia_minima=desde_entero(fila["existencia_minima"], ESCALA_CANTIDAD),
        maneja_vencimiento=bool(fila["maneja_vencimiento"]),
        dias_alerta_venc=fila["dias_alerta_venc"],
        activo=bool(fila["activo"]),
    )


def obtener(conexion: sqlite3.Connection, producto_id: int) -> Producto | None:
    fila = conexion.execute(
        f"SELECT {_CAMPOS} FROM producto WHERE id = ?", (producto_id,)
    ).fetchone()
    return _entidad(fila) if fila else None


def por_codigo_barras(conexion: sqlite3.Connection, codigo: str) -> Producto | None:
    """RF-04. Coincidencia exacta: es lo que entrega el lector."""
    fila = conexion.execute(
        f"SELECT {_CAMPOS} FROM producto WHERE codigo_barras = ?", (codigo,)
    ).fetchone()
    return _entidad(fila) if fila else None


def buscar_por_nombre(
    conexion: sqlite3.Connection,
    texto: str,
    solo_activos: bool = True,
    limite: int = 200,
) -> list[Producto]:
    """RF-04. Coincidencia parcial, sin distinguir mayusculas."""
    sql = f"SELECT {_CAMPOS} FROM producto WHERE nombre LIKE ? ESCAPE '\\'"
    if solo_activos:
        sql += " AND activo = 1"
    sql += " ORDER BY nombre LIMIT ?"
    patron = f"%{_escapar_like(texto)}%"
    return [_entidad(f) for f in conexion.execute(sql, (patron, limite))]


def listar(
    conexion: sqlite3.Connection,
    categoria_id: int | None = None,
    solo_activos: bool = True,
    limite: int = 200,
) -> list[Producto]:
    sql = f"SELECT {_CAMPOS} FROM producto WHERE 1 = 1"
    parametros: list[object] = []
    if categoria_id is not None:
        sql += " AND categoria_id = ?"
        parametros.append(categoria_id)
    if solo_activos:
        sql += " AND activo = 1"
    sql += " ORDER BY nombre LIMIT ?"
    parametros.append(limite)
    return [_entidad(f) for f in conexion.execute(sql, parametros)]


def crear(conexion: sqlite3.Connection, producto: Producto) -> int:
    cursor = conexion.execute(
        """INSERT INTO producto
               (codigo_barras, nombre, categoria_id, alicuota_iva_id,
                precio_venta_usd, margen_objetivo, existencia_minima,
                maneja_vencimiento, dias_alerta_venc, activo)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        _valores(producto),
    )
    return cursor.lastrowid


def actualizar(conexion: sqlite3.Connection, producto: Producto) -> None:
    conexion.execute(
        """UPDATE producto SET
               codigo_barras = ?, nombre = ?, categoria_id = ?, alicuota_iva_id = ?,
               precio_venta_usd = ?, margen_objetivo = ?, existencia_minima = ?,
               maneja_vencimiento = ?, dias_alerta_venc = ?, activo = ?,
               actualizado_en = datetime('now','localtime')
           WHERE id = ?""",
        (*_valores(producto), producto.id),
    )


def actualizar_precio(
    conexion: sqlite3.Connection, producto_id: int, precio_usd: Decimal
) -> None:
    """RF-08. Recalculo en bloque: toca el precio y nada mas."""
    conexion.execute(
        """UPDATE producto
              SET precio_venta_usd = ?, actualizado_en = datetime('now','localtime')
            WHERE id = ?""",
        (a_entero(precio_usd, ESCALA_PRECIO), producto_id),
    )


def cambiar_estado(
    conexion: sqlite3.Connection, producto_id: int, activo: bool
) -> None:
    """RF-02. La baja es logica: el producto nunca se borra."""
    conexion.execute(
        """UPDATE producto
              SET activo = ?, actualizado_en = datetime('now','localtime')
            WHERE id = ?""",
        (int(activo), producto_id),
    )


def tiene_movimientos(conexion: sqlite3.Connection, producto_id: int) -> bool:
    return (
        conexion.execute(
            "SELECT 1 FROM movimiento_inventario WHERE producto_id = ? LIMIT 1",
            (producto_id,),
        ).fetchone()
        is not None
    )


def ultimo_costo(
    conexion: sqlite3.Connection, producto_id: int
) -> Decimal | None:
    """RN-07. Costo de la compra confirmada mas reciente, o None si no hay."""
    fila = conexion.execute(
        "SELECT costo_unitario_usd FROM v_ultimo_costo WHERE producto_id = ?",
        (producto_id,),
    ).fetchone()
    return desde_entero(fila[0], ESCALA_PRECIO) if fila else None


def ultimos_costos(
    conexion: sqlite3.Connection, categoria_id: int
) -> dict[int, Decimal]:
    """RN-07 para toda una categoria, en una sola consulta (RF-08)."""
    filas = conexion.execute(
        """SELECT c.producto_id, c.costo_unitario_usd
             FROM v_ultimo_costo c
             JOIN producto p ON p.id = c.producto_id
            WHERE p.categoria_id = ?""",
        (categoria_id,),
    )
    return {f[0]: desde_entero(f[1], ESCALA_PRECIO) for f in filas}


def _valores(producto: Producto) -> tuple:
    return (
        producto.codigo_barras or None,  # RF-03: cadena vacia es "sin codigo"
        producto.nombre,
        producto.categoria_id,
        producto.alicuota_iva_id,
        a_entero(producto.precio_venta_usd, ESCALA_PRECIO),
        (
            None
            if producto.margen_objetivo is None
            else a_entero(producto.margen_objetivo, ESCALA_PORCENTAJE)
        ),
        a_entero(producto.existencia_minima, ESCALA_CANTIDAD),
        int(producto.maneja_vencimiento),
        producto.dias_alerta_venc,
        int(producto.activo),
    )


def _escapar_like(texto: str) -> str:
    """Sin esto, un `%` tecleado en la busqueda trae el catalogo entero."""
    for caracter in ("\\", "%", "_"):
        texto = texto.replace(caracter, "\\" + caracter)
    return texto
