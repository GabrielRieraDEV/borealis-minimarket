"""Autenticacion, alta y baja de usuarios, y control de permisos.

RF-56 a RF-60 y la seccion 6 de docs/reglas-de-negocio.md.

`exigir` es el unico control de acceso del sistema. La interfaz ademas esconde
lo que el cajero no puede usar, pero eso es comodidad: el permiso se verifica
aca, asi que llegar a una pantalla por otro camino no alcanza (RF-58).
"""

import sqlite3

from minimarket.datos.conexion import transaccion
from minimarket.datos.repositorios import usuario as repo_usuario
from minimarket.dominio.usuario import (
    ADMIN,
    GESTIONAR_USUARIOS,
    ROLES,
    Usuario,
    describir,
    hashear_clave,
    puede,
    verificar_clave,
)
from minimarket.infra import auditoria
from minimarket.servicios import (
    ErrorServicio,
    cerrar_sesion,
    iniciar_sesion,
    usuario_actual,
)

LARGO_MINIMO_CLAVE = 4


class ErrorUsuario(ErrorServicio):
    """Falla previsible de la gestion de usuarios."""


class ErrorPermiso(ErrorServicio):
    """RF-58. El perfil no alcanza para la operacion pedida."""


# --- Permisos (RF-58) -------------------------------------------------------


def exigir(
    conexion: sqlite3.Connection, operacion: str, usuario_id: int | None = None
) -> None:
    """RF-58. Corta la operacion si el rol no la tiene habilitada."""
    identificador = usuario_id if usuario_id is not None else usuario_actual()
    rol = repo_usuario.rol(conexion, identificador)
    if rol is None:
        raise ErrorPermiso("El usuario no existe o esta dado de baja.")
    if not puede(rol, operacion):
        raise ErrorPermiso(
            f"El perfil de {rol.lower()} no tiene permiso para {describir(operacion)}."
        )


def tiene_permiso(
    conexion: sqlite3.Connection, operacion: str, usuario_id: int | None = None
) -> bool:
    """Misma pregunta sin excepcion, para que la interfaz esconda los botones."""
    identificador = usuario_id if usuario_id is not None else usuario_actual()
    rol = repo_usuario.rol(conexion, identificador)
    return rol is not None and puede(rol, operacion)


# --- Autenticacion (RF-56) --------------------------------------------------


def autenticar(conexion: sqlite3.Connection, usuario: str, clave: str) -> Usuario:
    """RF-56. Deja la sesion iniciada y devuelve el usuario autenticado.

    El mensaje de error no distingue entre usuario inexistente y clave
    equivocada: decir cual de los dos fallo regala la mitad del trabajo.
    """
    registro = repo_usuario.por_nombre(conexion, usuario.strip())
    if (
        registro is None
        or not registro.activo
        or not verificar_clave(clave, repo_usuario.hash_de(conexion, registro.id))
    ):
        raise ErrorUsuario("Usuario o clave incorrectos.")
    iniciar_sesion(registro)
    return registro


def salir() -> None:
    cerrar_sesion()


def verificar(conexion: sqlite3.Connection, usuario: str, clave: str) -> Usuario:
    """RN-25. Comprueba una clave SIN cambiar la sesion en curso.

    Es la autorizacion que el administrador da parado detras del cajero: anular
    una venta o vender sin existencia.
    """
    registro = repo_usuario.por_nombre(conexion, usuario.strip())
    if (
        registro is None
        or not registro.activo
        or not verificar_clave(clave, repo_usuario.hash_de(conexion, registro.id))
    ):
        raise ErrorUsuario("Usuario o clave incorrectos.")
    return registro


def necesita_clave_inicial(conexion: sqlite3.Connection) -> Usuario | None:
    """El `admin` semilla mientras no tenga clave; None si ya la tiene.

    `esquema.sql` lo crea con `hash_clave` vacio, que no autentica. Sin esto la
    aplicacion no tendria por donde entrar. La Fase 6 lo hace desde el
    asistente de primer arranque y esta funcion queda igual.
    """
    registro = repo_usuario.por_nombre(conexion, "admin")
    if registro is None or repo_usuario.hash_de(conexion, registro.id):
        return None
    return registro


def establecer_clave_inicial(conexion: sqlite3.Connection, clave: str) -> Usuario:
    """Le pone clave al `admin` semilla. Solo funciona si todavia no tiene."""
    registro = necesita_clave_inicial(conexion)
    if registro is None:
        raise ErrorUsuario("El administrador ya tiene una clave establecida.")
    _validar_clave(clave)
    with transaccion(conexion):
        repo_usuario.cambiar_clave(conexion, registro.id, hashear_clave(clave))
    return registro


# --- Gestion (RF-57, RF-59, RF-60) ------------------------------------------


def listar(conexion: sqlite3.Connection) -> list[Usuario]:
    exigir(conexion, GESTIONAR_USUARIOS)
    return repo_usuario.listar(conexion)


