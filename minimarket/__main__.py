"""Punto de entrada: `python -m minimarket`.

Aca se arma la aplicacion: se abre la base y se le entrega a la interfaz. Es
el unico lugar que conoce las dos capas a la vez; las pantallas reciben la
conexion ya abierta y no saben de donde salio.
"""

import sys

from minimarket.datos import conexion as datos_conexion
from minimarket.infra import rutas
from minimarket.ui.principal import main


def arrancar() -> int:
    return main(datos_conexion.abrir(rutas.base_de_datos()))


if __name__ == "__main__":
    sys.exit(arrancar())
