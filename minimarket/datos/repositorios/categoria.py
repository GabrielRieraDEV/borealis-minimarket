"""Repositorio de categorias (RF-05).

Toda conversion entre el entero escalado de SQLite y `Decimal` ocurre aca.
"""

import sqlite3

from minimarket.dominio.dinero import ESCALA_PORCENTAJE, a_entero, desde_entero
from minimarket.dominio.producto import Categoria

_CAMPOS = "id, nombre, margen_objetivo, activo"


def _entidad(fila: sqlite3.Row) -> Categoria:
    return Categoria(
        id=fila["id"],
        nombre=fila["nombre"],
        margen_objetivo=desde_entero(fila["margen_objetivo"], ESCALA_PORCENTAJE),
        activo=bool(fila["activo"]),
    )


def listar(conexion: sqlite3.Connection, solo_activas: bool = True) -> list[Categoria]:
    sql = f"SELECT {_CAMPOS} FROM categoria"
    if solo_activas:
        sql += " WHERE activo = 1"
    sql += " ORDER BY nombre"
    return [_entidad(f) for f in conexion.execute(sql)]


def obtener(conexion: sqlite3.Connection, categoria_id: int) -> Categoria | None:
    fila = conexion.execute(
        f"SELECT {_CAMPOS} FROM categoria WHERE id = ?", (categoria_id,)
    ).fetchone()
    return _entidad(fila) if fila else None


def crear(conexion: sqlite3.Connection, categoria: Categoria) -> int:
    cursor = conexion.execute(
        "INSERT INTO categoria (nombre, margen_objetivo, activo) VALUES (?, ?, ?)",
        (
            categoria.nombre,
            a_entero(categoria.margen_objetivo, ESCALA_PORCENTAJE),
            int(categoria.activo),
        ),
    )
    return cursor.lastrowid


def actualizar(conexion: sqlite3.Connection, categoria: Categoria) -> None:
    conexion.execute(
        "UPDATE categoria SET nombre = ?, margen_objetivo = ?, activo = ? WHERE id = ?",
        (
            categoria.nombre,
            a_entero(categoria.margen_objetivo, ESCALA_PORCENTAJE),
            int(categoria.activo),
            categoria.id,
        ),
    )


def cantidad_productos(conexion: sqlite3.Connection, categoria_id: int) -> int:
    return conexion.execute(
        "SELECT COUNT(*) FROM producto WHERE categoria_id = ?", (categoria_id,)
    ).fetchone()[0]
