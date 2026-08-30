"""Ventana principal y arranque de la aplicacion.

Navegacion por teclado (RNF-08): F1 venta, F2 productos, F3 categorias,
F5 tasa del dia, F8 compras, F10 proveedores, F11 existencias, y Ctrl+letra
para el resto (Ctrl+I inicio, Ctrl+R reportes, Ctrl+P perdidas, Ctrl+G gastos,
Ctrl+U usuarios, Ctrl+K configuracion).

Las teclas de funcion que faltan estan tomadas ADENTRO de las pantallas: F4
edita, F6 anula, F7 abre la caja o ajusta, F9 recalcula o reimprime, F12
cobra. Un atajo de ventana con la misma tecla que uno de pantalla deja a Qt
sin saber cual disparar, asi que la navegacion nueva va por Ctrl.

Las pestanas que el perfil no puede usar no se dibujan (RF-58). Eso es
comodidad, no seguridad: quien corta cada operacion es la capa de servicios.
"""

import os
import sqlite3
import sys
from pathlib import Path

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QTabWidget

from minimarket.datos import conexion as datos_conexion
from minimarket.dominio.usuario import (
    CONFIGURAR,
    GESTIONAR_USUARIOS,
    MODIFICAR_PRECIOS,
    NOMBRE_ROL,
    REGISTRAR_COMPRAS,
    REGISTRAR_GASTOS,
    REGISTRAR_PERDIDAS,
    REPORTE_CIERRE,
    VENDER,
    VER_EXISTENCIAS,
    Usuario,
)
from minimarket.servicios import configuracion as servicio_configuracion
from minimarket.servicios import tasa as servicio_tasa
from minimarket.ui.categorias import PantallaCategorias
from minimarket.ui.comunes import avisar, formato
from minimarket.ui.compras import PantallaCompras, PantallaProveedores
from minimarket.ui.configuracion import DialogoConfiguracion
from minimarket.ui.gastos import PantallaGastos
from minimarket.ui.inicio import PantallaInicio
from minimarket.ui.inventario import PantallaExistencias
from minimarket.ui.perdidas import PantallaPerdidas
from minimarket.ui.productos import PantallaProductos
from minimarket.ui.reportes import PantallaReportes
from minimarket.ui.tasa import DialogoTasa
from minimarket.ui.usuarios import (
    DialogoClaveInicial,
    DialogoIngreso,
    PantallaUsuarios,
)
from minimarket.ui.venta import PantallaVenta


def ruta_base() -> Path:
    """Carpeta escribible por el usuario; el instalador la fija en la Fase 6."""
    if os.environ.get("MINIMARKET_DB"):
        return Path(os.environ["MINIMARKET_DB"])
    carpeta = Path.home() / "Minimarket"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta / "minimarket.db"


