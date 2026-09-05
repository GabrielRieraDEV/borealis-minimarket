"""Gastos operativos (RF-46), fijos por mes y variables por porcentaje (1.2.0).

Dos bloques. Arriba, los gastos que rigen todos los meses sin volver a
cargarlos: un monto fijo (alquiler, sueldos) o un porcentaje de lo cobrado
(la comision del punto de venta). Abajo, lo que pesa en un mes concreto:
lo cargado a mano mas los recurrentes ya valuados con lo vendido ese mes.
"""

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
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from minimarket.dominio.reportes import (
    CATEGORIAS_GASTO,
    FIJO,
    PORCENTAJE,
    GastoRecurrente,
    RenglonGasto,
)
from minimarket.dominio.venta import MEDIOS
from minimarket.servicios import ErrorServicio
from minimarket.servicios import gastos as servicio_gastos
from minimarket.servicios import tasa as servicio_tasa
from minimarket.ui.comunes import ErrorDeCampo, a_decimal, avisar, confirmar, formato

COLUMNAS_RECURRENTES = ["Categoria", "Descripcion", "Como se calcula", "Desde", "Hasta"]
COLUMNAS_MES = ["Categoria", "Descripcion", "Monto USD", "Origen"]

NOMBRE_MEDIO = {
    "EFECTIVO": "efectivo",
    "PAGO_MOVIL": "pago movil",
    "PUNTO": "punto de venta",
    "TRANSFERENCIA": "transferencia",
}


