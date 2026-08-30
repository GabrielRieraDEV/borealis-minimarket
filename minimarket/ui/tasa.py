"""Dialogo de carga de la tasa del dia (RF-09 a RF-13)."""

import sqlite3

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from minimarket.servicios import ErrorServicio
from minimarket.servicios import tasa as servicio_tasa
from minimarket.ui.comunes import ErrorDeCampo, a_decimal, avisar, formato

ORIGENES = {"BCV_AUTO": "BCV (automatica)", "MANUAL": "Manual"}


class DialogoTasa(QDialog):
    """Carga manual (RF-11) y consulta al BCV (RF-10), con el historico."""

    def __init__(
        self, conexion: sqlite3.Connection, padre: QWidget | None = None
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.setWindowTitle("Tasa de cambio del dia")
        self.resize(520, 420)

        self.estado = QLabel()
        self.valor = QLineEdit()
        self.valor.setPlaceholderText("Bolivares por dolar, por ejemplo 210,500000")

        boton_bcv = QPushButton("Consultar al &BCV")
        boton_bcv.clicked.connect(self.consultar_bcv)

        self.historico = QTableWidget(0, 3)
        self.historico.setHorizontalHeaderLabels(["Fecha", "Tasa", "Origen"])
        self.historico.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        botones = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Close, parent=self
        )
        botones.button(QDialogButtonBox.Save).setText("Guardar tasa")
        botones.button(QDialogButtonBox.Close).setText("Cerrar")
        botones.accepted.connect(self.guardar)
        botones.rejected.connect(self.reject)

        formulario = QFormLayout()
        formulario.addRow("Tasa de hoy:", self.valor)

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(self.estado)
        disposicion.addLayout(formulario)
        disposicion.addWidget(boton_bcv)
        disposicion.addWidget(QLabel("Historico (RF-13):"))
        disposicion.addWidget(self.historico)
        disposicion.addWidget(botones)

        self.refrescar()

    def refrescar(self) -> None:
        vigente = servicio_tasa.tasa_del_dia(self.conexion)
        self.estado.setText(
            f"Tasa de hoy: {formato(vigente, 6)} Bs/USD"
            if vigente is not None
            else "Todavia no hay tasa cargada para hoy. Sin tasa no se puede "
            "abrir la caja ni registrar ventas."
        )
        registros = servicio_tasa.historico(self.conexion)[:30]
        self.historico.setRowCount(len(registros))
        for fila, registro in enumerate(registros):
            celdas = [
                registro.fecha,
                formato(registro.valor, 6),
                ORIGENES.get(registro.origen, registro.origen),
            ]
            for columna, texto in enumerate(celdas):
                self.historico.setItem(fila, columna, QTableWidgetItem(texto))

    def consultar_bcv(self) -> None:
        """RF-10. Si falla no bloquea nada: queda la carga manual (RN-04)."""
        valor = servicio_tasa.actualizar_desde_bcv(self.conexion)
        if valor is None:
            avisar(
                self,
                "No se pudo consultar la tasa del BCV. Revisa la conexion o "
                "cargala a mano en el campo de arriba.",
            )
            return
        self.valor.setText(str(valor))
        self.refrescar()

    def guardar(self) -> None:
        try:
            valor = a_decimal(self.valor.text(), "la tasa de cambio")
            servicio_tasa.registrar_manual(self.conexion, valor)
        except (ErrorDeCampo, ErrorServicio) as error:
            avisar(self, str(error))
            return
        self.accept()
