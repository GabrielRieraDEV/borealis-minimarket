"""Gastos operativos del periodo (RF-46)."""

import sqlite3
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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

from minimarket.dominio.reportes import CATEGORIAS_GASTO, GastoOperativo
from minimarket.servicios import ErrorServicio
from minimarket.servicios import gastos as servicio_gastos
from minimarket.servicios import tasa as servicio_tasa
from minimarket.ui.comunes import ErrorDeCampo, a_decimal, avisar, confirmar, formato

COLUMNAS = ["Periodo", "Categoria", "Descripcion", "Monto USD", "Fecha de carga"]


class PantallaGastos(QWidget):
    """RF-46. Alquiler, servicios, sueldos y otros, por mes."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self.filas: list[GastoOperativo] = []

        self.desde = QLineEdit()
        self.hasta = QLineEdit()
        for campo, texto in ((self.desde, "AAAA-MM"), (self.hasta, "AAAA-MM")):
            campo.setPlaceholderText(texto)
            campo.setMaximumWidth(120)
            campo.editingFinished.connect(self.refrescar)

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.resumen = QLabel()

        boton = QPushButton("&Registrar gasto (Ins)")
        boton.clicked.connect(self.registrar)
        repetir = QPushButton("Repetir los del &mes anterior")
        repetir.setToolTip(
            "Copia a este mes el alquiler, los sueldos y los servicios del mes "
            "pasado, con el mismo monto. Despues se corrige el que cambio."
        )
        repetir.clicked.connect(self.repetir)
        botones = QHBoxLayout()
        botones.addWidget(boton)
        botones.addWidget(repetir)
        botones.addStretch()

        filtros = QHBoxLayout()
        filtros.addWidget(QLabel("Periodo desde:"))
        filtros.addWidget(self.desde)
        filtros.addWidget(QLabel("hasta:"))
        filtros.addWidget(self.hasta)
        filtros.addStretch()

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(
            QLabel(
                "Los gastos van por mes: el alquiler de septiembre es de "
                "septiembre aunque se pague en octubre. Se cargan cada mes, o "
                "se repiten los del anterior con un clic."
            )
        )
        disposicion.addLayout(filtros)
        disposicion.addWidget(self.tabla)
        disposicion.addWidget(self.resumen)
        disposicion.addLayout(botones)

        QShortcut(QKeySequence(Qt.Key_Insert), self, self.registrar)
        self.refrescar()

    def refrescar(self) -> None:
        try:
            self.filas = servicio_gastos.listar(
                self.conexion,
                desde_periodo=self.desde.text().strip() or None,
                hasta_periodo=self.hasta.text().strip() or None,
            )
        except ErrorServicio:
            self.filas = []
        self.tabla.setRowCount(len(self.filas))
        for numero, fila in enumerate(self.filas):
            celdas = [
                fila.periodo,
                fila.categoria,
                fila.descripcion,
                formato(fila.monto_usd),
                fila.fecha,
            ]
            for columna, texto in enumerate(celdas):
                self.tabla.setItem(numero, columna, QTableWidgetItem(texto))
        total = sum((f.monto_usd for f in self.filas), start=Decimal(0))
        self.resumen.setText(
            f"{len(self.filas)} gastos · {formato(total)} USD en total"
        )

    def registrar(self) -> None:
        if DialogoGasto(self.conexion, self).exec() == QDialog.Accepted:
            self.refrescar()

    def repetir(self) -> None:
        """Los gastos fijos son los mismos todos los meses."""
        mes = servicio_tasa.hoy()[:7]
        if not confirmar(
            self,
            f"Se van a copiar a {mes} los gastos del mes anterior, con el "
            "mismo monto. ¿Seguimos?",
        ):
            return
        try:
            copiados = servicio_gastos.repetir_mes_anterior(self.conexion, mes)
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        avisar(
            self,
            f"Se cargaron {len(copiados)} gastos en {mes}. Si alguno cambio de "
            "monto, registralo de nuevo con el valor correcto.",
            "Gastos repetidos",
        )
        self.refrescar()


class DialogoGasto(QDialog):
    """RF-46. El periodo se separa de la fecha de carga a proposito."""

    def __init__(
        self, conexion: sqlite3.Connection, padre: QWidget | None = None
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.setWindowTitle("Registrar gasto operativo")

        hoy = servicio_tasa.hoy()
        self.categoria = QComboBox()
        self.categoria.addItems(CATEGORIAS_GASTO)
        self.descripcion = QLineEdit()
        self.monto = QLineEdit()
        self.periodo = QLineEdit(hoy[:7])
        self.fecha = QLineEdit(hoy)

        botones = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        botones.button(QDialogButtonBox.Save).setText("Registrar gasto")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.guardar)
        botones.rejected.connect(self.reject)

        formulario = QFormLayout()
        formulario.addRow("Categoria:", self.categoria)
        formulario.addRow("Descripcion:", self.descripcion)
        formulario.addRow("Monto USD:", self.monto)
        formulario.addRow("Periodo (AAAA-MM):", self.periodo)
        formulario.addRow("Fecha de carga:", self.fecha)

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(formulario)
        disposicion.addWidget(
            QLabel(
                "El periodo es el mes al que corresponde el gasto: el alquiler "
                "de agosto sigue siendo de agosto aunque se pague en septiembre."
            )
        )
        disposicion.addWidget(botones)

    def guardar(self) -> None:
        try:
            servicio_gastos.registrar(
                self.conexion,
                categoria=self.categoria.currentText(),
                descripcion=self.descripcion.text(),
                monto_usd=a_decimal(self.monto.text(), "el monto del gasto"),
                periodo=self.periodo.text().strip(),
                fecha=self.fecha.text().strip(),
            )
        except (ErrorDeCampo, ErrorServicio) as error:
            avisar(self, str(error))
            return
        self.accept()
