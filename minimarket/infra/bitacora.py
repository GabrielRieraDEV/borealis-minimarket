"""Bitacora de errores en archivo, para diagnostico remoto (RNF-13).

Dos cosas y ninguna mas:

- `configurar` engancha `logging` a un archivo con rotacion. Los modulos que ya
  usaban `logging.getLogger(__name__)` —la tasa BCV, la impresora— empiezan a
  escribir ahi sin cambiar una linea.
- `anotar` es el otro lado de RNF-09: el detalle tecnico del sistema operativo
  va al archivo y al usuario se le muestra que hacer. Sin este par, o el
  mensaje asusta o el problema no se puede diagnosticar por telefono.

Una excepcion no controlada no cierra la aplicacion: se registra y se avisa.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import Callable

FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"
TAMANO_MAXIMO = 1_000_000  # ~1 MB por archivo
COPIAS = 3

_bitacora = logging.getLogger("minimarket")


def configurar(
    archivo: Path, avisar: Callable[[Path], None] | None = None
) -> Path:
    """Manda `logging` al archivo y atrapa lo que nadie atrapo.

    `avisar` recibe la ruta de la bitacora cuando revienta algo no previsto;
    es la interfaz la que sabe como mostrarlo, aca no se importa Qt.
    """
    archivo.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format=FORMATO,
        handlers=[
            RotatingFileHandler(
                archivo,
                maxBytes=TAMANO_MAXIMO,
                backupCount=COPIAS,
                encoding="utf-8",
            )
        ],
        force=True,
    )
    sys.excepthook = _manejador(archivo, avisar)
    return archivo


def anotar(mensaje: str, error: BaseException) -> None:
    """RNF-09. Guarda el detalle tecnico que NO se le muestra al usuario."""
    _bitacora.error("%s: %s", mensaje, error, exc_info=error)


def _manejador(archivo: Path, avisar: Callable[[Path], None] | None):
    def no_controlada(
        tipo: type[BaseException],
        valor: BaseException,
        traza: TracebackType | None,
    ) -> None:
        if issubclass(tipo, KeyboardInterrupt):
            sys.__excepthook__(tipo, valor, traza)
            return
        _bitacora.critical("Error no controlado", exc_info=(tipo, valor, traza))
        if avisar is not None:
            try:
                avisar(archivo)
            except Exception:  # avisar fallando no puede tumbar el manejador
                _bitacora.exception("No se pudo mostrar el aviso de error")

    return no_controlada
