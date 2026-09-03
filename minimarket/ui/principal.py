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

import sqlite3
import sys
from pathlib import Path

from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QMainWindow,
    QTabWidget,
)

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
from minimarket.infra import bitacora, rutas
from minimarket.servicios import ErrorServicio
from minimarket.servicios import catalogo as servicio_catalogo
from minimarket.servicios import configuracion as servicio_configuracion
from minimarket.servicios import tasa as servicio_tasa
from minimarket.servicios import usuarios as servicio_usuarios
from minimarket.ui import estilo
from minimarket.ui.asistente import AsistentePrimerArranque
from minimarket.ui.categorias import PantallaCategorias
from minimarket.ui.comunes import avisar, detallar, formato
from minimarket.ui.compras import PantallaCompras, PantallaProveedores
from minimarket.ui.configuracion import DialogoConfiguracion
from minimarket.ui.gastos import PantallaGastos
from minimarket.ui.inicio import PantallaInicio
from minimarket.ui.inventario import PantallaExistencias
from minimarket.ui.perdidas import PantallaPerdidas
from minimarket.ui.productos import PantallaProductos
from minimarket.ui.reportes import PantallaReportes
from minimarket.ui.tasa import DialogoTasa
from minimarket.ui.usuarios import DialogoIngreso, PantallaUsuarios
from minimarket.ui.venta import PantallaVenta


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

        if usuario.puede(MODIFICAR_PRECIOS):
            menu.addSeparator()
            menu.addAction(
                self._accion("Importar catalogo desde CSV…", "", self.importar)
            )
            menu.addAction(
                self._accion("Guardar plantilla de catalogo…", "", self.plantilla)
            )
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

    def importar(self) -> None:
        """Carga inicial del catalogo desde CSV (punto 7 de la Fase 6).

        Los errores por fila van en el detalle desplegable del aviso: pueden
        ser cientos y no entran en un cartel.
        """
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Elegi el archivo del catalogo", "", "Archivos CSV (*.csv)"
        )
        if not ruta:
            return
        try:
            resultado = servicio_catalogo.importar_csv(self.conexion, ruta)
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        if resultado.errores:
            detallar(
                self,
                f"No se cargo ningun producto: hay {len(resultado.errores)} "
                "filas con problemas. Corregilas en el archivo y volve a "
                "importarlo.",
                resultado.errores,
                "El archivo tiene errores",
            )
            return
        avisar(
            self,
            f"Se cargaron {resultado.creados} productos.",
            "Catalogo importado",
        )
        self.refrescar()

    def plantilla(self) -> None:
        """El archivo de ejemplo con las columnas que espera la importacion."""
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar plantilla", "catalogo.csv", "Archivos CSV (*.csv)"
        )
        if not ruta:
            return
        try:
            Path(ruta).write_text(
                servicio_catalogo.plantilla_csv(), encoding="utf-8-sig"
            )
        except OSError as error:
            bitacora.anotar(f"No se pudo escribir la plantilla en {ruta}", error)
            avisar(self, "No se pudo guardar la plantilla en esa carpeta.")
            return
        avisar(self, f"Plantilla guardada en {ruta}.", "Plantilla")

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
    """RF-56. En el primer arranque corre el asistente de puesta en marcha."""
    semilla = servicio_usuarios.necesita_clave_inicial(conexion)
    if semilla is not None:
        asistente = AsistentePrimerArranque(conexion, semilla, padre)
        if asistente.exec() != QDialog.Accepted:
            return None
    dialogo = DialogoIngreso(conexion, padre)
    return dialogo.usuario if dialogo.exec() == QDialog.Accepted else None


def main(conexion: sqlite3.Connection) -> int:
    """Muestra la aplicacion sobre una base ya abierta.

    Quien la abre es `minimarket.__main__`: la interfaz no habla con `datos/`.
    """
    aplicacion = QApplication(sys.argv)
    estilo.aplicar(aplicacion)
    # El icono de la aplicacion: lo heredan todas las ventanas y dialogos.
    # Sin esto la barra de titulo muestra el generico de Qt, aunque el .exe
    # lo tenga incrustado.
    aplicacion.setWindowIcon(QIcon(str(rutas.icono())))
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
