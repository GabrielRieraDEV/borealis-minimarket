"""Casos de uso. La interfaz entra por aca y nunca toca `datos/`."""

from minimarket.dominio.usuario import Usuario

# El `admin` que siembra esquema.sql. Firma las operaciones cuando no hay
# sesion iniciada: las pruebas y los scripts de carga corren sin pantalla de
# ingreso, y `movimiento_inventario.usuario_id` es NOT NULL.
USUARIO_SEMILLA = 1

_sesion: Usuario | None = None


class ErrorServicio(Exception):
    """Falla previsible, con el mensaje ya redactado para el usuario (RNF-09).

    Todas las excepciones de esta capa heredan de aca, para que una pantalla
    pueda atrapar una sola cosa y mostrarla tal cual.
    """


def iniciar_sesion(usuario: Usuario) -> None:
    """RF-56. Desde aca, las operaciones quedan firmadas por este usuario."""
    global _sesion
    _sesion = usuario


def cerrar_sesion() -> None:
    global _sesion
    _sesion = None


def sesion() -> Usuario | None:
    """El usuario autenticado, o None si todavia no se inicio sesion."""
    return _sesion


def usuario_actual() -> int:
    """Id que firma la operacion en curso."""
    return _sesion.id if _sesion is not None else USUARIO_SEMILLA
