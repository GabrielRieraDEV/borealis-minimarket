"""Configuracion del sistema y respaldo (RF-61 a RF-64).

Los datos fiscales, el redondeo, la impresora y la ruta de respaldo viven en la
tabla `configuracion` como pares de texto. `CAMPOS` es lo que la pantalla
dibuja: agregar una clave es agregar un renglon aca y en `esquema.sql`.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from minimarket.datos.conexion import transaccion
from minimarket.datos.repositorios import configuracion as repo_configuracion
from minimarket.dominio.usuario import CONFIGURAR
from minimarket.infra import auditoria, respaldo as infra_respaldo
from minimarket.servicios import ErrorServicio, usuario_actual
from minimarket.servicios import usuarios as servicio_usuarios


class ErrorConfiguracion(ErrorServicio):
    """Falla previsible, con mensaje listo para mostrar en pantalla."""


@dataclass(frozen=True)
class Campo:
    """Una clave configurable y como se presenta (RF-64)."""

    clave: str
    etiqueta: str
    ayuda: str = ""
    numerico: bool = False


CAMPOS: list[Campo] = [
    Campo("negocio.nombre", "Razon social", "Encabeza notas y reportes"),
    Campo("negocio.rif", "RIF"),
    Campo("negocio.direccion", "Direccion fiscal"),
    Campo("negocio.telefono", "Telefono"),
    Campo(
        "precio.redondeo_bs",
        "Redondeo del precio en Bs",
        "Multiplo al que se redondea hacia arriba el precio al publico (RN-10)",
        numerico=True,
    ),
    Campo(
        "vencimiento.dias_aviso",
        "Dias de aviso de vencimiento",
        "Valor por defecto para los productos nuevos",
        numerico=True,
    ),
    Campo(
        "impresora.destino",
        "Impresora",
        "Nombre en Windows o ruta del dispositivo. Vacio: no se imprime",
    ),
    Campo("respaldo.ruta", "Carpeta de respaldo", "La unidad externa (RF-61)"),
    Campo("respaldo.hora", "Hora del respaldo", "A partir de esa hora, HH:MM"),
    Campo("bcv.url", "Origen de la tasa BCV", "Vacio: usa el sitio oficial"),
]


def leer_todo(conexion: sqlite3.Connection) -> dict[str, str]:
    """Los valores actuales de las claves que la pantalla muestra."""
    return {
        campo.clave: repo_configuracion.leer(conexion, campo.clave)
        for campo in CAMPOS
    }


def guardar(conexion: sqlite3.Connection, valores: dict[str, str]) -> None:
    """RF-64. Guarda solo lo que cambio y lo deja en la bitacora (RF-59)."""
    servicio_usuarios.exigir(conexion, CONFIGURAR)
    anterior = leer_todo(conexion)
    conocidos = {campo.clave: campo for campo in CAMPOS}
    cambios = {}
    for clave, valor in valores.items():
        campo = conocidos.get(clave)
        if campo is None:
            raise ErrorConfiguracion(f"La clave «{clave}» no es configurable.")
        valor = valor.strip()
        if campo.numerico and valor:
            _validar_numero(campo, valor)
        if valor != anterior.get(clave, ""):
            cambios[clave] = valor
    if not cambios:
        return
    autor = usuario_actual()
    with transaccion(conexion):
        for clave, valor in cambios.items():
            repo_configuracion.escribir(conexion, clave, valor)
        auditoria.registrar(
            conexion,
            autor,
            auditoria.CAMBIO_CONFIGURACION,
            "configuracion",
            antes={c: anterior.get(c, "") for c in cambios},
            despues=cambios,
        )


def datos_del_negocio(conexion: sqlite3.Connection) -> dict[str, str]:
    """RF-64. El encabezado que llevan la nota de entrega y los PDF."""
    return {
        clave: repo_configuracion.leer(conexion, f"negocio.{clave}")
        for clave in ("nombre", "rif", "direccion", "telefono")
    }


# --- Respaldo (RF-61 a RF-63) -----------------------------------------------


def respaldar(conexion: sqlite3.Connection) -> infra_respaldo.Registro:
    """RF-61. Respaldo a pedido, hacia la carpeta configurada."""
    servicio_usuarios.exigir(conexion, CONFIGURAR)
    return infra_respaldo.ejecutar(
        conexion, repo_configuracion.leer(conexion, "respaldo.ruta")
    )


def respaldo_automatico(
    conexion: sqlite3.Connection, ahora: str | None = None
) -> infra_respaldo.Registro | None:
    """RF-61. El respaldo diario, disparado al arrancar la aplicacion.

    ponytail: no hay hilo ni programador de tareas. El equipo es uno solo y se
    apaga todas las noches, asi que «una vez por dia» se resuelve preguntando
    al arrancar si ya hubo uno hoy y si paso la hora configurada. Si alguna vez
    hace falta respaldar con la aplicacion abierta toda la noche, entra un
    QTimer en la ventana principal y esta funcion no cambia.

    No pide permiso: lo dispara el sistema, no el usuario. Devuelve None si no
    correspondia; el `Registro` con estado ERROR es lo que hay que avisarle al
    administrador (RF-62).
    """
    ruta = repo_configuracion.leer(conexion, "respaldo.ruta")
    if not ruta or infra_respaldo.hubo_hoy(conexion):
        return None
    hora = repo_configuracion.leer(conexion, "respaldo.hora", "22:00")
    if (ahora or _hora_actual()) < hora:
        return None
    return infra_respaldo.ejecutar(conexion, ruta)


def restaurar(conexion: sqlite3.Connection, origen: str) -> None:
    """RF-63. Reemplaza la base con la del respaldo elegido.

    El asiento de auditoria se escribe DESPUES, o sea sobre la base ya
    restaurada: es la unica que va a seguir existiendo.
    """
    servicio_usuarios.exigir(conexion, CONFIGURAR)
    autor = usuario_actual()
    try:
        infra_respaldo.restaurar(conexion, origen)
    except (OSError, ValueError, sqlite3.Error) as error:
        raise ErrorConfiguracion(
            f"No se pudo restaurar el respaldo: {error}"
        ) from error
    with transaccion(conexion):
        auditoria.registrar(
            conexion,
            autor,
            auditoria.RESTAURACION,
            "respaldo",
            despues={"origen": origen},
        )


def ultimo_respaldo(conexion: sqlite3.Connection) -> infra_respaldo.Registro | None:
    """RF-62. El ultimo intento, para el panel de alertas."""
    servicio_usuarios.exigir(conexion, CONFIGURAR)
    return infra_respaldo.ultimo(conexion)


def historial(conexion: sqlite3.Connection) -> list[infra_respaldo.Registro]:
    """RF-62. Todos los intentos, con su resultado."""
    servicio_usuarios.exigir(conexion, CONFIGURAR)
    return infra_respaldo.listar(conexion)


def _hora_actual() -> str:
    return datetime.now().strftime("%H:%M")


def _validar_numero(campo: Campo, valor: str) -> None:
    try:
        numero = Decimal(valor.replace(",", "."))
    except InvalidOperation as error:
        raise ErrorConfiguracion(
            f"{campo.etiqueta} tiene que ser un numero."
        ) from error
    if numero <= 0:
        raise ErrorConfiguracion(f"{campo.etiqueta} tiene que ser mayor que cero.")
