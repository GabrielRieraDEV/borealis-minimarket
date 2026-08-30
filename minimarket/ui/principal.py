"""Ventana principal y arranque de la aplicacion.

Navegacion por teclado (RNF-08): F2 productos, F3 categorias, F5 tasa del dia.
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
from minimarket.ui.productos import PantallaProductos
from minimarket.ui.tasa import DialogoTasa


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
        self.setWindowTitle("Minimarket — Catalogo y tasa")
        self.resize(1000, 640)

        self.productos = PantallaProductos(conexion)
        self.categorias = PantallaCategorias(conexion)
        self.pestanas = QTabWidget()
        self.pestanas.addTab(self.productos, "&Productos (F2)")
        self.pestanas.addTab(self.categorias, "&Categorias (F3)")
        self.pestanas.currentChanged.connect(self.refrescar)
        self.setCentralWidget(self.pestanas)

        menu = self.menuBar().addMenu("&Archivo")
        menu.addAction(self._accion("&Productos", "F2", lambda: self._ir(0)))
        menu.addAction(self._accion("&Categorias", "F3", lambda: self._ir(1)))
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
