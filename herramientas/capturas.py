"""Capturas de pantalla para el manual de usuario (punto 8 de la Fase 6).

    python -m herramientas.demostracion
    python -m herramientas.capturas

Arma cada pantalla sobre la base de demostracion y la guarda en
`docs/capturas/`. Se hace por programa y no a mano para que las imagenes del
manual se puedan rehacer cuando la interfaz cambie, en vez de envejecer.

`QWidget.grab()` dibuja el widget en una imagen sin necesidad de mostrarlo, asi
que no hay ventanas parpadeando ni un orden de clics que respetar.
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from minimarket.datos.conexion import abrir

DESTINO = Path("docs/capturas")
TAMANO = (1060, 660)


def main() -> int:
    from minimarket.infra import rutas
    from minimarket.servicios import iniciar_sesion
    from minimarket.servicios import usuarios as servicio_usuarios
    from minimarket.ui.compras import PantallaCompras
    from minimarket.ui.inicio import PantallaInicio
    from minimarket.ui.inventario import PantallaExistencias
    from minimarket.ui.perdidas import PantallaPerdidas
    from minimarket.ui.reportes import PantallaReportes
    from minimarket.ui.venta import PantallaVenta

    base = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else rutas.base_de_datos().with_name("demostracion.db")
    )
    if not base.is_file():
        print(f"Falta la base de demostracion: {base}")
        print("Corre primero: python -m herramientas.demostracion")
        return 1

    aplicacion = QApplication(sys.argv)  # noqa: F841  (lo pide Qt para dibujar)
    conexion = abrir(base)
    iniciar_sesion(servicio_usuarios.obtener(conexion, 1))

    DESTINO.mkdir(parents=True, exist_ok=True)
    pantallas = [
        ("inicio", PantallaInicio),
        ("venta", PantallaVenta),
        ("compras", PantallaCompras),
        ("existencias", PantallaExistencias),
        ("perdidas", PantallaPerdidas),
        ("reportes", PantallaReportes),
    ]
    for nombre, clase in pantallas:
        pantalla = clase(conexion)
        pantalla.resize(*TAMANO)
        pantalla.refrescar()
        if nombre == "venta":
            _venta_en_curso(pantalla)
        if nombre == "reportes":
            pantalla.generar()  # la pantalla abre vacia hasta que se pide uno
        archivo = DESTINO / f"{nombre}.png"
        pantalla.grab().save(str(archivo))
        print(f"  {archivo}")
    conexion.close()
    return 0


def _venta_en_curso(pantalla) -> None:
    """Una venta vacia no le muestra nada al que lee el manual."""
    for entrada in ("7591001000018", "2*7591003000016", "0.750*7591002000017"):
        pantalla.codigo.setText(entrada)
        pantalla.agregar()


if __name__ == "__main__":
    sys.exit(main())
