"""Perdidas y vencimientos (RF-28 a RF-32).

Las dos cosas viven en la misma pantalla porque se usan juntas: se mira que
esta por vencer y se da de baja ahi mismo, sin cambiar de pestana.
"""

import sqlite3
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from minimarket.dominio.inventario import Perdida, SaldoLoteProducto
from minimarket.servicios import ErrorServicio
from minimarket.servicios import inventario as servicio_inventario
from minimarket.servicios import perdidas as servicio_perdidas
from minimarket.servicios import tasa as servicio_tasa
from minimarket.ui.comunes import (
    ErrorDeCampo,
    a_decimal,
    avisar,
    combo_productos,
    confirmar,
    formato,
)

COLUMNAS_PERDIDA = [
    "Fecha",
    "Producto",
    "Motivo",
    "Cantidad",
    "Costo unitario USD",
    "Costo total USD",
    "Observacion",
]
COLUMNAS_LOTE = [
    "Producto",
    "Lote",
    "Vence",
    "Dias",
    "Cantidad",
    "Valorizado USD",
    "Estado",
]
ROJO_SUAVE = QColor(255, 224, 224)
AMARILLO_SUAVE = QColor(255, 246, 214)


class PantallaPerdidas(QWidget):
    """RF-28 a RF-32, en dos paginas: lo que se perdio y lo que esta por vencer."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self.registro = PaginaRegistro(conexion)
        self.vencimientos = PaginaVencimientos(conexion, self.registro.refrescar)

        paginas = QTabWidget()
        paginas.addTab(self.registro, "&Perdidas registradas")
        paginas.addTab(self.vencimientos, "Por &vencer (RF-31)")

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(paginas)

    def refrescar(self) -> None:
        self.registro.refrescar()
        self.vencimientos.refrescar()


class PaginaRegistro(QWidget):
    """RF-28 / RF-53. Alta de perdidas y listado del periodo."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self.filas: list[Perdida] = []

        self.desde = QLineEdit(servicio_tasa.hoy()[:8] + "01")
        self.hasta = QLineEdit(servicio_tasa.hoy())
        self.motivo = QComboBox()
        for campo in (self.desde, self.hasta):
            campo.setMaximumWidth(120)
            campo.editingFinished.connect(self.refrescar)
        self.motivo.currentIndexChanged.connect(self.refrescar)

        self.tabla = _tabla(COLUMNAS_PERDIDA)
        self.resumen = QLabel()

        filtros = QHBoxLayout()
        filtros.addWidget(QLabel("Desde:"))
        filtros.addWidget(self.desde)
        filtros.addWidget(QLabel("Hasta:"))
        filtros.addWidget(self.hasta)
        filtros.addWidget(QLabel("Motivo:"))
        filtros.addWidget(self.motivo, 1)

        botones = QHBoxLayout()
        for texto, destino in (
            ("&Registrar perdida (Ins)", self.registrar),
            ("Nuevo &motivo", self.nuevo_motivo),
        ):
            boton = QPushButton(texto)
            boton.clicked.connect(destino)
            botones.addWidget(boton)
        botones.addStretch()

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(filtros)
        disposicion.addWidget(self.tabla)
        disposicion.addWidget(self.resumen)
        disposicion.addLayout(botones)

        QShortcut(QKeySequence(Qt.Key_Insert), self, self.registrar)
        self._cargar_motivos()
        self.refrescar()

    def _cargar_motivos(self) -> None:
        actual = self.motivo.currentData()
        self.motivo.blockSignals(True)
        self.motivo.clear()
        self.motivo.addItem("Todos", None)
        for motivo in servicio_perdidas.motivos(self.conexion):
            self.motivo.addItem(motivo.nombre, motivo.id)
        if actual is not None:
            self.motivo.setCurrentIndex(max(self.motivo.findData(actual), 0))
        self.motivo.blockSignals(False)

    def refrescar(self) -> None:
        try:
            self.filas = servicio_perdidas.listar(
                self.conexion,
                desde=self.desde.text().strip() or None,
                hasta=self.hasta.text().strip() or None,
                motivo_id=self.motivo.currentData(),
            )
        except ErrorServicio:
            self.filas = []
        self.tabla.setRowCount(len(self.filas))
        for numero, fila in enumerate(self.filas):
            celdas = [
                fila.fecha,
                fila.producto or "",
                fila.motivo or "",
                formato(fila.cantidad, 3),
                formato(fila.costo_unitario_usd, 4)
                if fila.determinable
                else "sin costo",
                formato(fila.costo_total_usd),
                fila.observacion or "",
            ]
            for columna, texto in enumerate(celdas):
                self.tabla.setItem(numero, columna, QTableWidgetItem(texto))
        total = sum((f.costo_total_usd for f in self.filas), start=Decimal(0))
        self.resumen.setText(
            f"{len(self.filas)} perdidas · {formato(total)} USD, que se restan "
            "del resultado del periodo (RN-29)"
        )

    def registrar(self) -> None:
        if DialogoPerdida(self.conexion, self).exec() == QDialog.Accepted:
            self.refrescar()

    def nuevo_motivo(self) -> None:
        """RF-29. Los motivos son ampliables."""
        nombre, acepto = QInputDialog.getText(
            self, "Nuevo motivo de perdida", "Nombre del motivo:"
        )
        if not acepto:
            return
        try:
            servicio_perdidas.crear_motivo(self.conexion, nombre)
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        self._cargar_motivos()


