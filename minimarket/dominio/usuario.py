"""Usuarios, roles y permisos (RF-56 a RF-60).

Capa de dominio: no importa `datos/`, `ui/` ni `infra/`.

La tabla de permisos es la seccion 6 de docs/reglas-de-negocio.md, escrita una
sola vez y en un solo lugar. Quien la hace cumplir es `servicios/usuarios.py`
(RF-58): esconder un boton no es un control de acceso.

El hash de la clave vive aca porque es calculo puro sobre la biblioteca
estandar; guardarlo es tarea de `datos/`.
"""

import hashlib
import secrets
from dataclasses import dataclass

ADMIN = "ADMIN"
CAJERO = "CAJERO"
ROLES = [ADMIN, CAJERO]

NOMBRE_ROL = {ADMIN: "Administrador", CAJERO: "Cajero"}

# --- Operaciones controladas (seccion 6 de las reglas) ----------------------

VENDER = "VENDER"
OPERAR_CAJA = "OPERAR_CAJA"
VER_EXISTENCIAS = "VER_EXISTENCIAS"
VER_COSTOS = "VER_COSTOS"
MODIFICAR_PRECIOS = "MODIFICAR_PRECIOS"
REGISTRAR_COMPRAS = "REGISTRAR_COMPRAS"
AJUSTAR_INVENTARIO = "AJUSTAR_INVENTARIO"
REGISTRAR_PERDIDAS = "REGISTRAR_PERDIDAS"
ANULAR_VENTAS = "ANULAR_VENTAS"
REPORTES_GANANCIA = "REPORTES_GANANCIA"
VER_REPORTES = "VER_REPORTES"
REPORTE_CIERRE = "REPORTE_CIERRE"
GESTIONAR_USUARIOS = "GESTIONAR_USUARIOS"
CARGAR_TASA = "CARGAR_TASA"
CONFIGURAR = "CONFIGURAR"

# Roles habilitados para cada operacion, y como se nombra la operacion cuando
# hay que negarla en pantalla.
#
# `VER_REPORTES` no figura en la seccion 6, que solo nombra los reportes de
# ganancia. Se agrega para el reporte de ventas del periodo, el inventario
# valorizado y el libro de ventas: los tres exponen el movimiento completo del
# negocio y ninguno es necesario para atender la caja. El cierre de la propia
# sesion (RF-51) queda abierto al cajero, como pide la tabla.
PERMISOS: dict[str, tuple[frozenset[str], str]] = {
    VENDER: (frozenset({ADMIN, CAJERO}), "registrar ventas"),
    OPERAR_CAJA: (frozenset({ADMIN, CAJERO}), "abrir y cerrar la caja"),
    VER_EXISTENCIAS: (frozenset({ADMIN, CAJERO}), "consultar existencias"),
    VER_COSTOS: (frozenset({ADMIN}), "ver costos y margenes"),
    MODIFICAR_PRECIOS: (frozenset({ADMIN}), "modificar precios y el catalogo"),
    REGISTRAR_COMPRAS: (frozenset({ADMIN}), "registrar compras"),
    AJUSTAR_INVENTARIO: (frozenset({ADMIN}), "ajustar el inventario"),
    REGISTRAR_PERDIDAS: (frozenset({ADMIN}), "registrar perdidas"),
    ANULAR_VENTAS: (frozenset({ADMIN}), "anular ventas"),
    REPORTES_GANANCIA: (frozenset({ADMIN}), "consultar reportes de ganancia"),
    VER_REPORTES: (frozenset({ADMIN}), "consultar los reportes del negocio"),
    REPORTE_CIERRE: (frozenset({ADMIN, CAJERO}), "ver el cierre de su sesion"),
    GESTIONAR_USUARIOS: (frozenset({ADMIN}), "gestionar usuarios"),
    CARGAR_TASA: (frozenset({ADMIN}), "cargar la tasa del dia"),
    CONFIGURAR: (frozenset({ADMIN}), "configurar el sistema"),
}


def puede(rol: str, operacion: str) -> bool:
    """RF-58. Si la operacion no esta en la tabla, no la puede nadie."""
    roles, _ = PERMISOS.get(operacion, (frozenset(), ""))
    return rol in roles


def describir(operacion: str) -> str:
    """Como se nombra la operacion en el mensaje que ve el usuario."""
    _, descripcion = PERMISOS.get(operacion, (frozenset(), operacion.lower()))
    return descripcion


@dataclass
class Usuario:
    """RF-57. Dos perfiles y nada mas: administrador y cajero."""

    usuario: str
    nombre: str
    rol: str = CAJERO
    activo: bool = True
    creado_en: str | None = None
    id: int | None = None

    @property
    def es_administrador(self) -> bool:
        return self.rol == ADMIN

    def puede(self, operacion: str) -> bool:
        return puede(self.rol, operacion)


# --- Clave (RF-60) ----------------------------------------------------------

# Parametros de scrypt. 128 x N x r = 16 MiB de memoria por verificacion, que
# en este equipo tarda decimas de segundo y encarece muchisimo probar claves a
# ciegas. Van guardados junto al hash para que subirlos no invalide las claves
# ya establecidas.
_N = 2**14
_R = 8
_P = 1
_LARGO = 32
_SAL = 16


def hashear_clave(clave: str, sal: bytes | None = None) -> str:
    """RF-60. Derivacion con sal aleatoria; el resultado se guarda como texto.

    Formato: `scrypt$N$r$p$sal_hex$hash_hex`. Nunca un hash simple: una tabla
    de SHA-256 de claves de cuatro digitos se arma en un segundo.
    """
    if not clave:
        raise ValueError("La clave no puede estar vacia.")
    sal = sal if sal is not None else secrets.token_bytes(_SAL)
    derivada = hashlib.scrypt(
        clave.encode("utf-8"), salt=sal, n=_N, r=_R, p=_P, dklen=_LARGO
    )
    return f"scrypt${_N}${_R}${_P}${sal.hex()}${derivada.hex()}"


def verificar_clave(clave: str, guardado: str) -> bool:
    """RF-56. Compara en tiempo constante contra el hash almacenado.

    Un `hash_clave` vacio o ilegible no autentica nunca: asi queda el usuario
    semilla de `esquema.sql` hasta que se le establece una clave.
    """
    partes = guardado.split("$")
    if len(partes) != 6 or partes[0] != "scrypt":
        return False
    _, n, r, p, sal, esperado = partes
    try:
        derivada = hashlib.scrypt(
            clave.encode("utf-8"),
            salt=bytes.fromhex(sal),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(esperado) // 2,
        )
    except (ValueError, MemoryError):
        return False
    return secrets.compare_digest(derivada.hex(), esperado)
