"""Configuracion del negocio, respaldo y bitacora (RF-59, RF-61 a RF-64)."""

import sqlite3

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from minimarket.infra import auditoria
from minimarket.servicios import ErrorServicio
from minimarket.servicios import configuracion as servicio_configuracion
from minimarket.ui.comunes import avisar, confirmar

COLUMNAS_RESPALDO = ["Fecha y hora", "Estado", "Archivo", "Tamano", "Mensaje"]
COLUMNAS_BITACORA = ["Fecha y hora", "Usuario", "Accion", "Entidad", "Antes", "Despues"]


class DialogoConfiguracion(QDialog):
    """RF-64 y RF-61 a RF-63 en una sola ventana de administracion."""

    def __init__(
        self, conexion: sqlite3.Connection, padre: QWidget | None = None
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.setWindowTitle("Configuracion del sistema")
        self.resize(760, 560)

        self.campos: dict[str, QLineEdit] = {}
        valores = servicio_configuracion.leer_todo(conexion)
        formulario = QFormLayout()
        for campo in servicio_configuracion.CAMPOS:
            editor = QLineEdit(valores.get(campo.clave, ""))
            if campo.ayuda:
                editor.setPlaceholderText(campo.ayuda)
            self.campos[campo.clave] = editor
            formulario.addRow(f"{campo.etiqueta}:", editor)
        pagina_datos = QWidget()
        pagina_datos.setLayout(formulario)

        self.tabla_respaldo = _tabla(COLUMNAS_RESPALDO)
        self.tabla_bitacora = _tabla(COLUMNAS_BITACORA)

        pestanas = QTabWidget()
        pestanas.addTab(pagina_datos, "&Datos del negocio")
        pestanas.addTab(self._pagina_respaldo(), "&Respaldo")
        pestanas.addTab(self.tabla_bitacora, "&Bitacora")

        botones = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Close, parent=self
        )
        botones.button(QDialogButtonBox.Save).setText("Guardar configuracion")
        botones.button(QDialogButtonBox.Close).setText("Cerrar")
        botones.accepted.connect(self.guardar)
        botones.rejected.connect(self.reject)

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(pestanas)
        disposicion.addWidget(botones)
        self.refrescar()

    def _pagina_respaldo(self) -> QWidget:
        boton_respaldar = QPushButton("Respaldar &ahora")
        boton_respaldar.clicked.connect(self.respaldar)
        boton_restaurar = QPushButton("Restaurar un respaldo…")
        boton_restaurar.clicked.connect(self.restaurar)
        botones = QHBoxLayout()
        botones.addWidget(boton_respaldar)
        botones.addWidget(boton_restaurar)
        botones.addStretch()

        pagina = QWidget()
        disposicion = QVBoxLayout(pagina)
        disposicion.addWidget(
            QLabel(
                "El respaldo diario corre solo al abrir la aplicacion, a partir "
                "de la hora configurada (RF-61). Guarda la carpeta antes de "
                "respaldar por primera vez."
            )
        )
        disposicion.addWidget(self.tabla_respaldo)
        disposicion.addLayout(botones)
        return pagina

    def refrescar(self) -> None:
        try:
            registros = servicio_configuracion.historial(self.conexion)
        except ErrorServicio:
            registros = []
        _llenar(
            self.tabla_respaldo,
            [
                [
                    r.fecha_hora,
                    r.estado,
                    r.ruta,
                    f"{(r.tamano_bytes or 0) / 1_048_576:.1f} MB",
                    r.mensaje or "",
                ]
                for r in registros
            ],
        )
        _llenar(
            self.tabla_bitacora,
            [
                [
                    a.fecha_hora,
                    a.usuario,
                    a.accion,
                    f"{a.entidad} {a.entidad_id or ''}".strip(),
                    a.datos_antes or "",
                    a.datos_despues or "",
                ]
                for a in auditoria.listar(self.conexion)
            ],
        )

    def guardar(self) -> None:
        """RF-64."""
        try:
            servicio_configuracion.guardar(
                self.conexion,
                {clave: editor.text() for clave, editor in self.campos.items()},
            )
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        avisar(self, "Configuracion guardada.", "Listo")
        self.refrescar()

    def respaldar(self) -> None:
        """RF-61 / RF-62."""
        try:
            registro = servicio_configuracion.respaldar(self.conexion)
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        self.refrescar()
        if registro.ok:
            avisar(self, f"Respaldo guardado en {registro.ruta}.", "Respaldo listo")
        else:
            avisar(self, registro.mensaje or "El respaldo fallo.", "Respaldo fallido")

    def restaurar(self) -> None:
        """RF-63. Reemplaza todo lo que hay: se confirma dos veces."""
        origen, _ = QFileDialog.getOpenFileName(
            self, "Elegi el respaldo a restaurar", "", "Base de datos (*.db)"
        )
        if not origen:
            return
        if not confirmar(
            self,
            "Restaurar reemplaza TODA la informacion actual por la del "
            "respaldo. Lo que se haya cargado despues de esa copia se pierde.\n\n"
            f"¿Restaurar desde {origen}?",
            "Restaurar respaldo",
        ):
            return
        try:
            servicio_configuracion.restaurar(self.conexion, origen)
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        avisar(
            self,
            "Respaldo restaurado. Cerra y volve a abrir la aplicacion para "
            "trabajar con los datos restaurados.",
            "Restauracion completa",
        )
        self.refrescar()


def _tabla(columnas: list[str]) -> QTableWidget:
    tabla = QTableWidget(0, len(columnas))
    tabla.setHorizontalHeaderLabels(columnas)
    tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
    tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tabla.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
    return tabla


def _llenar(tabla: QTableWidget, filas: list[list[str]]) -> None:
    tabla.setRowCount(len(filas))
    for numero, fila in enumerate(filas):
        for columna, texto in enumerate(fila):
            tabla.setItem(numero, columna, QTableWidgetItem(texto))
