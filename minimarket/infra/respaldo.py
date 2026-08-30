"""Respaldo y restauracion de la base (RF-61 a RF-63).

Siempre `conexion.backup(destino)`, NUNCA copia de archivo: con WAL activo las
ultimas transacciones viven en el `-wal` y copiar el `.db` solo se lleva una
base vieja o rota. La API de sqlite3 toma un punto consistente sin frenar la
caja.

Un fallo no levanta excepcion: devuelve un `Registro` en estado ERROR, que es
lo que la tabla `respaldo` guarda y lo que el administrador tiene que ver
(RF-62). Que la unidad externa no este conectada es lo normal, no un error de
programa.
"""

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from minimarket.datos.conexion import transaccion
from minimarket.infra import bitacora

OK = "OK"
ERROR = "ERROR"

FORMATO_NOMBRE = "minimarket-%Y%m%d-%H%M%S.db"


@dataclass(frozen=True)
class Registro:
    """Una fila de la tabla `respaldo` (RF-62)."""

    id: int | None
    fecha_hora: str
    ruta: str
    tamano_bytes: int | None
    estado: str
    mensaje: str | None

    @property
    def ok(self) -> bool:
        return self.estado == OK


def ejecutar(conexion: sqlite3.Connection, carpeta: str) -> Registro:
    """RF-61 / RF-62. Respalda hacia `carpeta` y deja constancia del intento."""
    if not carpeta.strip():
        return _registrar(
            conexion,
            "",
            None,
            ERROR,
            "No hay carpeta de respaldo configurada.",
        )
    destino = Path(carpeta) / datetime.now().strftime(FORMATO_NOMBRE)
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        copia = sqlite3.connect(str(destino))
        try:
            conexion.backup(copia)
        finally:
            copia.close()
    except (OSError, sqlite3.Error) as error:
        # RNF-09. El mensaje que se guarda y se muestra dice que hacer; el
        # detalle del sistema operativo queda en la bitacora (RNF-13).
        bitacora.anotar(f"Fallo el respaldo hacia {destino}", error)
        return _registrar(
            conexion,
            str(destino),
            None,
            ERROR,
            "No se pudo escribir en la carpeta de respaldo. Revisa que la "
            "unidad este conectada y que la carpeta configurada exista.",
        )
    return _registrar(conexion, str(destino), destino.stat().st_size, OK, None)


def restaurar(conexion: sqlite3.Connection, origen: str) -> None:
    """RF-63. Vuelca el respaldo SOBRE la base viva, sin tocar archivos.

    `backup` en este sentido reemplaza el contenido de la base abierta: la
    conexion sigue sirviendo despues, y el `-wal` queda coherente solo. Copiar
    el archivo encima con la aplicacion abierta seria justo lo que WAL prohibe.

    Todo lo que la base tenga ahora se pierde. Quien confirma es el usuario.
    """
    ruta = Path(origen)
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encuentra el archivo de respaldo: {origen}")
    fuente = sqlite3.connect(f"file:{ruta.as_posix()}?mode=ro", uri=True)
    try:
        if not _parece_la_base(fuente):
            raise ValueError(
                "El archivo elegido no es un respaldo de este sistema."
            )
        fuente.backup(conexion)
    finally:
        fuente.close()


def ultimo(conexion: sqlite3.Connection) -> Registro | None:
    filas = listar(conexion, limite=1)
    return filas[0] if filas else None


def hubo_hoy(conexion: sqlite3.Connection) -> bool:
    """RF-61. Si ya corrio con exito hoy, no hace falta repetirlo."""
    fila = conexion.execute(
        "SELECT 1 FROM respaldo WHERE estado = ? AND date(fecha_hora) = ? LIMIT 1",
        (OK, date.today().isoformat()),
    ).fetchone()
    return fila is not None


def listar(conexion: sqlite3.Connection, limite: int = 60) -> list[Registro]:
    return [
        Registro(
            id=f["id"],
            fecha_hora=f["fecha_hora"],
            ruta=f["ruta"],
            tamano_bytes=f["tamano_bytes"],
            estado=f["estado"],
            mensaje=f["mensaje"],
        )
        for f in conexion.execute(
            """SELECT id, fecha_hora, ruta, tamano_bytes, estado, mensaje
                 FROM respaldo ORDER BY id DESC LIMIT ?""",
            (limite,),
        )
    ]


def _parece_la_base(fuente: sqlite3.Connection) -> bool:
    """Un .db cualquiera no sirve: se busca el esqueleto de este sistema."""
    tablas = {
        f[0]
        for f in fuente.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    return {"venta", "producto", "movimiento_inventario", "usuario"} <= tablas


def _registrar(
    conexion: sqlite3.Connection,
    ruta: str,
    tamano: int | None,
    estado: str,
    mensaje: str | None,
) -> Registro:
    """RF-62. Cada intento queda registrado, haya salido bien o mal."""
    with transaccion(conexion):
        identificador = conexion.execute(
            """INSERT INTO respaldo (ruta, tamano_bytes, estado, mensaje)
               VALUES (?, ?, ?, ?)""",
            (ruta, tamano, estado, mensaje),
        ).lastrowid
    fila = conexion.execute(
        "SELECT fecha_hora FROM respaldo WHERE id = ?", (identificador,)
    ).fetchone()
    return Registro(identificador, fila[0], ruta, tamano, estado, mensaje)
