"""Ingreso al sistema y gestion de usuarios (RF-56, RF-57, RF-60).

La pantalla esconde lo que el perfil no puede usar, pero el que decide es
`servicios/usuarios.py`: aca no hay ninguna verificacion de permisos que el
servicio no repita (RF-58).
"""

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from minimarket.dominio.usuario import NOMBRE_ROL, ROLES, Usuario
from minimarket.infra import rutas
from minimarket.servicios import ErrorServicio
from minimarket.servicios import usuarios as servicio_usuarios
from minimarket.ui.comunes import avisar, confirmar

COLUMNAS = ["Usuario", "Nombre", "Perfil", "Estado", "Alta"]


class DialogoIngreso(QDialog):
    """RF-56. Sin esto no se entra a la aplicacion."""

    def __init__(
        self, conexion: sqlite3.Connection, padre: QWidget | None = None
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.usuario: Usuario | None = None
        self.setWindowTitle("Ingreso al sistema")

        self.nombre = QLineEdit()
        self.nombre.setPlaceholderText("Nombre de usuario")
        self.clave = QLineEdit()
        self.clave.setPlaceholderText("Clave")
        self.clave.setEchoMode(QLineEdit.Password)
        # Enter en cualquiera de los dos campos confirma: es el gesto de todos
        # los dias y no tiene por que pedir un clic.
        self.nombre.returnPressed.connect(self.entrar)
        self.clave.returnPressed.connect(self.entrar)

        botones = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        botones.button(QDialogButtonBox.Ok).setText("Entrar")
        botones.button(QDialogButtonBox.Ok).setDefault(True)
        botones.button(QDialogButtonBox.Cancel).setText("Salir")
        botones.accepted.connect(self.entrar)
        botones.rejected.connect(self.reject)

        # El logotipo arriba, los campos en una tarjeta. Es la primera pantalla
        # que ve el cliente y la unica que ve el que no tiene clave.
        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        imagen = QPixmap(str(rutas.logo()))
        if not imagen.isNull():
            logo.setPixmap(
                imagen.scaledToHeight(110, Qt.SmoothTransformation)
            )
        titulo = QLabel("Ingreso al sistema")
        titulo.setObjectName("tituloIngreso")
        titulo.setAlignment(Qt.AlignCenter)
        subtitulo = QLabel("Escribi tu usuario y tu clave, y Enter.")
        subtitulo.setObjectName("subtituloIngreso")
        subtitulo.setAlignment(Qt.AlignCenter)

        tarjeta = QFrame()
        tarjeta.setObjectName("tarjetaIngreso")
        adentro = QVBoxLayout(tarjeta)
        adentro.setContentsMargins(28, 18, 28, 16)
        adentro.setSpacing(8)
        adentro.addWidget(titulo)
        adentro.addWidget(subtitulo)
        adentro.addSpacing(6)
        adentro.addWidget(self.nombre)
        adentro.addWidget(self.clave)
        adentro.addSpacing(6)
        adentro.addWidget(botones)

        disposicion = QVBoxLayout(self)
        disposicion.setContentsMargins(36, 16, 36, 20)
        disposicion.setSpacing(12)
        disposicion.addWidget(logo)
        disposicion.addWidget(tarjeta)
        self.setFixedWidth(420)
        self.nombre.setFocus()

    def entrar(self) -> None:
        try:
            self.usuario = servicio_usuarios.autenticar(
                self.conexion, self.nombre.text(), self.clave.text()
            )
        except ErrorServicio as error:
            avisar(self, str(error), "No se pudo entrar")
            self.clave.clear()
            self.clave.setFocus()
            return
        self.accept()


class DialogoAutorizacion(QDialog):
    """RN-25. El administrador autoriza sin desplazar al cajero de la sesion.

    Devuelve el id del administrador que valido su clave; quien decide si eso
    alcanza es el servicio.
    """

    def __init__(
        self, conexion: sqlite3.Connection, motivo: str, padre: QWidget | None = None
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.autorizado_por: int | None = None
        self.setWindowTitle("Autorizacion de administrador")

        self.nombre = QLineEdit()
        self.clave = QLineEdit()
        self.clave.setEchoMode(QLineEdit.Password)
        self.clave.returnPressed.connect(self.validar)

        botones = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        botones.button(QDialogButtonBox.Ok).setText("Autorizar")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.validar)
        botones.rejected.connect(self.reject)

        formulario = QFormLayout()
        formulario.addRow("Administrador:", self.nombre)
        formulario.addRow("Clave:", self.clave)

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(QLabel(motivo))
        disposicion.addLayout(formulario)
        disposicion.addWidget(botones)
        self.nombre.setFocus()

    def validar(self) -> None:
        try:
            usuario = servicio_usuarios.verificar(
                self.conexion, self.nombre.text(), self.clave.text()
            )
        except ErrorServicio as error:
            avisar(self, str(error))
            self.clave.clear()
            return
        if not usuario.es_administrador:
            avisar(self, "Ese usuario no es administrador.")
            return
        self.autorizado_por = usuario.id
        self.accept()


def pedir_autorizacion(
    conexion: sqlite3.Connection, motivo: str, padre: QWidget | None = None
) -> int | None:
    """Atajo: devuelve el id que autorizo, o None si se cancelo."""
    dialogo = DialogoAutorizacion(conexion, motivo, padre)
    if dialogo.exec() != QDialog.Accepted:
        return None
    return dialogo.autorizado_por


class PantallaUsuarios(QWidget):
    """RF-57. Alta, modificacion, baja y cambio de clave."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self.filas: list[Usuario] = []

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla.itemActivated.connect(lambda _: self.editar())

        botones = QHBoxLayout()
        for texto, destino in (
            ("&Nuevo usuario", self.nuevo),
            ("&Editar", self.editar),
            ("Cambiar &clave", self.cambiar_clave),
            ("&Activar o dar de baja", self.alternar_estado),
        ):
            boton = QPushButton(texto)
            boton.clicked.connect(destino)
            botones.addWidget(boton)
        botones.addStretch()

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(self.tabla)
        disposicion.addLayout(botones)
        self.refrescar()

    def refrescar(self) -> None:
        try:
            self.filas = servicio_usuarios.listar(self.conexion)
        except ErrorServicio:
            # El cajero no llega aca por menu; si llega, ve la lista vacia y el
            # servicio corta cualquier intento de escritura.
            self.filas = []
        self.tabla.setRowCount(len(self.filas))
        for numero, fila in enumerate(self.filas):
            celdas = [
                fila.usuario,
                fila.nombre,
                NOMBRE_ROL.get(fila.rol, fila.rol),
                "Activo" if fila.activo else "De baja",
                fila.creado_en or "",
            ]
            for columna, texto in enumerate(celdas):
                self.tabla.setItem(numero, columna, QTableWidgetItem(texto))

    def _elegido(self) -> Usuario | None:
        numero = self.tabla.currentRow()
        if not 0 <= numero < len(self.filas):
            avisar(self, "Elegi un usuario de la lista.")
            return None
        return self.filas[numero]

    def nuevo(self) -> None:
        if DialogoUsuario(self.conexion, None, self).exec() == QDialog.Accepted:
            self.refrescar()

    def editar(self) -> None:
        usuario = self._elegido()
        if usuario and DialogoUsuario(self.conexion, usuario, self).exec() == (
            QDialog.Accepted
        ):
            self.refrescar()

    def cambiar_clave(self) -> None:
        usuario = self._elegido()
        if usuario and DialogoClave(self.conexion, usuario, self).exec() == (
            QDialog.Accepted
        ):
            self.refrescar()

    def alternar_estado(self) -> None:
        usuario = self._elegido()
        if usuario is None:
            return
        accion = "dar de baja" if usuario.activo else "reactivar"
        if not confirmar(self, f"¿Confirmas {accion} a «{usuario.usuario}»?"):
            return
        try:
            servicio_usuarios.cambiar_estado(
                self.conexion, usuario.id, not usuario.activo
            )
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        self.refrescar()


class DialogoUsuario(QDialog):
    """RF-57. Alta si no hay usuario, modificacion si lo hay."""

    def __init__(
        self,
        conexion: sqlite3.Connection,
        usuario: Usuario | None,
        padre: QWidget | None = None,
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.usuario = usuario
        self.setWindowTitle("Usuario" if usuario else "Nuevo usuario")

        self.ingreso = QLineEdit(usuario.usuario if usuario else "")
        self.nombre = QLineEdit(usuario.nombre if usuario else "")
        self.rol = QComboBox()
        for rol in ROLES:
            self.rol.addItem(NOMBRE_ROL[rol], rol)
        if usuario:
            self.rol.setCurrentIndex(ROLES.index(usuario.rol))
        self.activo = QCheckBox("Activo")
        self.activo.setChecked(usuario.activo if usuario else True)

        self.clave = QLineEdit()
        self.clave.setEchoMode(QLineEdit.Password)

        botones = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        botones.button(QDialogButtonBox.Save).setText("Guardar")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.guardar)
        botones.rejected.connect(self.reject)

        formulario = QFormLayout()
        formulario.addRow("Usuario:", self.ingreso)
        formulario.addRow("Nombre:", self.nombre)
        formulario.addRow("Perfil:", self.rol)
        formulario.addRow("", self.activo)
        if usuario is None:
            formulario.addRow("Clave:", self.clave)

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(formulario)
        disposicion.addWidget(
            QLabel("El cajero no accede a costos, compras ni ganancias (RF-58).")
        )
        disposicion.addWidget(botones)

    def guardar(self) -> None:
        datos = Usuario(
            id=self.usuario.id if self.usuario else None,
            usuario=self.ingreso.text().strip(),
            nombre=self.nombre.text().strip(),
            rol=self.rol.currentData(),
            activo=self.activo.isChecked(),
        )
        try:
            if self.usuario is None:
                servicio_usuarios.crear(self.conexion, datos, self.clave.text())
            else:
                servicio_usuarios.modificar(self.conexion, datos)
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        self.accept()


class DialogoClave(QDialog):
    """RF-60. Cambio de clave de un usuario existente."""

    def __init__(
        self,
        conexion: sqlite3.Connection,
        usuario: Usuario,
        padre: QWidget | None = None,
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.usuario = usuario
        self.setWindowTitle(f"Clave de {usuario.usuario}")

        self.clave = QLineEdit()
        self.clave.setEchoMode(QLineEdit.Password)
        self.repetida = QLineEdit()
        self.repetida.setEchoMode(QLineEdit.Password)

        botones = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        botones.button(QDialogButtonBox.Save).setText("Cambiar clave")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.guardar)
        botones.rejected.connect(self.reject)

        formulario = QFormLayout()
        formulario.addRow("Clave nueva:", self.clave)
        formulario.addRow("Repetir clave:", self.repetida)

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(formulario)
        disposicion.addWidget(botones)

    def guardar(self) -> None:
        if self.clave.text() != self.repetida.text():
            avisar(self, "Las dos claves no coinciden.")
            return
        try:
            servicio_usuarios.cambiar_clave(
                self.conexion, self.usuario.id, self.clave.text()
            )
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        self.accept()
