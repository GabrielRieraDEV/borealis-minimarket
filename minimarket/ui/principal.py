"""Ventana principal y arranque de la aplicacion.

Navegacion por teclado (RNF-08): F1 venta, F2 productos, F3 categorias,
F5 tasa del dia, F8 compras, F10 proveedores, F11 existencias.
"""

import os
import sqlite3
import sys
from pathlib import Path

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QTabWidget

from minimarket.datos import conexion as datos_conexion
from minimarket.servicios import tasa as servicio_tasa
from minimarket.ui.categorias import PantallaCategorias
from minimarket.ui.comunes import formato
from minimarket.ui.compras import PantallaCompras, PantallaProveedores
from minimarket.ui.inventario import PantallaExistencias
from minimarket.ui.productos import PantallaProductos
from minimarket.ui.tasa import DialogoTasa
from minimarket.ui.venta import PantallaVenta


def ruta_base() -> Path:
    """Carpeta escribible por el usuario; el instalador la fija en la Fase 6."""
    if os.environ.get("MINIMARKET_DB"):
        return Path(os.environ["MINIMARKET_DB"])
    carpeta = Path.home() / "Minimarket"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta / "minimarket.db"


class VentanaPrincipal(QMainWindow):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self.setWindowTitle("Minimarket — Venta, catalogo, compras e inventario")
        self.resize(1060, 660)

        self.pestanas = QTabWidget()
        for titulo, pantalla in (
            ("&Venta (F1)", PantallaVenta(conexion)),
            ("&Productos (F2)", PantallaProductos(conexion)),
            ("&Categorias (F3)", PantallaCategorias(conexion)),
            ("Co&mpras (F8)", PantallaCompras(conexion)),
            ("Pro&veedores (F10)", PantallaProveedores(conexion)),
            ("&Existencias (F11)", PantallaExistencias(conexion)),
        ):
            self.pestanas.addTab(pantalla, titulo)
        self.pestanas.currentChanged.connect(self.refrescar)
        self.setCentralWidget(self.pestanas)

        menu = self.menuBar().addMenu("&Archivo")
        menu.addAction(self._accion("&Venta", "F1", lambda: self._ir(0)))
        menu.addAction(self._accion("&Productos", "F2", lambda: self._ir(1)))
        menu.addAction(self._accion("&Categorias", "F3", lambda: self._ir(2)))
        menu.addAction(self._accion("Co&mpras", "F8", lambda: self._ir(3)))
        menu.addAction(self._accion("Pro&veedores", "F10", lambda: self._ir(4)))
        menu.addAction(self._accion("&Existencias", "F11", lambda: self._ir(5)))
        menu.addAction(self._accion("&Tasa del dia…", "F5", self.cargar_tasa))
        menu.addSeparator()
        menu.addAction(self._accion("&Salir", "Ctrl+Q", self.close))

        self.refrescar()

    def _accion(self, texto: str, atajo: str, destino) -> QAction:
        accion = QAction(texto, self)
        accion.setShortcut(QKeySequence(atajo))
        accion.triggered.connect(destino)
        return accion

    def _ir(self, indice: int) -> None:
        self.pestanas.setCurrentIndex(indice)

    def cargar_tasa(self) -> None:
        """RF-11. La tasa manda sobre toda la conversion a bolivares."""
        if DialogoTasa(self.conexion, self).exec() == QDialog.Accepted:
            self.refrescar()

    def refrescar(self) -> None:
        self.pestanas.currentWidget().refrescar()
        vigente = servicio_tasa.tasa_del_dia(self.conexion)
        self.statusBar().showMessage(
            f"Tasa de hoy: {formato(vigente, 6)} Bs/USD"
            if vigente is not None
            else "Sin tasa del dia. Cargala con F5 antes de abrir la caja."
        )


def main() -> int:
    aplicacion = QApplication(sys.argv)
    conexion = datos_conexion.abrir(ruta_base())
    ventana = VentanaPrincipal(conexion)
    ventana.show()
    return aplicacion.exec()


if __name__ == "__main__":
    sys.exit(main())
