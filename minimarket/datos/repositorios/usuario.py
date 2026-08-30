"""Repositorio de usuarios (RF-56, RF-57, RF-60).

El `hash_clave` no viaja dentro de la entidad `Usuario`: se pide aparte con
`hash_de` y solo lo lee la autenticacion. Asi no queda dando vueltas por las
pantallas ni en un `repr` de depuracion.
"""

import sqlite3

from minimarket.dominio.usuario import ADMIN, Usuario

_CAMPOS = "id, usuario, nombre, rol, activo, creado_en"


def _entidad(fila: sqlite3.Row) -> Usuario:
    return Usuario(
        id=fila["id"],
        usuario=fila["usuario"],
        nombre=fila["nombre"],
        rol=fila["rol"],
        activo=bool(fila["activo"]),
        creado_en=fila["creado_en"],
    )


def rol(conexion: sqlite3.Connection, usuario_id: int) -> str | None:
    """RF-58. El rol del usuario activo; None si no existe o esta de baja."""
    fila = conexion.execute(
        "SELECT rol FROM usuario WHERE id = ? AND activo = 1", (usuario_id,)
    ).fetchone()
    return fila[0] if fila else None


def es_administrador(conexion: sqlite3.Connection, usuario_id: int) -> bool:
    return rol(conexion, usuario_id) == ADMIN


def obtener(conexion: sqlite3.Connection, usuario_id: int) -> Usuario | None:
    fila = conexion.execute(
        f"SELECT {_CAMPOS} FROM usuario WHERE id = ?", (usuario_id,)
    ).fetchone()
    return _entidad(fila) if fila else None


def por_nombre(conexion: sqlite3.Connection, usuario: str) -> Usuario | None:
    """RF-56. El nombre de usuario es unico; con eso entra al sistema."""
    fila = conexion.execute(
        f"SELECT {_CAMPOS} FROM usuario WHERE usuario = ?", (usuario,)
    ).fetchone()
    return _entidad(fila) if fila else None


def listar(conexion: sqlite3.Connection, solo_activos: bool = False) -> list[Usuario]:
    sql = f"SELECT {_CAMPOS} FROM usuario"
    if solo_activos:
        sql += " WHERE activo = 1"
    return [_entidad(f) for f in conexion.execute(sql + " ORDER BY usuario")]


def hash_de(conexion: sqlite3.Connection, usuario_id: int) -> str:
    """RF-60. Devuelve cadena vacia si el usuario no tiene clave establecida."""
    fila = conexion.execute(
        "SELECT hash_clave FROM usuario WHERE id = ?", (usuario_id,)
    ).fetchone()
    return fila[0] if fila else ""


def crear(conexion: sqlite3.Connection, usuario: Usuario, hash_clave: str) -> int:
    return conexion.execute(
        """INSERT INTO usuario (usuario, nombre, hash_clave, rol, activo)
           VALUES (?, ?, ?, ?, ?)""",
        (
            usuario.usuario,
            usuario.nombre,
            hash_clave,
            usuario.rol,
            int(usuario.activo),
        ),
    ).lastrowid


def actualizar(conexion: sqlite3.Connection, usuario: Usuario) -> None:
    """Nombre visible, rol y estado. La clave va por `cambiar_clave`."""
    conexion.execute(
        "UPDATE usuario SET usuario = ?, nombre = ?, rol = ?, activo = ? WHERE id = ?",
        (
            usuario.usuario,
            usuario.nombre,
            usuario.rol,
            int(usuario.activo),
            usuario.id,
        ),
    )


def cambiar_clave(
    conexion: sqlite3.Connection, usuario_id: int, hash_clave: str
) -> None:
    conexion.execute(
        "UPDATE usuario SET hash_clave = ? WHERE id = ?", (hash_clave, usuario_id)
    )


def cambiar_estado(
    conexion: sqlite3.Connection, usuario_id: int, activo: bool
) -> None:
    """RF-02 vale igual aca: el usuario no se borra, se da de baja."""
    conexion.execute(
        "UPDATE usuario SET activo = ? WHERE id = ?", (int(activo), usuario_id)
    )


def administradores_activos(conexion: sqlite3.Connection) -> int:
    """Cuantos quedan. Sin ninguno el sistema se vuelve inadministrable."""
    return conexion.execute(
        "SELECT COUNT(*) FROM usuario WHERE rol = ? AND activo = 1", (ADMIN,)
    ).fetchone()[0]
