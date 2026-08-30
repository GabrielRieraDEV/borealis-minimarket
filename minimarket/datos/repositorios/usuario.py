"""Repositorio de usuarios: por ahora, solo el rol.

La Fase 4 trae autenticacion, alta y baja. RF-26 necesita saber si quien pide
un ajuste de inventario es administrador, y eso no puede esperar.
"""

import sqlite3

ADMIN = "ADMIN"
CAJERO = "CAJERO"


def rol(conexion: sqlite3.Connection, usuario_id: int) -> str | None:
    fila = conexion.execute(
        "SELECT rol FROM usuario WHERE id = ? AND activo = 1", (usuario_id,)
    ).fetchone()
    return fila[0] if fila else None


def es_administrador(conexion: sqlite3.Connection, usuario_id: int) -> bool:
    return rol(conexion, usuario_id) == ADMIN