def obtener(conexion: sqlite3.Connection, usuario_id: int) -> Usuario | None:
    return repo_usuario.obtener(conexion, usuario_id)


def crear(conexion: sqlite3.Connection, usuario: Usuario, clave: str) -> int:
    """RF-57 / RF-60. Alta con clave derivada y sal."""
    exigir(conexion, GESTIONAR_USUARIOS)
    _validar(usuario)
    _validar_clave(clave)
    autor = usuario_actual()
    with transaccion(conexion):
        try:
            identificador = repo_usuario.crear(
                conexion, usuario, hashear_clave(clave)
            )
        except sqlite3.IntegrityError as error:
            raise ErrorUsuario(
                f"Ya existe un usuario «{usuario.usuario}»."
            ) from error
        auditoria.registrar(
            conexion,
            autor,
            auditoria.ALTA_USUARIO,
            "usuario",
            identificador,
            despues={"usuario": usuario.usuario, "rol": usuario.rol},
        )
    return identificador


def modificar(conexion: sqlite3.Connection, usuario: Usuario) -> None:
    """RF-57. Cambia nombre, rol y estado; la clave va aparte."""
    exigir(conexion, GESTIONAR_USUARIOS)
    if usuario.id is None:
        raise ErrorUsuario("No se puede modificar un usuario que no fue guardado.")
    _validar(usuario)
    anterior = repo_usuario.obtener(conexion, usuario.id)
    if anterior is None:
        raise ErrorUsuario("El usuario ya no existe.")
    _cuidar_ultimo_administrador(conexion, anterior, usuario)
    autor = usuario_actual()
    with transaccion(conexion):
        try:
            repo_usuario.actualizar(conexion, usuario)
        except sqlite3.IntegrityError as error:
            raise ErrorUsuario(
                f"Ya existe un usuario «{usuario.usuario}»."
            ) from error
        auditoria.registrar(
            conexion,
            autor,
            auditoria.CAMBIO_USUARIO,
            "usuario",
            usuario.id,
            antes={
                "usuario": anterior.usuario,
                "nombre": anterior.nombre,
                "rol": anterior.rol,
                "activo": anterior.activo,
            },
            despues={
                "usuario": usuario.usuario,
                "nombre": usuario.nombre,
                "rol": usuario.rol,
                "activo": usuario.activo,
            },
        )


def cambiar_estado(
    conexion: sqlite3.Connection, usuario_id: int, activo: bool
) -> None:
    """Baja logica. Nada se borra (regla 6 de CLAUDE.md)."""
    registro = repo_usuario.obtener(conexion, usuario_id)
    if registro is None:
        raise ErrorUsuario("El usuario ya no existe.")
    registro.activo = activo
    modificar(conexion, registro)


def cambiar_clave(
    conexion: sqlite3.Connection, usuario_id: int, clave: str
) -> None:
    """RF-60. La propia se cambia sin permiso especial; la ajena, no."""
    autor = usuario_actual()
    if usuario_id != autor:
        exigir(conexion, GESTIONAR_USUARIOS)
    if repo_usuario.obtener(conexion, usuario_id) is None:
        raise ErrorUsuario("El usuario ya no existe.")
    _validar_clave(clave)
    with transaccion(conexion):
        repo_usuario.cambiar_clave(conexion, usuario_id, hashear_clave(clave))
        # El asiento no guarda la clave ni su hash: solo que alguien la cambio.
        auditoria.registrar(
            conexion, autor, auditoria.CAMBIO_CLAVE, "usuario", usuario_id
        )


# --- Validacion -------------------------------------------------------------


def _validar(usuario: Usuario) -> None:
    if not usuario.usuario.strip():
        raise ErrorUsuario("El usuario necesita un nombre de ingreso.")
    if not usuario.nombre.strip():
        raise ErrorUsuario("El usuario necesita un nombre visible.")
    if usuario.rol not in ROLES:
        raise ErrorUsuario("Elegi un perfil valido: administrador o cajero.")


def _validar_clave(clave: str) -> None:
    if len(clave) < LARGO_MINIMO_CLAVE:
        raise ErrorUsuario(
            f"La clave necesita al menos {LARGO_MINIMO_CLAVE} caracteres."
        )


def _cuidar_ultimo_administrador(
    conexion: sqlite3.Connection, anterior: Usuario, nuevo: Usuario
) -> None:
    """Sin administrador activo el sistema queda sin quien lo administre."""
    perdia_el_rol = anterior.rol == ADMIN and anterior.activo
    sigue_siendo = nuevo.rol == ADMIN and nuevo.activo
    if perdia_el_rol and not sigue_siendo:
        if repo_usuario.administradores_activos(conexion) <= 1:
            raise ErrorUsuario(
                "Es el unico administrador activo. Nombra otro antes de darlo "
                "de baja o cambiarle el perfil."
            )
