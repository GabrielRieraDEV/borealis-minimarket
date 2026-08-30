"""Consulta de existencias y ajuste por conteo fisico (RF-22 a RF-26)."""

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
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

from minimarket.dominio.inventario import ExistenciaProducto
from minimarket.servicios import inventario
from minimarket.ui.comunes import ErrorDeCampo, a_decimal, avisar, formato

COLUMNAS = [
    "Producto",
    "Existencia",
    "Minima",
    "Ultimo costo USD",
    "Valorizado USD",
    "Estado",
]
ROJO_SUAVE = QColor(255, 224, 224)


class PantallaExistencias(QWidget):
    """RF-22 y RF-24, con filtro de bajo stock y acceso al ajuste."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self.filas: list[ExistenciaProducto] = []

        self.busqueda = QLineEdit()
        self.busqueda.setPlaceholderText("Buscar por codigo de barras o nombre…")
        self.busqueda.setClearButtonEnabled(True)
        self.busqueda.textChanged.connect(self.refrescar)

        self.solo_alerta = QCheckBox("Solo los que estan en o bajo el minimo (RF-24)")
        self.solo_alerta.stateChanged.connect(self.refrescar)

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla.itemActivated.connect(lambda _: self.ajustar())

        self.resumen = QLabel()

        boton_ajuste = QPushButton("&Ajustar por conteo fisico (F7)")
        boton_ajuste.clicked.connect(self.ajustar)
        botones = QHBoxLayout()
        botones.addWidget(boton_ajuste)
        botones.addStretch()

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(self.busqueda)
        disposicion.addWidget(self.solo_alerta)
        disposicion.addWidget(self.tabla)
        disposicion.addWidget(self.resumen)
        disposicion.addLayout(botones)

        QShortcut(QKeySequence(Qt.Key_F7), self, self.ajustar)

        self.refrescar()

    def refrescar(self) -> None:
        self.filas = inventario.consultar(
            self.conexion,
            texto=self.busqueda.text(),
            solo_alerta=self.solo_alerta.isChecked(),
        )
        self.tabla.setRowCount(len(self.filas))
        for numero, fila in enumerate(self.filas):
            celdas = [
                fila.nombre,
                formato(fila.existencia, 3),
                formato(fila.existencia_minima, 3),
                formato(fila.ultimo_costo, 4),
                formato(fila.valorizacion),
                "Reponer" if fila.en_alerta else "",
            ]
            for columna, texto in enumerate(celdas):
                celda = QTableWidgetItem(texto)
                if fila.en_alerta:
                    celda.setBackground(QBrush(ROJO_SUAVE))
                self.tabla.setItem(numero, columna, celda)
        en_alerta = sum(1 for f in self.filas if f.en_alerta)
        valorizado = sum(f.valorizacion for f in self.filas)
        self.resumen.setText(
            f"{len(self.filas)} productos · {en_alerta} por reponer · "
            f"inventario valorizado en {formato(valorizado)} USD"
        )

    def ajustar(self) -> None:
        """RF-25 / RF-26. Solo administrador; lo hace cumplir el servicio."""
        numero = self.tabla.currentRow()
        if not 0 <= numero < len(self.filas):
            avisar(self, "Elegi un producto de la lista.")
            return
        if DialogoAjuste(self.conexion, self.filas[numero], self).exec() == (
            QDialog.Accepted
        ):
            self.refrescar()


class DialogoAjuste(QDialog):
    """RF-25. Deja constancia de sistema, contado, diferencia y motivo."""

    def __init__(
        self,
        conexion: sqlite3.Connection,
        fila: ExistenciaProducto,
        padre: QWidget | None = None,
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.fila = fila
        self.setWindowTitle("Ajuste por conteo fisico")

        self.contada = QLineEdit(str(fila.existencia))
        self.motivo = QLineEdit()
        self.motivo.setPlaceholderText("Por que difiere el conteo")
        self.diferencia = QLabel()
        self.contada.textChanged.connect(self.actualizar_diferencia)

        botones = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        botones.button(QDialogButtonBox.Save).setText("Aplicar ajuste")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.guardar)
        botones.rejected.connect(self.reject)

        formulario = QFormLayout()
        formulario.addRow("Producto:", QLabel(fila.nombre))
        formulario.addRow(
            "Cantidad segun el sistema:", QLabel(formato(fila.existencia, 3))
        )
        formulario.addRow("Cantidad contada:", self.contada)
        formulario.addRow("Diferencia:", self.diferencia)
        formulario.addRow("Motivo:", self.motivo)

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(formulario)
        disposicion.addWidget(
            QLabel(
                "El ajuste no edita la existencia: genera un movimiento con la "
                "diferencia (RN-11)."
            )
        )
        disposicion.addWidget(botones)
        self.actualizar_diferencia()

    def actualizar_diferencia(self) -> None:
        try:
            contada = a_decimal(self.contada.text(), "la cantidad contada")
        except ErrorDeCampo:
            self.diferencia.setText("—")
            return
        self.diferencia.setText(formato(contada - self.fila.existencia, 3))

    def guardar(self) -> None:
        try:
            diferencia = inventario.ajustar_por_conteo(
                self.conexion,
                self.fila.producto_id,
                a_decimal(self.contada.text(), "la cantidad contada"),
                self.motivo.text(),
            )
        except (ErrorDeCampo, inventario.ErrorInventario) as error:
            avisar(self, str(error))
            return
        if diferencia == 0:
            avisar(
                self,
                "El conteo coincide con el sistema. Queda registrado, sin "
                "movimiento de inventario.",
                titulo="Conteo registrado",
            )
        self.accept()
