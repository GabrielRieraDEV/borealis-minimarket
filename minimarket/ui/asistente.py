"""Asistente de primer arranque (punto 6 de la Fase 6).

Se muestra una sola vez: cuando el `admin` que siembra `esquema.sql` todavia no
tiene clave. Reemplaza al `DialogoClaveInicial` de la Fase 4, que solo pedia la
clave, y de paso deja cargado lo que si o si hace falta antes de la primera
venta: los datos fiscales del encabezado, la carpeta de respaldo y la tasa.

Lo unico obligatorio es la clave. Todo lo demas se puede completar despues en
Archivo → Configuracion; no tiene sentido trabar la instalacion porque el
cliente todavia no decidio en que pendrive respalda.

No hay pasos ni «Siguiente»: son diez campos y entran en una pantalla. Un
asistente por pasos seria mas codigo y mas clics para el mismo resultado.
"""

import sqlite3

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from minimarket.dominio.usuario import Usuario
from minimarket.servicios import ErrorServicio
from minimarket.servicios import configuracion as servicio_configuracion
from minimarket.servicios import tasa as servicio_tasa
from minimarket.servicios import usuarios as servicio_usuarios
from minimarket.ui.comunes import ErrorDeCampo, a_decimal, avisar

IMAGENES = "Imagenes (*.png *.jpg *.jpeg *.gif);;Todos los archivos (*)"


class AsistentePrimerArranque(QDialog):
    """Deja el sistema utilizable: clave, datos fiscales, respaldo y tasa."""

    def __init__(
        self,
        conexion: sqlite3.Connection,
        usuario: Usuario,
        padre: QWidget | None = None,
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.usuario = usuario
        self.setWindowTitle("Puesta en marcha del sistema")
        self.setMinimumWidth(520)

        self.clave = QLineEdit()
        self.clave.setEchoMode(QLineEdit.Password)
        self.repetida = QLineEdit()
        self.repetida.setEchoMode(QLineEdit.Password)

        self.nombre = QLineEdit()
        self.rif = QLineEdit()
        self.direccion = QLineEdit()
        self.telefono = QLineEdit()
        self.logo = QLineEdit()
        self.respaldo = QLineEdit()
        self.tasa = QLineEdit()
        self.tasa.setPlaceholderText("Bolivares por dolar, por ejemplo 804,81")

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(
            QLabel(
                "Bienvenido. Estos datos se cargan una sola vez; despues se "
                "cambian en Archivo → Configuracion."
            )
        )
        disposicion.addWidget(self._grupo_administrador())
        disposicion.addWidget(self._grupo_negocio())
        disposicion.addWidget(self._grupo_operacion())

        botones = QDialogButtonBox(QDialogButtonBox.Ok, parent=self)
        botones.button(QDialogButtonBox.Ok).setText("Poner en marcha")
        botones.accepted.connect(self.guardar)
        disposicion.addWidget(botones)

    def _grupo_administrador(self) -> QGroupBox:
        grupo = QGroupBox(f"Clave del administrador «{self.usuario.usuario}»")
        formulario = QFormLayout(grupo)
        formulario.addRow("Clave:", self.clave)
        formulario.addRow("Repetir clave:", self.repetida)
        return grupo

    def _grupo_negocio(self) -> QGroupBox:
        grupo = QGroupBox("Datos del negocio (encabezan notas y reportes)")
        formulario = QFormLayout(grupo)
        formulario.addRow("Razon social:", self.nombre)
        formulario.addRow("RIF:", self.rif)
        formulario.addRow("Direccion fiscal:", self.direccion)
        formulario.addRow("Telefono:", self.telefono)
        formulario.addRow("Logotipo:", _con_examinar(self.logo, self._buscar_logo))
        return grupo

    def _grupo_operacion(self) -> QGroupBox:
        grupo = QGroupBox("Respaldo y tasa del dia")
        formulario = QFormLayout(grupo)
        formulario.addRow(
            "Carpeta de respaldo:",
            _con_examinar(self.respaldo, self._buscar_respaldo),
        )
        formulario.addRow("Tasa de cambio de hoy:", self.tasa)
        return grupo

    def _buscar_logo(self) -> None:
        elegido, _ = QFileDialog.getOpenFileName(
            self, "Elegi el archivo del logotipo", "", IMAGENES
        )
        if elegido:
            self.logo.setText(elegido)

    def _buscar_respaldo(self) -> None:
        elegido = QFileDialog.getExistingDirectory(
            self, "Elegi la carpeta de respaldo"
        )
        if elegido:
            self.respaldo.setText(elegido)

    def guardar(self) -> None:
        """Clave primero: sin ella no hay sesion que firme lo demas."""
        if self.clave.text() != self.repetida.text():
            avisar(self, "Las dos claves no coinciden.")
            return
        try:
            tasa = a_decimal(self.tasa.text(), "la tasa de cambio", opcional=True)
        except ErrorDeCampo as error:
            avisar(self, str(error))
            return
        try:
            servicio_usuarios.establecer_clave_inicial(
                self.conexion, self.clave.text()
            )
            self._guardar_configuracion()
            if tasa is not None:
                servicio_tasa.registrar_manual(self.conexion, tasa)  # RF-11
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        self.accept()

    def _guardar_configuracion(self) -> None:
        """RF-64. Solo lo que se cargo; `guardar` ignora lo que no cambio."""
        servicio_configuracion.guardar(
            self.conexion,
            {
                "negocio.nombre": self.nombre.text(),
                "negocio.rif": self.rif.text(),
                "negocio.direccion": self.direccion.text(),
                "negocio.telefono": self.telefono.text(),
                "negocio.logo": self.logo.text(),
                "respaldo.ruta": self.respaldo.text(),
            },
        )


def _con_examinar(campo: QLineEdit, buscar) -> QWidget:
    """Un campo de texto con su boton de «Examinar…» al lado."""
    contenedor = QWidget()
    fila = QHBoxLayout(contenedor)
    fila.setContentsMargins(0, 0, 0, 0)
    boton = QPushButton("Examinar…")
    boton.clicked.connect(buscar)
    fila.addWidget(campo)
    fila.addWidget(boton)
    return contenedor