class VentanaPrincipal(QMainWindow):
    def __init__(self, conexion: sqlite3.Connection, usuario: Usuario) -> None:
        super().__init__()
        self.conexion = conexion
        self.usuario = usuario
        rol = NOMBRE_ROL.get(usuario.rol, usuario.rol)
        self.setWindowTitle(f"Minimarket — {usuario.nombre} ({rol})")
        self.resize(1060, 660)

        # (permiso, titulo, atajo, pantalla). Sin el permiso, la pestana no
        # existe: al cajero no le aparecen compras, catalogo ni reportes.
        posibles = [
            (CONFIGURAR, "&Inicio", "Ctrl+I", PantallaInicio),
            (VENDER, "&Venta", "F1", PantallaVenta),
            (MODIFICAR_PRECIOS, "&Productos", "F2", PantallaProductos),
            (MODIFICAR_PRECIOS, "&Categorias", "F3", PantallaCategorias),
            (REGISTRAR_COMPRAS, "Co&mpras", "F8", PantallaCompras),
            (REGISTRAR_COMPRAS, "Pro&veedores", "F10", PantallaProveedores),
            (VER_EXISTENCIAS, "&Existencias", "F11", PantallaExistencias),
            (REGISTRAR_PERDIDAS, "&Perdidas", "Ctrl+P", PantallaPerdidas),
            (REGISTRAR_GASTOS, "&Gastos", "Ctrl+G", PantallaGastos),
            (REPORTE_CIERRE, "&Reportes", "Ctrl+R", PantallaReportes),
            (GESTIONAR_USUARIOS, "&Usuarios", "Ctrl+U", PantallaUsuarios),
        ]
        self.pestanas = QTabWidget()
        menu = self.menuBar().addMenu("&Archivo")
        for indice, (_, titulo, atajo, clase) in enumerate(
            [p for p in posibles if usuario.puede(p[0])]
        ):
            self.pestanas.addTab(clase(conexion), f"{titulo} ({atajo})")
            menu.addAction(self._accion(titulo, atajo, self._ir(indice)))
        self.pestanas.currentChanged.connect(self.refrescar)
        self.setCentralWidget(self.pestanas)

        if usuario.puede(CONFIGURAR):
            menu.addSeparator()
            menu.addAction(self._accion("&Tasa del dia…", "F5", self.cargar_tasa))
            menu.addAction(
                self._accion("&Configuracion…", "Ctrl+K", self.configurar)
            )
        menu.addSeparator()
        menu.addAction(self._accion("&Salir", "Ctrl+Q", self.close))

        self.refrescar()

    def _accion(self, texto: str, atajo: str, destino) -> QAction:
        accion = QAction(texto, self)
        accion.setShortcut(QKeySequence(atajo))
        accion.triggered.connect(destino)
        return accion

    def _ir(self, indice: int):
        return lambda: self.pestanas.setCurrentIndex(indice)

    def cargar_tasa(self) -> None:
        """RF-11. La tasa manda sobre toda la conversion a bolivares."""
        if DialogoTasa(self.conexion, self).exec() == QDialog.Accepted:
            self.refrescar()

    def configurar(self) -> None:
        """RF-64, RF-61 a RF-63 y la bitacora de RF-59."""
        DialogoConfiguracion(self.conexion, self).exec()
        self.refrescar()

    def refrescar(self) -> None:
        pantalla = self.pestanas.currentWidget()
        if pantalla is not None:
            pantalla.refrescar()
        vigente = servicio_tasa.tasa_del_dia(self.conexion)
        self.statusBar().showMessage(
            f"{self.usuario.nombre} · Tasa de hoy: {formato(vigente, 6)} Bs/USD"
            if vigente is not None
            else f"{self.usuario.nombre} · Sin tasa del dia. Cargala antes de "
            "abrir la caja."
        )


def ingresar(conexion: sqlite3.Connection, padre=None) -> Usuario | None:
    """RF-56. Pide la clave inicial si el administrador todavia no tiene."""
    from minimarket.servicios import usuarios as servicio_usuarios

    semilla = servicio_usuarios.necesita_clave_inicial(conexion)
    if semilla is not None:
        if DialogoClaveInicial(conexion, semilla, padre).exec() != QDialog.Accepted:
            return None
    dialogo = DialogoIngreso(conexion, padre)
    return dialogo.usuario if dialogo.exec() == QDialog.Accepted else None


def main() -> int:
    aplicacion = QApplication(sys.argv)
    conexion = datos_conexion.abrir(ruta_base())
    usuario = ingresar(conexion)
    if usuario is None:
        return 0
    ventana = VentanaPrincipal(conexion, usuario)
    ventana.show()
    # RF-61 / RF-62. Se dispara despues de mostrar la ventana para que el aviso
    # tenga donde aparecer si la unidad externa no esta.
    registro = servicio_configuracion.respaldo_automatico(conexion)
    if registro is not None and not registro.ok and usuario.puede(CONFIGURAR):
        avisar(
            ventana,
            f"{registro.mensaje}\n\nRevisa la unidad de respaldo en "
            "Archivo → Configuracion.",
            "El respaldo diario fallo",
        )
    return aplicacion.exec()


if __name__ == "__main__":
    sys.exit(main())
