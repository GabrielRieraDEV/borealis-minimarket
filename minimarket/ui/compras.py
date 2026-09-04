"""Pantallas de compras y proveedores (RF-14 a RF-21)."""

import sqlite3
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from minimarket.dominio.compra import ANULADA, Compra, LineaCompra, Proveedor
from minimarket.servicios import ErrorServicio
from minimarket.servicios import catalogo, compras, usuario_actual
from minimarket.servicios import tasa as servicio_tasa
from minimarket.ui.comunes import (
    ErrorDeCampo,
    a_decimal,
    avisar,
    combo_productos,
    confirmar,
    formato,
)

COLUMNAS = ["Fecha", "Documento", "Proveedor", "Total USD", "Saldo USD", "Estado"]
COLUMNAS_LINEA = [
    "Producto",
    "Present.",
    "Unid. x present.",
    "Costo present. USD",
    "Vencimiento",
    "Unidades",
    "Costo unit. USD",
    "Total USD",
]


class PantallaCompras(QWidget):
    """Listado de compras con alta, pago y anulacion."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self.compras: list[Compra] = []

        self.proveedor = QComboBox()
        self.proveedor.addItem("Todos los proveedores", None)
        self.proveedor.currentIndexChanged.connect(self.refrescar)
        self.incluir_anuladas = QCheckBox("Incluir compras anuladas")
        self.incluir_anuladas.stateChanged.connect(self.refrescar)

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabla.itemActivated.connect(lambda _: self.ver())

        botones = QHBoxLayout()
        for texto, destino in (
            ("&Nueva compra (Ins)", self.nueva),
            ("&Ver detalle (F4)", self.ver),
            ("Registrar &pago (F6)", self.pagar),
            ("&Anular (Supr)", self.anular),
        ):
            boton = QPushButton(texto)
            boton.clicked.connect(destino)
            botones.addWidget(boton)
        botones.addStretch()

        filtros = QHBoxLayout()
        filtros.addWidget(self.proveedor)
        filtros.addWidget(self.incluir_anuladas)
        filtros.addStretch()

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(filtros)
        disposicion.addWidget(self.tabla)
        disposicion.addLayout(botones)

        # RNF-08: todo alcanzable sin mouse.
        QShortcut(QKeySequence(Qt.Key_Insert), self, self.nueva)
        QShortcut(QKeySequence(Qt.Key_F4), self, self.ver)
        QShortcut(QKeySequence(Qt.Key_F6), self, self.pagar)
        QShortcut(QKeySequence(Qt.Key_Delete), self, self.anular)

        self.refrescar()

    def refrescar(self) -> None:
        seleccionado = self.proveedor.currentData()
        self.proveedor.blockSignals(True)
        self.proveedor.clear()
        self.proveedor.addItem("Todos los proveedores", None)
        self.proveedores = {}
        for proveedor in compras.listar_proveedores(self.conexion, solo_activos=False):
            self.proveedores[proveedor.id] = proveedor.nombre
            self.proveedor.addItem(proveedor.nombre, proveedor.id)
        indice = self.proveedor.findData(seleccionado)
        self.proveedor.setCurrentIndex(max(indice, 0))
        self.proveedor.blockSignals(False)

        self.compras = compras.listar_compras(
            self.conexion, proveedor_id=self.proveedor.currentData()
        )
        if not self.incluir_anuladas.isChecked():
            self.compras = [c for c in self.compras if c.estado != ANULADA]

        self.tabla.setRowCount(len(self.compras))
        for fila, compra in enumerate(self.compras):
            celdas = [
                compra.fecha,
                compra.numero_documento or "",
                self.proveedores.get(compra.proveedor_id, ""),
                formato(compra.total_usd),
                formato(compra.saldo_pendiente_usd),
                "Anulada" if compra.estado == ANULADA else "Confirmada",
            ]
            for columna, texto in enumerate(celdas):
                self.tabla.setItem(fila, columna, QTableWidgetItem(texto))

    def seleccionada(self) -> Compra | None:
        fila = self.tabla.currentRow()
        return self.compras[fila] if 0 <= fila < len(self.compras) else None

    def _exigir(self) -> Compra | None:
        compra = self.seleccionada()
        if compra is None:
            avisar(self, "Elegi una compra de la lista.")
        return compra

    def nueva(self) -> None:
        if DialogoCompra(self.conexion, None, self).exec() == QDialog.Accepted:
            self.refrescar()

    def ver(self) -> None:
        compra = self._exigir()
        if compra is not None:
            # `listar` trae el encabezado sin detalle; el dialogo lo necesita.
            completa = compras.obtener_compra(self.conexion, compra.id)
            DialogoCompra(self.conexion, completa, self).exec()

    def pagar(self) -> None:
        """RF-19."""
        compra = self._exigir()
        if compra is None:
            return
        if DialogoPago(self.conexion, compra, self).exec() == QDialog.Accepted:
            self.refrescar()

    def anular(self) -> None:
        """RF-20. Movimientos inversos; el registro se conserva."""
        compra = self._exigir()
        if compra is None:
            return
        if not confirmar(
            self,
            f"¿Anular la compra del {compra.fecha} por "
            f"{formato(compra.total_usd)} USD?\n\nSe generan movimientos "
            "inversos de inventario. El registro no se borra.",
        ):
            return
        try:
            compras.anular_compra(self.conexion, compra.id, "Anulada desde pantalla")
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        self.refrescar()


class DialogoCompra(QDialog):
    """Alta de compra con detalle (RF-15 a RF-18, RF-21).

    Con una compra ya confirmada solo muestra: nada se modifica (RN-13).
    """

    def __init__(
        self,
        conexion: sqlite3.Connection,
        compra: Compra | None,
        padre: QWidget | None = None,
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.solo_lectura = compra is not None
        self.lineas: list[LineaCompra] = []
        self.nombres: dict[int, str] = {}
        self.setWindowTitle(
            "Compra registrada" if self.solo_lectura else "Nueva compra"
        )
        self.resize(940, 560)

        self.proveedor = QComboBox()
        for proveedor in compras.listar_proveedores(conexion):
            self.proveedor.addItem(proveedor.nombre, proveedor.id)
        self.fecha = QLineEdit(servicio_tasa.hoy())
        self.documento = QLineEdit()
        self.observacion = QLineEdit()

        self.tabla = QTableWidget(0, len(COLUMNAS_LINEA))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS_LINEA)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        self.total = QLabel()

        formulario = QFormLayout()
        formulario.addRow("Proveedor:", self.proveedor)
        formulario.addRow("Fecha (AAAA-MM-DD):", self.fecha)
        formulario.addRow("Numero de documento:", self.documento)
        formulario.addRow("Observacion:", self.observacion)

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(formulario)
        disposicion.addWidget(QLabel("Detalle:"))
        disposicion.addWidget(self.tabla)

        if self.solo_lectura:
            self._cargar(compra)
            botones = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
            botones.button(QDialogButtonBox.Close).setText("Cerrar")
            botones.rejected.connect(self.reject)
        else:
            disposicion.addLayout(self._carga_de_lineas())
            botones = QDialogButtonBox(
                QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
            )
            botones.button(QDialogButtonBox.Save).setText("Confirmar compra")
            botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
            botones.accepted.connect(self.confirmar)
            botones.rejected.connect(self.reject)

        disposicion.addWidget(self.total)
        disposicion.addWidget(botones)
        self._pintar()

    # ponytail: el detalle se edita agregando y quitando lineas, no celda por
    # celda. La edicion en sitio de un QTableWidget con un selector de producto
    # adentro es varias veces mas codigo y peor con teclado. Si el minimarket
    # pide corregir una linea sin rehacerla, ahi si conviene.
    def _carga_de_lineas(self) -> QHBoxLayout:
        self.producto = combo_productos(self.conexion)
        self.presentaciones = QLineEdit("1")
        self.presentaciones.setMaximumWidth(70)
        self.unidades = QLineEdit("1")  # RN-06: por linea, no en la ficha
        self.unidades.setMaximumWidth(70)
        self.costo = QLineEdit()
        self.costo.setMaximumWidth(110)
        self.costo.setPlaceholderText("Costo present.")
        self.vencimiento = QLineEdit()
        self.vencimiento.setMaximumWidth(120)
        self.vencimiento.setPlaceholderText("Vence AAAA-MM-DD")

        agregar = QPushButton("&Agregar (F9)")
        agregar.clicked.connect(self.agregar_linea)
        quitar = QPushButton("&Quitar (Supr)")
        quitar.clicked.connect(self.quitar_linea)
        QShortcut(QKeySequence(Qt.Key_F9), self, self.agregar_linea)
        QShortcut(QKeySequence(Qt.Key_Delete), self.tabla, self.quitar_linea)

        fila = QHBoxLayout()
        fila.addWidget(self.producto, stretch=1)
        for campo in (
            self.presentaciones,
            self.unidades,
            self.costo,
            self.vencimiento,
        ):
            fila.addWidget(campo)
        fila.addWidget(agregar)
        fila.addWidget(quitar)
        return fila

    def _cargar(self, compra: Compra) -> None:
        self.proveedor.setCurrentIndex(self.proveedor.findData(compra.proveedor_id))
        self.proveedor.setEnabled(False)
        self.fecha.setText(compra.fecha)
        self.documento.setText(compra.numero_documento or "")
        self.observacion.setText(compra.observacion or "")
        for campo in (self.fecha, self.documento, self.observacion):
            campo.setReadOnly(True)
        self.lineas = compra.lineas

    def agregar_linea(self) -> None:
        producto_id = self.producto.currentData()
        if producto_id is None:
            avisar(self, "Elegi un producto para la linea.")
            return
        try:
            linea = LineaCompra(
                producto_id=producto_id,
                cant_presentacion=a_decimal(
                    self.presentaciones.text(), "la cantidad de presentaciones"
                ),
                unid_x_presentacion=a_decimal(
                    self.unidades.text(), "las unidades por presentacion"
                ),
                costo_present_usd=a_decimal(
                    self.costo.text(), "el costo de la presentacion"
                ),
                fecha_vencimiento=self.vencimiento.text().strip() or None,
            )
        except ErrorDeCampo as error:
            avisar(self, str(error))
            return
        self.lineas.append(linea)
        self.costo.clear()
        self.vencimiento.clear()
        self.producto.setCurrentIndex(-1)
        self.producto.setFocus()
        self._pintar()

    def quitar_linea(self) -> None:
        fila = self.tabla.currentRow()
        if 0 <= fila < len(self.lineas):
            self.lineas.pop(fila)
            self._pintar()

    def _pintar(self) -> None:
        total = Decimal(0)
        self.tabla.setRowCount(len(self.lineas))
        for fila, linea in enumerate(self.lineas):
            if linea.producto_id not in self.nombres:
                producto = catalogo.obtener_producto(self.conexion, linea.producto_id)
                self.nombres[linea.producto_id] = producto.nombre if producto else "?"
            celdas = [
                self.nombres[linea.producto_id],
                formato(linea.cant_presentacion, 3),
                formato(linea.unid_x_presentacion, 3),
                formato(linea.costo_present_usd, 4),
                linea.fecha_vencimiento or "",
                formato(linea.cantidad_unidades, 3),
                formato(linea.costo_unitario_usd, 4),  # RN-06
                formato(linea.total_usd),
            ]
            for columna, texto in enumerate(celdas):
                self.tabla.setItem(fila, columna, QTableWidgetItem(texto))
            total += linea.total_usd
        self.total.setText(f"Total de la compra: {formato(total)} USD")

    def confirmar(self) -> None:
        compra = Compra(
            proveedor_id=self.proveedor.currentData(),
            fecha=self.fecha.text().strip(),
            usuario_id=usuario_actual(),
            numero_documento=self.documento.text().strip() or None,
            observacion=self.observacion.text().strip() or None,
            lineas=self.lineas,
        )
        try:
            resultado = compras.registrar_compra(self.conexion, compra)
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        if resultado.avisos:
            self._avisar_margenes(resultado.avisos)
        self.accept()

    def _avisar_margenes(self, avisos: list[compras.AvisoMargen]) -> None:
        """El nuevo costo dejo precios cortos. Se informa; no se toca nada."""
        detalle = "\n".join(
            f"· {aviso.producto.nombre}: margen "
            f"{formato(aviso.margen_actual)} % contra un objetivo de "
            f"{formato(aviso.margen_objetivo)} %. "
            f"Precio sugerido {formato(aviso.precio_sugerido_usd, 4)} USD."
            for aviso in avisos
        )
        QMessageBox.information(
            self,
            "Precios por debajo del margen",
            "Con el costo recien cargado, estos productos quedaron por debajo "
            "de su margen objetivo:\n\n"
            f"{detalle}\n\nRevisalos en la pantalla de productos.",
        )


class DialogoPago(QDialog):
    """RF-19. Pago parcial o total contra el saldo de una compra."""

    def __init__(
        self,
        conexion: sqlite3.Connection,
        compra: Compra,
        padre: QWidget | None = None,
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.compra = compra
        self.setWindowTitle("Pago a proveedor")

        self.monto = QLineEdit(str(compra.saldo_pendiente_usd))
        self.medio = QComboBox()
        self.medio.addItems(compras.MEDIOS_PAGO)
        self.fecha = QLineEdit(servicio_tasa.hoy())
        self.referencia = QLineEdit()

        botones = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        botones.button(QDialogButtonBox.Save).setText("Registrar pago")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.guardar)
        botones.rejected.connect(self.reject)

        formulario = QFormLayout()
        formulario.addRow("Total de la compra:", QLabel(formato(compra.total_usd)))
        formulario.addRow(
            "Saldo pendiente USD:", QLabel(formato(compra.saldo_pendiente_usd))
        )
        formulario.addRow("Monto a pagar USD:", self.monto)
        formulario.addRow("Medio:", self.medio)
        formulario.addRow("Fecha (AAAA-MM-DD):", self.fecha)
        formulario.addRow("Referencia:", self.referencia)

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(formulario)
        disposicion.addWidget(botones)

    def guardar(self) -> None:
        try:
            compras.registrar_pago(
                self.conexion,
                self.compra.id,
                a_decimal(self.monto.text(), "el monto del pago"),
                self.medio.currentText(),
                fecha=self.fecha.text().strip(),
                referencia=self.referencia.text().strip() or None,
            )
        except (ErrorDeCampo, ErrorServicio) as error:
            avisar(self, str(error))
            return
        self.accept()


class PantallaProveedores(QWidget):
    """RF-14."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self.proveedores: list[Proveedor] = []

        self.incluir_inactivos = QCheckBox("Incluir proveedores dados de baja")
        self.incluir_inactivos.stateChanged.connect(self.refrescar)

        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels(
            ["Nombre", "RIF", "Telefono", "Contacto", "Estado"]
        )
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla.itemActivated.connect(lambda _: self.editar())

        botones = QHBoxLayout()
        for texto, destino in (
            ("&Nuevo (Ins)", self.nuevo),
            ("&Editar (F4)", self.editar),
            ("Dar de &baja / reactivar (Supr)", self.cambiar_estado),
        ):
            boton = QPushButton(texto)
            boton.clicked.connect(destino)
            botones.addWidget(boton)
        botones.addStretch()

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(self.incluir_inactivos)
        disposicion.addWidget(self.tabla)
        disposicion.addLayout(botones)

        QShortcut(QKeySequence(Qt.Key_Insert), self, self.nuevo)
        QShortcut(QKeySequence(Qt.Key_F4), self, self.editar)
        QShortcut(QKeySequence(Qt.Key_Delete), self, self.cambiar_estado)

        self.refrescar()

    def refrescar(self) -> None:
        self.proveedores = compras.listar_proveedores(
            self.conexion, solo_activos=not self.incluir_inactivos.isChecked()
        )
        self.tabla.setRowCount(len(self.proveedores))
        for fila, proveedor in enumerate(self.proveedores):
            celdas = [
                proveedor.nombre,
                proveedor.rif or "",
                proveedor.telefono or "",
                proveedor.contacto or "",
                "Activo" if proveedor.activo else "De baja",
            ]
            for columna, texto in enumerate(celdas):
                self.tabla.setItem(fila, columna, QTableWidgetItem(texto))

    def seleccionado(self) -> Proveedor | None:
        fila = self.tabla.currentRow()
        return self.proveedores[fila] if 0 <= fila < len(self.proveedores) else None

    def nuevo(self) -> None:
        self._abrir(None)

    def editar(self) -> None:
        proveedor = self.seleccionado()
        if proveedor is None:
            avisar(self, "Elegi un proveedor de la lista.")
            return
        self._abrir(proveedor)

    def cambiar_estado(self) -> None:
        proveedor = self.seleccionado()
        if proveedor is None:
            avisar(self, "Elegi un proveedor de la lista.")
            return
        compras.cambiar_estado_proveedor(
            self.conexion, proveedor.id, not proveedor.activo
        )
        self.refrescar()

    def _abrir(self, proveedor: Proveedor | None) -> None:
        if DialogoProveedor(self.conexion, proveedor, self).exec() == QDialog.Accepted:
            self.refrescar()


