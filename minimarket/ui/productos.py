"""Pantalla de productos y formulario de alta/edicion (RF-01 a RF-07)."""

import sqlite3
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
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

from minimarket.dominio.producto import Producto, precio_publico_bs
from minimarket.servicios import ErrorServicio
from minimarket.servicios import catalogo, tasa as servicio_tasa
from minimarket.servicios import reportes as servicio_reportes
from minimarket.ui.estilo import ROJO, VERDE_OSCURO
from minimarket.ui.comunes import ErrorDeCampo, a_decimal, avisar, confirmar, formato

COLUMNAS = ["Codigo", "Nombre", "Categoria", "IVA", "Precio USD", "Precio Bs", "Margen %", "Estado"]
COLUMNA_MARGEN = 6


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
        boton_recalcular = QPushButton("&Recalcular todos los precios")
        boton_recalcular.setToolTip(
            "Vuelve a calcular el precio de todo el catalogo con el ultimo costo "
            "de compra y el margen objetivo de cada producto o categoria."
        )
        boton_recalcular.clicked.connect(self.recalcular_todo)
        boton_margen = QPushButton("¿A que &margen vender?…")
        boton_margen.setToolTip(
            "El margen minimo para que las ventas paguen los gastos y dejen "
            "ganancia, y aplicarlo a todo lo que este por debajo."
        )
        boton_margen.clicked.connect(self.margen_sugerido)

        botones = QHBoxLayout()
        for boton in (boton_nuevo, boton_editar, boton_baja):
            botones.addWidget(boton)
        botones.addStretch()
        botones.addWidget(boton_recalcular)
        botones.addWidget(boton_margen)

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
        categorias = {
            c.id: c.nombre
            for c in catalogo.listar_categorias(self.conexion, solo_activas=False)
        }
        alicuotas = {a.id: a for a in catalogo.listar_alicuotas(self.conexion)}
        tasa = servicio_tasa.tasa_del_dia(self.conexion)
        multiplo = servicio_tasa.multiplo_redondeo(self.conexion)
        margenes, piso = self._margenes()

        self.tabla.setRowCount(len(self.productos))
        for fila, producto in enumerate(self.productos):
            alicuota = alicuotas.get(producto.alicuota_iva_id)
            bs = (
                formato(precio_publico_bs(producto.precio_venta_usd, tasa, multiplo))
                if tasa is not None
                else "sin tasa"
            )
            margen = margenes.get(producto.id) if margenes is not None else None
            celdas = [
                producto.codigo_barras or "",
                producto.nombre,
                categorias.get(producto.categoria_id, ""),
                alicuota.nombre if alicuota else "",
                formato(producto.precio_venta_usd, 4),
                bs,
                formato(margen) if margen is not None else ("sin costo" if margenes is not None else ""),
                "Activo" if producto.activo else "De baja",
            ]
            for columna, texto in enumerate(celdas):
                celda = QTableWidgetItem(texto)
                # Rojo si el precio de hoy no llega al margen que cubre los gastos.
                if columna == COLUMNA_MARGEN and margen is not None and piso is not None:
                    celda.setForeground(QBrush(QColor(ROJO if margen < piso else VERDE_OSCURO)))
                self.tabla.setItem(fila, columna, celda)

    def _margenes(self) -> tuple[dict | None, Decimal | None]:
        """El margen actual de cada producto y el piso sugerido; None sin permiso."""
        try:
            margenes = catalogo.margenes_actuales(self.conexion)
        except ErrorServicio:
            return None, None
        try:
            sugerido = servicio_reportes.margen_sugerido(self.conexion)
        except ErrorServicio:
            sugerido = None
        return margenes, sugerido.piso_pct if sugerido is not None else None

    def recalcular_todo(self) -> None:
        """RF-08 sobre todo el catalogo: vista previa, confirmacion, aplicar."""
        try:
            cambios = catalogo.previsualizar_recalculo_total(self.conexion)
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        if not cambios:
            avisar(
                self,
                "Todos los precios ya estan al dia con su margen objetivo y su "
                "ultimo costo. Los productos sin costo de compra quedan fuera.",
            )
            return
        if _confirmar_cambios(self, cambios, "con el margen objetivo de cada uno"):
            catalogo.aplicar_recalculo(self.conexion, cambios)
            self.refrescar()

    def margen_sugerido(self) -> None:
        if DialogoMargenSugerido(self.conexion, self).exec() == QDialog.Accepted:
            self.refrescar()

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
            if catalogo.tiene_movimientos(self.conexion, producto.id):
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


