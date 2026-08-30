"""Repositorio de proveedores (RF-14)."""

import sqlite3

from minimarket.dominio.compra import Proveedor

_CAMPOS = "id, nombre, rif, telefono, contacto, activo"


def _entidad(fila: sqlite3.Row) -> Proveedor:
    return Proveedor(
        id=fila["id"],
        nombre=fila["nombre"],
        rif=fila["rif"],
        telefono=fila["telefono"],
        contacto=fila["contacto"],
        activo=bool(fila["activo"]),
    )


def listar(conexion: sqlite3.Connection, solo_activos: bool = True) -> list[Proveedor]:
    sql = f"SELECT {_CAMPOS} FROM proveedor"
    if solo_activos:
        sql += " WHERE activo = 1"
    sql += " ORDER BY nombre"
    return [_entidad(f) for f in conexion.execute(sql)]


def obtener(conexion: sqlite3.Connection, proveedor_id: int) -> Proveedor | None:
    fila = conexion.execute(
        f"SELECT {_CAMPOS} FROM proveedor WHERE id = ?", (proveedor_id,)
    ).fetchone()
    return _entidad(fila) if fila else None


def crear(conexion: sqlite3.Connection, proveedor: Proveedor) -> int:
    cursor = conexion.execute(
        """INSERT INTO proveedor (nombre, rif, telefono, contacto, activo)
           VALUES (?, ?, ?, ?, ?)""",
        _valores(proveedor),
    )
    return cursor.lastrowid


def actualizar(conexion: sqlite3.Connection, proveedor: Proveedor) -> None:
    conexion.execute(
        """UPDATE proveedor
              SET nombre = ?, rif = ?, telefono = ?, contacto = ?, activo = ?
            WHERE id = ?""",
        (*_valores(proveedor), proveedor.id),
    )


def _valores(proveedor: Proveedor) -> tuple:
    return (
        proveedor.nombre,
        proveedor.rif or None,
        proveedor.telefono or None,
        proveedor.contacto or None,
        int(proveedor.activo),
    )
