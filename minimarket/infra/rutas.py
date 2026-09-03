"""Donde vive cada cosa en el disco.

La base NO puede quedar dentro de Program Files: ahi el usuario no escribe y
SQLite no podria abrirla. El instalador de la Fase 6 crea la carpeta del
usuario y esta funcion la encuentra igual, este o no empaquetada la aplicacion.

`MINIMARKET_DB` la cambia de lugar, que es como las pruebas y la base de
demostracion trabajan sin tocar la real.
"""

import os
import sys
from pathlib import Path

CARPETA = "Minimarket"
ARCHIVO = "minimarket.db"
BITACORA = "minimarket.log"


def base_de_datos() -> Path:
    """Ruta del archivo de la base, creando su carpeta si hace falta."""
    variable = os.environ.get("MINIMARKET_DB")
    if variable:
        return Path(variable)
    carpeta = Path.home() / CARPETA
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta / ARCHIVO


def bitacora() -> Path:
    """RNF-13. El archivo de errores, al lado de la base."""
    return base_de_datos().with_name(BITACORA)


def recurso(nombre: str) -> Path:
    """Un archivo de `recursos/`, este o no empaquetada la aplicacion.

    PyInstaller descomprime los datos en `sys._MEIPASS`; desde el codigo fuente
    la carpeta es la raiz del repositorio, dos niveles arriba de este archivo.
    """
    raiz = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return raiz / "recursos" / nombre


def icono() -> Path:
    return recurso("minimarket.ico")


def logo() -> Path:
    return recurso("logo.png")