def _confirmar_cambios(padre, cambios, motivo: str) -> bool:
    muestra = "\n".join(
        f"· {producto.nombre}: {formato(producto.precio_venta_usd, 4)} → "
        f"{formato(nuevo, 4)} USD"
        for producto, nuevo in cambios[:15]
    )
    if len(cambios) > 15:
        muestra += f"\n… y {len(cambios) - 15} producto(s) mas."
    return confirmar(
        padre,
        f"Se van a actualizar {len(cambios)} precio(s) {motivo}:\n\n{muestra}\n\n"
        "¿Continuar?",
    )


class DialogoMargenSugerido(QDialog):
    """¿A que margen vender? (1.2.0)

    Muestra el piso (no perder) y el sugerido (con la ganancia deseada), el
    volumen con que se calcularon y por que baja al vender mas. El margen es
    editable antes de aplicar; lo que esta por encima no se toca.
    """

    def __init__(
        self, conexion: sqlite3.Connection, padre: QWidget | None = None
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.plan = None
        self.setWindowTitle("¿A que margen vender?")
        self.setMinimumWidth(640)

        self.explicacion = QLabel()
        self.explicacion.setWordWrap(True)
        self.margen = QLineEdit()
        self.margen.setMaximumWidth(120)
        self.margen.editingFinished.connect(self.previsualizar)
        self.detalle = QLabel()
        self.detalle.setWordWrap(True)
        self.detalle.setObjectName("subtituloIngreso")

        botones = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        self.boton_aplicar = botones.button(QDialogButtonBox.Save)
        self.boton_aplicar.setText("Aplicar a lo que este por debajo")
        botones.button(QDialogButtonBox.Cancel).setText("Cerrar")
        botones.accepted.connect(self.aplicar)
        botones.rejected.connect(self.reject)

        fila = QHBoxLayout()
        fila.addWidget(QLabel("Margen a aplicar como piso (%):"))
        fila.addWidget(self.margen)
        fila.addStretch()

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(self.explicacion)
        disposicion.addLayout(fila)
        disposicion.addWidget(self.detalle)
        disposicion.addWidget(botones)
        self._calcular()

    def _calcular(self) -> None:
        try:
            sugerido = servicio_reportes.margen_sugerido(self.conexion)
        except ErrorServicio as error:
            self.explicacion.setText(str(error))
            self.boton_aplicar.setEnabled(False)
            return
        self.explicacion.setText(texto_margen_sugerido(sugerido))
        if sugerido is None or sugerido.sugerido_pct is None:
            self.boton_aplicar.setEnabled(False)
            return
        self.margen.setText(str(sugerido.sugerido_pct))
        self.previsualizar()

    def previsualizar(self) -> None:
        try:
            margen = a_decimal(self.margen.text(), "el margen")
            self.plan = catalogo.previsualizar_margen(self.conexion, margen)
        except (ErrorDeCampo, ErrorServicio) as error:
            self.detalle.setText(str(error))
            self.boton_aplicar.setEnabled(False)
            return
        plan = self.plan
        partes = []
        if plan.categorias:
            partes.append(
                "Categorias que suben a ese margen: "
                + ", ".join(f"{c.nombre} ({formato(m)} %)" for c, m in plan.categorias)
                + "."
            )
        if plan.productos:
            partes.append(f"Productos con margen propio que suben: {len(plan.productos)}.")
        if not plan.categorias and not plan.productos:
            partes.append("Ninguna categoria ni producto esta por debajo de ese margen.")
        partes.append(f"Precios que cambiarian: {len(plan.cambios)}.")
        if plan.sin_costo:
            partes.append(
                f"{plan.sin_costo} producto(s) sin compra registrada quedan fuera: "
                "sin costo no hay precio que calcular."
            )
        self.detalle.setText(" ".join(partes))
        self.boton_aplicar.setEnabled(bool(plan.categorias or plan.productos or plan.cambios))

    def aplicar(self) -> None:
        if self.plan is None:
            return
        if self.plan.cambios and not _confirmar_cambios(
            self, self.plan.cambios, f"con un margen minimo de {formato(self.plan.margen_pct)} %"
        ):
            return
        try:
            cuantos = catalogo.aplicar_margen(self.conexion, self.plan)
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        avisar(
            self,
            f"Listo: {len(self.plan.categorias)} categoria(s) y {len(self.plan.productos)} "
            f"producto(s) subieron su margen a {formato(self.plan.margen_pct)} %, y se "
            f"actualizaron {cuantos} precios.",
            "Margen aplicado",
        )
        self.accept()


def texto_margen_sugerido(sugerido) -> str:
    """La explicacion en palabras del dueno, para el dialogo y para Inicio."""
    if sugerido is None:
        return (
            "Todavia no se puede sugerir un margen: no hay ventas y no se "
            "cargaron las ventas esperadas por mes. Cargalas en Archivo → "
            "Configuracion, o esperá a tener unos dias de ventas."
        )
    if sugerido.origen_ventas == "esperado":
        base = f"las ventas esperadas que cargaste ({formato(sugerido.ventas_mes_usd)} USD al mes)"
    elif sugerido.origen_ventas == "proyectado":
        base = (
            f"lo vendido en {_dias(sugerido.dias_de_ventas)}, proyectado a un mes "
            f"({formato(sugerido.ventas_mes_usd)} USD)"
        )
    else:
        base = f"lo vendido en los ultimos 30 dias ({formato(sugerido.ventas_mes_usd)} USD)"
    gastos = (
        f"Gastos fijos del mes: {formato(sugerido.gastos_fijos_usd)} USD"
        + (
            f", mas {formato(sugerido.tasa_variable * 100)} % de comisiones sobre lo cobrado."
            if sugerido.tasa_variable > 0
            else "."
        )
    )
    if sugerido.piso_pct is None:
        return (
            f"Calculado con {base}. {gastos}\n\n"
            "Con ese volumen ningun margen alcanza: los gastos superan lo que se "
            "vende. Hay que vender mas o bajar gastos; subir precios no lo arregla."
        )
    doble = sugerido.sugerido_si_vendiera(sugerido.ventas_mes_usd * 2)
    return (
        f"Calculado con {base}. {gastos}\n\n"
        f"Margen minimo para no perder: {formato(sugerido.piso_pct)} % sobre el costo.\n"
        f"Sugerido, con {formato(sugerido.ganancia_pct)} % de ganancia sobre las ventas: "
        f"{formato(sugerido.sugerido_pct)} %.\n\n"
        f"Este margen baja solo cuando se vende mas: con el doble de ventas bastaria "
        f"{formato(doble)} %. Lo que ya tenga un margen mas alto (charcuteria, por "
        "ejemplo) no se toca; eso lo decide el dueno."
    )


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
        for categoria in catalogo.listar_categorias(conexion):
            self.categoria.addItem(categoria.nombre, categoria.id)
        self.alicuota = QComboBox()
        for alicuota in catalogo.listar_alicuotas(conexion):
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
        """Costo vigente, margen que deja el precio cargado y su valor en Bs.

        Corre en cada tecla, asi que no puede levantar nada: sin permiso para
        ver costos (RF-58) muestra solo el precio al publico.
        """
        try:
            producto = self._leer()
        except ErrorDeCampo:
            self.informacion.setText("")
            return
        partes = []
        try:
            costo = (
                catalogo.ultimo_costo(self.conexion, producto.id)
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
        except ErrorServicio:
            pass
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
        except (ErrorDeCampo, ErrorServicio) as error:
            avisar(self, str(error))
            return
        self.accept()


def _dias(n: int) -> str:
    return "1 dia" if n == 1 else f"{n} dias"
