"""Capturas de pantalla para el manual de usuario (punto 8 de la Fase 6).

    python -m herramientas.demostracion
    python -m herramientas.capturas

Arma la ventana principal sobre la base de demostracion —con menu, pestanas
y barra de estado, tal como la ve el usuario— y guarda una imagen por pestana
en `docs/capturas/`, mas el ingreso y el cobro. Se hace por programa y no a
mano para que las imagenes del manual se puedan rehacer cuando la interfaz
cambie, en vez de envejecer.

`QWidget.grab()` dibuja el widget en una imagen sin necesidad de mostrarlo,
asi que no hay ventanas parpadeando ni un orden de clics que respetar.
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from minimarket.datos.conexion import abrir

DESTINO = Path("docs/capturas")
TAMANO = (1280, 720)  # la resolucion mas chica que se ve en un equipo de caja

# (archivo, titulo de la pestana). El titulo es el que arma VentanaPrincipal.
PESTANAS = [
    ("inicio", "&Inicio"),
    ("venta", "&Venta"),
    ("productos", "&Productos"),
    ("compras", "Co&mpras"),
    ("existencias", "&Existencias"),
    ("perdidas", "&Perdidas"),
    ("gastos", "&Gastos"),
    ("reportes", "&Reportes"),
]


def main() -> int:
    from minimarket.infra import rutas
    from minimarket.servicios import iniciar_sesion
    from minimarket.servicios import usuarios as servicio_usuarios
    from minimarket.ui import estilo
    from minimarket.ui.principal import VentanaPrincipal
    from minimarket.ui.usuarios import DialogoIngreso
    from minimarket.ui.productos import DialogoMargenSugerido
    from minimarket.ui.venta import DialogoCierre, DialogoCobro

    base = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else rutas.base_de_datos().with_name("demostracion.db")
    )
    if not base.is_file():
        print(f"Falta la base de demostracion: {base}")
        print("Corre primero: python -m herramientas.demostracion")
        return 1

    aplicacion = QApplication(sys.argv)
    estilo.aplicar(aplicacion)
    conexion = abrir(base)
    administrador = servicio_usuarios.obtener(conexion, 1)
    iniciar_sesion(administrador)
    DESTINO.mkdir(parents=True, exist_ok=True)

    ingreso = DialogoIngreso(conexion)
    ingreso.nombre.setText("admin")
    _guardar(ingreso, "ingreso")

    ventana = VentanaPrincipal(conexion, administrador)
    ventana.resize(*TAMANO)
    indices = {
        ventana.pestanas.tabText(i).split(" (")[0]: i
        for i in range(ventana.pestanas.count())
    }
    for archivo, titulo in PESTANAS:
        ventana.pestanas.setCurrentIndex(indices[titulo])
        pantalla = ventana.pestanas.currentWidget()
        if archivo == "venta":
            _venta_en_curso(pantalla)
        if archivo == "reportes":
            pantalla.generar()  # la pantalla abre vacia hasta que se pide uno
        _guardar(ventana, archivo)

    venta = ventana.pestanas.widget(indices["&Venta"])
    cobro = DialogoCobro(venta._venta_en_curso())
    _guardar(cobro, "cobro")
    _guardar(DialogoMargenSugerido(conexion), "margen")
    from minimarket.servicios import caja as servicio_caja
    sesion = servicio_caja.sesion_abierta(conexion)
    cierre = DialogoCierre(conexion, sesion.id)
    cierre.findChild(__import__("PySide6.QtWidgets", fromlist=["QTabWidget"]).QTabWidget).setCurrentIndex(1)
    _guardar(cierre, "cierre")

    conexion.close()
    return 0


def _guardar(widget, nombre: str) -> None:
    archivo = DESTINO / f"{nombre}.png"
    widget.grab().save(str(archivo))
    print(f"  {archivo}")


def _venta_en_curso(pantalla) -> None:
    """Una venta vacia no le muestra nada al que lee el manual."""
    for entrada in ("7591001000018", "2*7591003000016", "0.750*7591002000017"):
        pantalla.codigo.setText(entrada)
        pantalla.agregar()


if __name__ == "__main__":
    sys.exit(main())
