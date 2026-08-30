"""Pantalla de productos y formulario de alta/edicion (RF-01 a RF-07)."""

import sqlite3

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
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from minimarket.datos.repositorios import alicuota as repo_alicuota
from minimarket.datos.repositorios import categoria as repo_categoria
from minimarket.datos.repositorios import producto as repo_producto
from minimarket.dominio.producto import Producto, precio_publico_bs
from minimarket.servicios import catalogo, tasa as servicio_tasa
from minimarket.ui.comunes import ErrorDeCampo, a_decimal, avisar, confirmar, formato

COLUMNAS = ["Codigo", "Nombre", "Categoria", "IVA", "Precio USD", "Precio Bs", "Estado"]


class PantallaProductos(QWidget):
    """Tabla con busqueda por codigo de barras o nombre (RF-04)."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self.productos: list[Producto] = []

        self.busqueda = QLineEdit()
        self.busqueda.setPlaceholderText("Buscar por codigo de barras o nombre…")
        self.busqueda.setClearButtonEnabled(True)
        self.busqueda.textChanged.connect(self.refrescar)

        self.incluir_inactivos = QCheckBox("Incluir productos dados de baja")
        self.incluir_inactivos.stateChanged.connect(self.refrescar)

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla.itemActivated.connect(lambda _: self.editar())

        boton_nuevo = QPushButton("&Nuevo (Ins)")
        boton_nuevo.clicked.connect(self.nuevo)
        boton_editar = QPushButton("&Editar (F4)")
        boton_editar.clicked.connect(self.editar)
        boton_baja = QPushButton("Dar de &baja / reactivar (Supr)")
        boton_baja.clicked.connect(self.cambiar_estado)

        botones = QHBoxLayout()
        for boton in (boton_nuevo, boton_editar, boton_baja):
            botones.addWidget(boton)
        botones.addStretch()

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(self.busqueda)
        disposicion.addWidget(self.incluir_inactivos)
        disposicion.addWidget(self.tabla)
        disposicion.addLayout(botones)

        # RNF-08: todo alcanzable sin mouse.
        QShortcut(QKeySequence(Qt.Key_Insert), self, self.nuevo)
        QShortcut(QKeySequence(Qt.Key_F4), self, self.editar)
        QShortcut(QKeySequence(Qt.Key_Delete), self, self.cambiar_estado)

        self.refrescar()

    def refrescar(self) -> None:
        solo_activos = not self.incluir_inactivos.isChecked()
        self.productos = catalogo.buscar(
            self.conexion, self.busqueda.text(), solo_activos=solo_activos
        )
        categorias = {c.id: c.nombre for c in repo_categoria.listar(self.conexion, False)}
        alicuotas = {a.id: a for a in repo_alicuota.listar(self.conexion)}
        tasa = servicio_tasa.tasa_del_dia(self.conexion)
        multiplo = servicio_tasa.multiplo_redondeo(self.conexion)

        self.tabla.setRowCount(len(self.productos))
        for fila, producto in enumerate(self.productos):
            alicuota = alicuotas.get(producto.alicuota_iva_id)
            bs = (
                formato(precio_publico_bs(producto.precio_venta_usd, tasa, multiplo))
                if tasa is not None
                else "sin tasa"
            )
            celdas = [
                producto.codigo_barras or "",
                producto.nombre,
                categorias.get(producto.categoria_id, ""),
                alicuota.nombre if alicuota else "",
                formato(producto.precio_venta_usd, 4),
                bs,
                "Activo" if producto.activo else "De baja",
            ]
            for columna, texto in enumerate(celdas):
                self.tabla.setItem(fila, columna, QTableWidgetItem(texto))

    def seleccionado(self) -> Producto | None:
        fila = self.tabla.currentRow()
        return self.productos[fila] if 0 <= fila < len(self.productos) else None

    def nuevo(self) -> None:
        self._abrir_formulario(None)

    def editar(self) -> None:
        producto = self.seleccionado()
        if producto is None:
            avisar(self, "Elegi un producto de la lista.")
            return
        self._abrir_formulario(producto)

    def cambiar_estado(self) -> None:
        """RF-02. Nunca se borra: se desactiva o se vuelve a activar."""
        producto = self.seleccionado()
        if producto is None:
            avisar(self, "Elegi un producto de la lista.")
            return
        if producto.activo:
            aviso = f"¿Dar de baja «{producto.nombre}»?"
            if repo_producto.tiene_movimientos(self.conexion, producto.id):
                aviso += (
                    "\n\nTiene movimientos de inventario registrados: se conserva "
                    "el historico y solo deja de aparecer en las ventas."
                )
            if not confirmar(self, aviso):
                return
            catalogo.desactivar_producto(self.conexion, producto.id)
        else:
            catalogo.reactivar_producto(self.conexion, producto.id)
        self.refrescar()

    def _abrir_formulario(self, producto: Producto | None) -> None:
        dialogo = DialogoProducto(self.conexion, producto, self)
        if dialogo.exec() == QDialog.Accepted:
            self.refrescar()


class DialogoProducto(QDialog):
    """Alta y edicion. El precio cargado INCLUYE IVA (RF-01, RF-07)."""

    def __init__(
        self,
        conexion: sqlite3.Connection,
        producto: Producto | None,
        padre: QWidget | None = None,
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.producto = producto
        self.setWindowTitle("Nuevo producto" if producto is None else "Editar producto")

        self.nombre = QLineEdit()
        self.codigo = QLineEdit()
        self.codigo.setPlaceholderText("Opcional")  # RF-03
        self.categoria = QComboBox()
        for categoria in repo_categoria.listar(conexion):
            self.categoria.addItem(categoria.nombre, categoria.id)
        self.alicuota = QComboBox()
        for alicuota in repo_alicuota.listar(conexion):
            self.alicuota.addItem(
                f"{alicuota.nombre} ({formato(alicuota.porcentaje)} %)", alicuota.id
            )
        self.margen = QLineEdit()
        self.margen.setPlaceholderText("Vacio: usa el margen de la categoria")
        self.precio = QLineEdit()
        self.existencia_minima = QLineEdit("0")
        self.maneja_vencimiento = QCheckBox("Controla fecha de vencimiento")
        self.dias_alerta = QSpinBox()
        self.dias_alerta.setRange(0, 365)
        self.dias_alerta.setValue(15)

        self.informacion = QLabel()
        self.informacion.setWordWrap(True)

        boton_calcular = QPushButton("Calcular precio desde el &margen (F9)")
        boton_calcular.clicked.connect(self.calcular_precio)
        QShortcut(QKeySequence(Qt.Key_F9), self, self.calcular_precio)

        botones = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        botones.button(QDialogButtonBox.Save).setText("Guardar")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.guardar)
        botones.rejected.connect(self.reject)

        formulario = QFormLayout()
        formulario.addRow("Nombre:", self.nombre)
        formulario.addRow("Codigo de barras:", self.codigo)
        formulario.addRow("Categoria:", self.categoria)
        formulario.addRow("Alicuota de IVA:", self.alicuota)
        formulario.addRow("Margen objetivo (%):", self.margen)
        formulario.addRow("Precio de venta USD (con IVA):", self.precio)
        formulario.addRow("Existencia minima:", self.existencia_minima)
        formulario.addRow("", self.maneja_vencimiento)
        formulario.addRow("Dias de aviso de vencimiento:", self.dias_alerta)

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(formulario)
        disposicion.addWidget(boton_calcular)
        disposicion.addWidget(self.informacion)
        disposicion.addWidget(botones)

        if producto is not None:
            self._cargar(producto)
        self.precio.textChanged.connect(self.actualizar_informacion)
        self.alicuota.currentIndexChanged.connect(self.actualizar_informacion)
        self.actualizar_informacion()

    def _cargar(self, producto: Producto) -> None:
        self.nombre.setText(producto.nombre)
        self.codigo.setText(producto.codigo_barras or "")
        self.categoria.setCurrentIndex(self.categoria.findData(producto.categoria_id))
        self.alicuota.setCurrentIndex(self.alicuota.findData(producto.alicuota_iva_id))
        # str() y no formato(): el separador de miles no se puede volver a leer.
        if producto.margen_objetivo is not None:
            self.margen.setText(str(producto.margen_objetivo))
        self.precio.setText(str(producto.precio_venta_usd))
        self.existencia_minima.setText(str(producto.existencia_minima))
        self.maneja_vencimiento.setChecked(producto.maneja_vencimiento)
        self.dias_alerta.setValue(producto.dias_alerta_venc)

    def _leer(self) -> Producto:
        precio = a_decimal(self.precio.text() or "0", "el precio de venta")
        return Producto(
            id=None if self.producto is None else self.producto.id,
            nombre=self.nombre.text().strip(),
            codigo_barras=self.codigo.text().strip() or None,
            categoria_id=self.categoria.currentData(),
            alicuota_iva_id=self.alicuota.currentData(),
            precio_venta_usd=precio,
            margen_objetivo=a_decimal(
                self.margen.text(), "el margen objetivo", opcional=True
            ),
            existencia_minima=a_decimal(
                self.existencia_minima.text() or "0", "la existencia minima"
            ),
            maneja_vencimiento=self.maneja_vencimiento.isChecked(),
            dias_alerta_venc=self.dias_alerta.value(),
            activo=True if self.producto is None else self.producto.activo,
        )

    def calcular_precio(self) -> None:
        """RF-07. Precio con IVA a partir del margen objetivo aplicable."""
        try:
            producto = self._leer()
        except ErrorDeCampo as error:
            avisar(self, str(error))
            return
        sugerido = catalogo.calcular_precio(self.conexion, producto)
        if sugerido is None:
            avisar(
                self,
                "Todavia no hay un costo de compra registrado para este producto, "
                "asi que no se puede calcular el precio. Cargalo a mano.",
            )
            return
        self.precio.setText(str(sugerido))

    def actualizar_informacion(self) -> None:
        """Costo vigente, margen que deja el precio cargado y su valor en Bs."""
        try:
            producto = self._leer()
        except ErrorDeCampo:
            self.informacion.setText("")
            return
        partes = []
        costo = (
            repo_producto.ultimo_costo(self.conexion, producto.id)
            if producto.id
            else None
        )
        partes.append(f"Ultimo costo: {formato(costo, 4)} USD")
        margen = catalogo.calcular_margen(self.conexion, producto)
        partes.append(
            f"Margen resultante: {formato(margen)} %"
            if margen is not None
            else "Margen resultante: no determinable sin costo"
        )
        tasa = servicio_tasa.tasa_del_dia(self.conexion)
        if tasa is not None:
            bs = precio_publico_bs(
                producto.precio_venta_usd,
                tasa,
                servicio_tasa.multiplo_redondeo(self.conexion),
            )
            partes.append(f"Precio al publico: {formato(bs)} Bs")
        else:
            partes.append("Sin tasa del dia cargada")
        self.informacion.setText("   ·   ".join(partes))

    def guardar(self) -> None:
        try:
            producto = self._leer()
            if producto.id is None:
                catalogo.crear_producto(self.conexion, producto)
            else:
                catalogo.modificar_producto(self.conexion, producto)
        except (ErrorDeCampo, catalogo.ErrorCatalogo) as error:
            avisar(self, str(error))
            return
        self.accept()