class PaginaVencimientos(QWidget):
    """RF-31 / RF-32. La alerta y la baja del lote, en el mismo lugar."""

    def __init__(self, conexion: sqlite3.Connection, al_dar_de_baja) -> None:
        super().__init__()
        self.conexion = conexion
        self.al_dar_de_baja = al_dar_de_baja
        self.filas: list[SaldoLoteProducto] = []

        self.tabla = _tabla(COLUMNAS_LOTE)
        self.tabla.itemActivated.connect(lambda _: self.dar_de_baja())
        self.resumen = QLabel()

        boton = QPushButton("Dar de &baja el lote como perdida (Supr)")
        boton.clicked.connect(self.dar_de_baja)
        botones = QHBoxLayout()
        botones.addWidget(boton)
        botones.addStretch()

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(
            QLabel(
                "Lotes con existencia dentro del plazo de aviso de cada "
                "producto (RN-17). Un lote vencido NO bloquea la venta: la "
                "decision de darlo de baja es del negocio."
            )
        )
        disposicion.addWidget(self.tabla)
        disposicion.addWidget(self.resumen)
        disposicion.addLayout(botones)

        QShortcut(QKeySequence(Qt.Key_Delete), self, self.dar_de_baja)
        self.refrescar()

    def refrescar(self) -> None:
        try:
            self.filas = servicio_perdidas.proximos_a_vencer(self.conexion)
        except ErrorServicio:
            self.filas = []
        self.tabla.setRowCount(len(self.filas))
        for numero, fila in enumerate(self.filas):
            dias = fila.dias_para_vencer()
            vencido = dias < 0
            celdas = [
                fila.producto,
                fila.codigo or f"#{fila.lote_id}",
                fila.fecha_vencimiento,
                str(dias),
                formato(fila.cantidad, 3),
                formato(fila.valorizacion),
                "Vencido" if vencido else "Por vencer",
            ]
            for columna, texto in enumerate(celdas):
                celda = QTableWidgetItem(texto)
                celda.setBackground(QBrush(ROJO_SUAVE if vencido else AMARILLO_SUAVE))
                self.tabla.setItem(numero, columna, celda)
        vencidos = sum(1 for f in self.filas if f.vencido())
        expuesto = sum((f.valorizacion for f in self.filas), start=Decimal(0))
        self.resumen.setText(
            f"{len(self.filas)} lotes en alerta · {vencidos} ya vencidos · "
            f"{formato(expuesto)} USD en juego"
        )

    def dar_de_baja(self) -> None:
        """RF-32. Da de baja el lote entero con el motivo «vencido»."""
        numero = self.tabla.currentRow()
        if not 0 <= numero < len(self.filas):
            avisar(self, "Elegi un lote de la lista.")
            return
        lote = self.filas[numero]
        if not confirmar(
            self,
            f"Se van a dar de baja {formato(lote.cantidad, 3)} unidades de "
            f"«{lote.producto}» del lote que vence el {lote.fecha_vencimiento}, "
            f"por {formato(lote.valorizacion)} USD.\n\n¿Confirmas la perdida?",
            "Dar de baja el lote",
        ):
            return
        try:
            servicio_perdidas.dar_de_baja_lote(self.conexion, lote.lote_id)
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        self.refrescar()
        self.al_dar_de_baja()