class DialogoProveedor(QDialog):
    def __init__(
        self,
        conexion: sqlite3.Connection,
        proveedor: Proveedor | None,
        padre: QWidget | None = None,
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.proveedor = proveedor
        self.setWindowTitle(
            "Nuevo proveedor" if proveedor is None else "Editar proveedor"
        )

        self.nombre = QLineEdit()
        self.rif = QLineEdit()
        self.telefono = QLineEdit()
        self.contacto = QLineEdit()
        if proveedor is not None:
            self.nombre.setText(proveedor.nombre)
            self.rif.setText(proveedor.rif or "")
            self.telefono.setText(proveedor.telefono or "")
            self.contacto.setText(proveedor.contacto or "")

        botones = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        botones.button(QDialogButtonBox.Save).setText("Guardar")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.guardar)
        botones.rejected.connect(self.reject)

        formulario = QFormLayout()
        formulario.addRow("Nombre:", self.nombre)
        formulario.addRow("RIF:", self.rif)
        formulario.addRow("Telefono:", self.telefono)
        formulario.addRow("Contacto:", self.contacto)

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(formulario)
        disposicion.addWidget(botones)

    def guardar(self) -> None:
        try:
            compras.guardar_proveedor(
                self.conexion,
                Proveedor(
                    id=None if self.proveedor is None else self.proveedor.id,
                    nombre=self.nombre.text().strip(),
                    rif=self.rif.text().strip() or None,
                    telefono=self.telefono.text().strip() or None,
                    contacto=self.contacto.text().strip() or None,
                    activo=True if self.proveedor is None else self.proveedor.activo,
                ),
            )
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        self.accept()