class PantallaGastos(QWidget):
    """RF-46. Lo que se paga aunque no se venda nada, y lo que se paga por vender."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self.recurrentes: list[GastoRecurrente] = []
        self.renglones: list[RenglonGasto] = []

        self.tabla_recurrentes = _tabla(COLUMNAS_RECURRENTES, estirar=1)
        boton_recurrente = QPushButton("&Nuevo gasto de todos los meses")
        boton_recurrente.clicked.connect(self.nuevo_recurrente)
        boton_baja = QPushButton("Dar de &baja el seleccionado")
        boton_baja.clicked.connect(self.dar_de_baja)
        botones_recurrentes = QHBoxLayout()
        botones_recurrentes.addWidget(boton_recurrente)
        botones_recurrentes.addWidget(boton_baja)
        botones_recurrentes.addStretch()

        grupo_recurrentes = QGroupBox("Gastos de todos los meses")
        arriba = QVBoxLayout(grupo_recurrentes)
        arriba.addWidget(
            QLabel(
                "Se cargan una vez y rigen cada mes hasta que se den de baja. "
                "Fijos: alquiler, sueldos, internet. Por porcentaje: la comision "
                "del punto de venta, que depende de cuanto se cobre."
            )
        )
        arriba.addWidget(self.tabla_recurrentes)
        arriba.addLayout(botones_recurrentes)

        self.periodo = QLineEdit(servicio_tasa.hoy()[:7])
        self.periodo.setPlaceholderText("AAAA-MM")
        self.periodo.setMaximumWidth(110)
        self.periodo.editingFinished.connect(self.refrescar)
        self.tabla_mes = _tabla(COLUMNAS_MES, estirar=1)
        self.resumen = QLabel()
        boton_mes = QPushButton("&Registrar un gasto de este mes (Ins)")
        boton_mes.clicked.connect(self.registrar)
        fila_mes = QHBoxLayout()
        fila_mes.addWidget(QLabel("Mes:"))
        fila_mes.addWidget(self.periodo)
        fila_mes.addStretch()
        fila_mes.addWidget(boton_mes)

        self.grupo_mes = QGroupBox()
        abajo = QVBoxLayout(self.grupo_mes)
        abajo.addLayout(fila_mes)
        abajo.addWidget(self.tabla_mes)
        abajo.addWidget(self.resumen)

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(grupo_recurrentes)
        disposicion.addWidget(self.grupo_mes, stretch=1)

        QShortcut(QKeySequence(Qt.Key_Insert), self, self.registrar)
        self.refrescar()

    def refrescar(self) -> None:
        periodo = self.periodo.text().strip() or servicio_tasa.hoy()[:7]
        try:
            self.recurrentes = servicio_gastos.listar_recurrentes(self.conexion)
            self.renglones = servicio_gastos.desglose_del_mes(self.conexion, periodo)
        except ErrorServicio:
            self.recurrentes, self.renglones = [], []

        self.tabla_recurrentes.setRowCount(len(self.recurrentes))
        for numero, gasto in enumerate(self.recurrentes):
            celdas = [
                gasto.categoria,
                gasto.descripcion,
                describir(gasto),
                gasto.desde_periodo,
                gasto.hasta_periodo or "sigue vigente",
            ]
            for columna, texto in enumerate(celdas):
                self.tabla_recurrentes.setItem(numero, columna, QTableWidgetItem(texto))

        self.grupo_mes.setTitle(f"Lo que pesa en {periodo}")
        self.tabla_mes.setRowCount(len(self.renglones))
        for numero, renglon in enumerate(self.renglones):
            celdas = [
                renglon.categoria,
                renglon.descripcion,
                formato(renglon.monto_usd),
                renglon.origen,
            ]
            for columna, texto in enumerate(celdas):
                self.tabla_mes.setItem(numero, columna, QTableWidgetItem(texto))
        total = sum((r.monto_usd for r in self.renglones), start=Decimal(0))
        self.resumen.setText(
            f"{len(self.renglones)} gastos · {formato(total)} USD en el mes. "
            "Los porcentuales se recalculan solos a medida que se vende."
        )

    def registrar(self) -> None:
        if DialogoGasto(self.conexion, self).exec() == QDialog.Accepted:
            self.refrescar()

    def nuevo_recurrente(self) -> None:
        if DialogoGastoRecurrente(self.conexion, self).exec() == QDialog.Accepted:
            self.refrescar()

    def dar_de_baja(self) -> None:
        fila = self.tabla_recurrentes.currentRow()
        if not 0 <= fila < len(self.recurrentes):
            avisar(self, "Elegi un gasto de la tabla de arriba.")
            return
        gasto = self.recurrentes[fila]
        if gasto.hasta_periodo is not None:
            avisar(self, f"«{gasto.descripcion}» ya esta dado de baja.")
            return
        mes = servicio_tasa.hoy()[:7]
        if not confirmar(
            self,
            f"«{gasto.descripcion}» se cuenta por ultima vez en {mes} y deja de "
            "regir desde el mes que viene. ¿Seguimos?",
        ):
            return
        try:
            servicio_gastos.dar_de_baja_recurrente(self.conexion, gasto.id, mes)
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        self.refrescar()


def describir(gasto: GastoRecurrente) -> str:
    if gasto.tipo == FIJO:
        return f"{formato(gasto.monto_usd)} USD cada mes"
    base = "todo lo cobrado" if gasto.medio is None else f"lo cobrado por {NOMBRE_MEDIO[gasto.medio]}"
    return f"{gasto.porcentaje.normalize()} % de {base}"


class DialogoGastoRecurrente(QDialog):
    """Un gasto que rige todos los meses: fijo o porcentaje de lo cobrado."""

    def __init__(
        self, conexion: sqlite3.Connection, padre: QWidget | None = None
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.setWindowTitle("Gasto de todos los meses")
        self.setMinimumWidth(460)

        self.fijo = QRadioButton("Monto fijo por mes (alquiler, sueldos, internet)")
        self.fijo.setChecked(True)
        self.porcentual = QRadioButton("Porcentaje de lo cobrado (comision del punto)")
        self.fijo.toggled.connect(self._segun_tipo)

        self.categoria = QComboBox()
        self.categoria.addItems(CATEGORIAS_GASTO)
        self.descripcion = QLineEdit()
        self.monto = QLineEdit()
        self.monto.setPlaceholderText("USD por mes")
        self.porcentaje = QLineEdit()
        self.porcentaje.setPlaceholderText("por ejemplo 3")
        self.medio = QComboBox()
        self.medio.addItem("Todo lo cobrado", None)
        for medio in MEDIOS:
            self.medio.addItem(NOMBRE_MEDIO[medio].capitalize(), medio)
        self.medio.setCurrentIndex(self.medio.findData("PUNTO"))
        self.desde = QLineEdit(servicio_tasa.hoy()[:7])

        self.formulario = QFormLayout()
        self.formulario.addRow("Categoria:", self.categoria)
        self.formulario.addRow("Descripcion:", self.descripcion)
        self.formulario.addRow("Monto mensual USD:", self.monto)
        self.formulario.addRow("Porcentaje (%):", self.porcentaje)
        self.formulario.addRow("Sobre lo cobrado por:", self.medio)
        self.formulario.addRow("Rige desde (AAAA-MM):", self.desde)

        botones = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        botones.button(QDialogButtonBox.Save).setText("Guardar")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.guardar)
        botones.rejected.connect(self.reject)

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(self.fijo)
        disposicion.addWidget(self.porcentual)
        disposicion.addLayout(self.formulario)
        disposicion.addWidget(botones)
        self._segun_tipo()

    def _segun_tipo(self) -> None:
        es_fijo = self.fijo.isChecked()
        for campo, visible in (
            (self.monto, es_fijo),
            (self.porcentaje, not es_fijo),
            (self.medio, not es_fijo),
        ):
            campo.setVisible(visible)
            self.formulario.labelForField(campo).setVisible(visible)

    def guardar(self) -> None:
        es_fijo = self.fijo.isChecked()
        try:
            servicio_gastos.registrar_recurrente(
                self.conexion,
                categoria=self.categoria.currentText(),
                descripcion=self.descripcion.text(),
                tipo=FIJO if es_fijo else PORCENTAJE,
                monto_usd=a_decimal(self.monto.text(), "el monto mensual") if es_fijo else Decimal(0),
                porcentaje=Decimal(0) if es_fijo else a_decimal(self.porcentaje.text(), "el porcentaje"),
                medio=None if es_fijo else self.medio.currentData(),
                desde_periodo=self.desde.text().strip(),
            )
        except (ErrorDeCampo, ErrorServicio) as error:
            avisar(self, str(error))
            return
        self.accept()


class DialogoGasto(QDialog):
    """RF-46. Un gasto de un mes concreto: lo que no se repite."""

    def __init__(
        self, conexion: sqlite3.Connection, padre: QWidget | None = None
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.setWindowTitle("Registrar un gasto de este mes")

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
        formulario.addRow("Mes (AAAA-MM):", self.periodo)
        formulario.addRow("Fecha de carga:", self.fecha)

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(formulario)
        disposicion.addWidget(
            QLabel(
                "Para lo que se paga una sola vez: una reparacion, una multa.\n"
                "Lo que se repite todos los meses va en «Gastos de todos los meses»."
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


def _tabla(columnas: list[str], estirar: int) -> QTableWidget:
    tabla = QTableWidget(0, len(columnas))
    tabla.setHorizontalHeaderLabels(columnas)
    tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
    tabla.setSelectionMode(QAbstractItemView.SingleSelection)
    tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
    encabezado = tabla.horizontalHeader()
    encabezado.setSectionResizeMode(QHeaderView.ResizeToContents)
    encabezado.setSectionResizeMode(estirar, QHeaderView.Stretch)
    return tabla