class DialogoPerdida(QDialog):
    """RF-28 / RF-30. Muestra la existencia y el costo antes de confirmar."""

    def __init__(
        self, conexion: sqlite3.Connection, padre: QWidget | None = None
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.setWindowTitle("Registrar perdida")

        self.producto = combo_productos(conexion)
        self.producto.currentIndexChanged.connect(self.actualizar_detalle)
        self.cantidad = QLineEdit("1")
        self.cantidad.textChanged.connect(self.actualizar_detalle)
        self.motivo = QComboBox()
        for motivo in servicio_perdidas.motivos(conexion):
            self.motivo.addItem(motivo.nombre, motivo.id)
        self.fecha = QLineEdit(servicio_tasa.hoy())
        self.fecha.editingFinished.connect(self.actualizar_detalle)
        self.observacion = QLineEdit()
        self.existencia = QLabel("—")
        self.valorizacion = QLabel("—")

        botones = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        botones.button(QDialogButtonBox.Save).setText("Registrar perdida")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.guardar)
        botones.rejected.connect(self.reject)

        formulario = QFormLayout()
        formulario.addRow("Producto:", self.producto)
        formulario.addRow("Existencia actual:", self.existencia)
        formulario.addRow("Cantidad perdida:", self.cantidad)
        formulario.addRow("Motivo:", self.motivo)
        formulario.addRow("Fecha (AAAA-MM-DD):", self.fecha)
        formulario.addRow("Se valoriza en:", self.valorizacion)
        formulario.addRow("Observacion:", self.observacion)

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(formulario)
        disposicion.addWidget(
            QLabel(
                "La perdida se valoriza al ultimo costo vigente en su fecha "
                "(RN-18) y descuenta el lote mas proximo a vencer (RN-15)."
            )
        )
        disposicion.addWidget(botones)

    def actualizar_detalle(self) -> None:
        producto_id = self.producto.currentData()
        if producto_id is None:
            self.existencia.setText("—")
            self.valorizacion.setText("—")
            return
        self.existencia.setText(
            formato(servicio_inventario.existencia(self.conexion, producto_id), 3)
        )
        try:
            cantidad = a_decimal(self.cantidad.text(), "la cantidad")
        except ErrorDeCampo:
            self.valorizacion.setText("—")
            return
        costo = servicio_perdidas.costo_a_fecha(
            self.conexion, producto_id, self.fecha.text().strip()
        )
        if costo is None:
            self.valorizacion.setText("sin costo de compra: se registra en 0,00")
            return
        self.valorizacion.setText(
            f"{formato(cantidad * costo)} USD, al costo de {formato(costo, 4)}"
        )

    def guardar(self) -> None:
        if self.producto.currentData() is None:
            avisar(self, "Elegi el producto que se perdio.")
            return
        try:
            servicio_perdidas.registrar(
                self.conexion,
                producto_id=self.producto.currentData(),
                cantidad=a_decimal(self.cantidad.text(), "la cantidad"),
                motivo_id=self.motivo.currentData(),
                fecha=self.fecha.text().strip(),
                observacion=self.observacion.text().strip() or None,
            )
        except (ErrorDeCampo, ErrorServicio) as error:
            avisar(self, str(error))
            return
        self.accept()


def _tabla(columnas: list[str]) -> QTableWidget:
    tabla = QTableWidget(0, len(columnas))
    tabla.setHorizontalHeaderLabels(columnas)
    tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
    tabla.setSelectionMode(QAbstractItemView.SingleSelection)
    tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    return tabla
