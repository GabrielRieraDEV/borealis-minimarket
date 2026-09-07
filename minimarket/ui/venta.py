"""Punto de venta y caja (RF-34 a RF-45).

La pantalla mas usada del sistema, y la unica que se opera con un cliente
enfrente: todo se alcanza con el teclado (RNF-08) y el foco vuelve siempre al
campo del codigo de barras, porque el lector se comporta como un teclado y
termina con Enter.

Teclas: F4 cliente · F6 anular una venta · F7 abrir o cerrar caja ·
F9 reimprimir · F12 cobrar · Supr quitar linea · Esc cancelar la venta.
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
    QFrame,
    QGroupBox,
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

from minimarket.dominio.dinero import convertir_a_bs, redondear_comercial
from minimarket.dominio.producto import precio_publico_bs
from minimarket.dominio.usuario import ANULAR_VENTAS
from minimarket.dominio.venta import (
    BS,
    EFECTIVO,
    MEDIOS,
    MONEDAS,
    PAGO_MOVIL,
    TRANSFERENCIA,
    USD,
    Cliente,
    LineaVenta,
    Venta,
)
from minimarket.servicios import ErrorServicio, usuario_actual
from minimarket.servicios import caja as servicio_caja
from minimarket.servicios import catalogo
from minimarket.servicios import reportes as servicio_reportes
from minimarket.servicios import tasa as servicio_tasa
from minimarket.servicios import usuarios as servicio_usuarios
from minimarket.servicios import venta as servicio_venta
from minimarket.ui.comunes import ErrorDeCampo, a_decimal, avisar, confirmar, formato
from minimarket.ui.usuarios import pedir_autorizacion

COLUMNAS = ["Producto", "Cantidad", "Precio USD", "Precio Bs", "IVA %", "Total USD", "Total Bs"]
COLUMNAS_PAGO = ["Medio", "Moneda", "Monto", "Equivale USD", "Referencia"]
COLUMNAS_ARQUEO = ["Medio", "Moneda", "Esperado", "Contado", "Diferencia"]
NOMBRE_MEDIO_VUELTO = {EFECTIVO: "Efectivo", PAGO_MOVIL: "Pago movil", TRANSFERENCIA: "Transferencia"}


class PantallaVenta(QWidget):
    """RF-34 a RF-39. Una venta en curso; se confirma al cobrar."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self.lineas: list[LineaVenta] = []
        self.cliente: Cliente | None = None
        self.tasa: Decimal | None = None
        self.ultima_venta_id: int | None = None

        self.estado = QLabel()
        self.estado.setObjectName("estadoCaja")
        self.codigo = QLineEdit()
        self.codigo.setObjectName("codigo")  # lo agranda `ui/estilo.py`
        self.codigo.setPlaceholderText(
            "Codigo de barras o nombre  —  3*codigo para varias unidades"
        )
        self.codigo.returnPressed.connect(self.agregar)

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setFocusPolicy(Qt.NoFocus)  # el foco no se va del codigo
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        self.desglose = QLabel()
        self.cliente_visible = QLabel()
        # El panel verde con el total: bolivares grande, porque es lo que el
        # cliente paga y mira desde el otro lado del mostrador; dolares chico.
        self.total_usd = QLabel()
        self.total_usd.setObjectName("totalUsd")
        self.total_bs = QLabel()
        self.total_bs.setObjectName("totalBs")
        etiqueta = QLabel("TOTAL A PAGAR")
        etiqueta.setObjectName("etiquetaTotal")
        panel = QFrame()
        panel.setObjectName("panelTotales")
        adentro = QVBoxLayout(panel)
        adentro.setContentsMargins(20, 10, 20, 12)
        adentro.setSpacing(0)
        for parte in (etiqueta, self.total_bs, self.total_usd):
            parte.setAlignment(Qt.AlignRight)
            adentro.addWidget(parte)

        botones = QHBoxLayout()
        for texto, destino in (
            ("&Cobrar (F12)", self.cobrar),
            ("&Quitar linea (Supr)", self.quitar),
            ("C&liente (F4)", self.elegir_cliente),
            ("Ca&ncelar venta (Esc)", self.cancelar),
            ("Ca&ja (F7)", self.caja),
            ("&Anular venta (F6)", self.anular),
            ("&Reimprimir (F9)", self.reimprimir),
        ):
            boton = QPushButton(texto)
            boton.clicked.connect(destino)
            boton.setFocusPolicy(Qt.NoFocus)
            botones.addWidget(boton)
        botones.addStretch()

        # Abajo: a la izquierda el cliente y el desglose de IVA, a la derecha
        # el panel del total.
        pie = QHBoxLayout()
        textos = QVBoxLayout()
        textos.addStretch()
        textos.addWidget(self.cliente_visible)
        textos.addWidget(self.desglose)
        pie.addLayout(textos, stretch=1)
        pie.addWidget(panel)

        disposicion = QVBoxLayout(self)
        disposicion.setSpacing(8)
        disposicion.addWidget(self.estado)
        disposicion.addWidget(self.codigo)
        disposicion.addWidget(self.tabla, stretch=1)
        disposicion.addLayout(pie)
        disposicion.addLayout(botones)

        for tecla, destino in (
            (Qt.Key_F12, self.cobrar),
            (Qt.Key_Delete, self.quitar),
            (Qt.Key_F4, self.elegir_cliente),
            (Qt.Key_Escape, self.cancelar),
            (Qt.Key_F7, self.caja),
            (Qt.Key_F6, self.anular),
            (Qt.Key_F9, self.reimprimir),
        ):
            QShortcut(QKeySequence(tecla), self, destino)

        self.refrescar()

    # --- Estado -------------------------------------------------------------

    def refrescar(self) -> None:
        self.tasa = servicio_tasa.tasa_del_dia(self.conexion)
        sesion = servicio_caja.sesion_abierta(self.conexion)
        if sesion is None:
            self.estado.setText(
                "CAJA CERRADA — abrila con F7 antes de vender (RF-44)."
            )
        else:
            self.estado.setText(
                f"Caja abierta desde {sesion.fecha_apertura} · "
                f"tasa {formato(self.tasa, 2)} Bs/USD"
            )
        self._pintar()

    def _pintar(self) -> None:
        venta = self._venta_en_curso()
        self.tabla.setRowCount(len(self.lineas))
        # Pedido del cliente (1.2.2): cada linea tambien en bolivares. El
        # unitario con el redondeo al publico (RN-10), el total sin redondear,
        # que es lo que suma el total en Bs del panel.
        multiplo = servicio_tasa.multiplo_redondeo(self.conexion)
        for fila, linea in enumerate(self.lineas):
            celdas = [
                linea.descripcion,
                formato(linea.cantidad, 3),
                formato(linea.precio_unit_usd, 4),
                formato(precio_publico_bs(linea.precio_unit_usd, self.tasa, multiplo))
                if self.tasa is not None else "—",
                formato(linea.alicuota_pct),
                formato(linea.total_linea_usd),
                formato(convertir_a_bs(linea.total_linea_usd, self.tasa))
                if self.tasa is not None else "—",
            ]
            for columna, texto in enumerate(celdas):
                self.tabla.setItem(fila, columna, QTableWidgetItem(texto))
        self.tabla.scrollToBottom()

        # RN-21: exento, base imponible e IVA siempre a la vista.
        self.desglose.setText(
            f"Exento {formato(venta.exento_usd)} USD   ·   "
            f"Base imponible {formato(venta.base_imponible_usd)} USD   ·   "
            f"IVA {formato(venta.iva_usd)} USD"
        )
        self.total_usd.setText(f"{formato(venta.total_usd)} USD")
        self.total_bs.setText(
            f"Bs {formato(venta.total_bs)}"
            if self.tasa is not None
            else "Sin tasa del dia (F5)"
        )
        self.cliente_visible.setText(
            f"Cliente: {self.cliente.razon_social} ({self.cliente.rif})"
            if self.cliente
            else "Cliente: consumidor final — F4 para cargar datos fiscales"
        )
        self.codigo.setFocus()

    def _venta_en_curso(self) -> Venta:
        """Solo para calcular y mostrar; la venta real la arma `cobrar`."""
        return Venta(
            usuario_id=usuario_actual(),
            tasa=self.tasa or Decimal(1),
            cliente_id=self.cliente.id if self.cliente else None,
            lineas=self.lineas,
        )

    # --- Carga de lineas (RF-34) --------------------------------------------

    def agregar(self) -> None:
        texto = self.codigo.text().strip()
        if not texto:
            return
        cantidad, separador, resto = texto.partition("*")
        if separador:
            try:
                cantidad = a_decimal(cantidad, "la cantidad")
            except ErrorDeCampo as error:
                return self._error(str(error))
            texto = resto.strip()
        else:
            cantidad = Decimal(1)

        producto = self._buscar(texto)
        if producto is None:
            return
        try:
            linea = servicio_venta.nueva_linea(self.conexion, producto.id, cantidad)
        except ErrorServicio as error:
            return self._error(str(error))

        # Escanear dos veces el mismo producto suma cantidad, no repite renglon.
        repetida = next(
            (
                existente
                for existente in self.lineas
                if existente.producto_id == linea.producto_id
                and existente.precio_unit_usd == linea.precio_unit_usd
            ),
            None,
        )
        if repetida is None:
            self.lineas.append(linea)
        else:
            repetida.cantidad += linea.cantidad
        self.codigo.clear()
        self._pintar()

    def _buscar(self, texto: str):
        """RF-04. Codigo exacto, o eleccion entre las coincidencias por nombre."""
        encontrados = catalogo.buscar(self.conexion, texto)
        if not encontrados:
            self._error(f"No hay ningun producto que coincida con «{texto}».")
            return None
        if len(encontrados) == 1:
            return encontrados[0]
        nombres = [p.nombre for p in encontrados[:50]]
        elegido, acepto = QInputDialog.getItem(
            self, "Elegi el producto", "Coincidencias:", nombres, 0, False
        )
        self.codigo.setFocus()
        if not acepto:
            return None
        return encontrados[nombres.index(elegido)]

    def quitar(self) -> None:
        fila = self.tabla.currentRow()
        if 0 <= fila < len(self.lineas):
            self.lineas.pop(fila)
            self._pintar()

    def cancelar(self) -> None:
        if not self.lineas:
            return
        if confirmar(self, "¿Descartar la venta en curso?"):
            self.lineas = []
            self.cliente = None
            self.codigo.clear()
            self._pintar()

    def elegir_cliente(self) -> None:
        """RF-40."""
        dialogo = DialogoCliente(self.conexion, self)
        if dialogo.exec() == QDialog.Accepted:
            self.cliente = dialogo.cliente
        self._pintar()

    # --- Cobro (RF-35 a RF-39) ----------------------------------------------

    def cobrar(self) -> None:
        if not self.lineas:
            return self._error("Cargá al menos un producto antes de cobrar.")
        if self.tasa is None:
            return self._error(
                "No hay tasa de cambio cargada para hoy. Cargala con F5 antes "
                "de cobrar."
            )
        if servicio_caja.sesion_abierta(self.conexion) is None:
            return self._error("No hay una caja abierta. Abrila con F7.")

        venta = self._venta_en_curso()
        dialogo = DialogoCobro(
            venta, self, multiplo=servicio_tasa.multiplo_redondeo(self.conexion)
        )
        if dialogo.exec() != QDialog.Accepted:
            self.codigo.setFocus()
            return
        venta.pagos = dialogo.pagos
        venta.vueltos = dialogo.vueltos
        try:
            registrada = servicio_venta.registrar_venta(self.conexion, venta)
        except ErrorServicio as error:
            return self._error(str(error))

        self.ultima_venta_id = registrada.id
        self.lineas = []
        self.cliente = None
        self._imprimir(registrada.id)
        self.refrescar()

    def _imprimir(self, venta_id: int) -> None:
        """RF-39. La venta ya esta registrada: un fallo de impresion no la pierde."""
        from minimarket.infra.impresora import ErrorImpresion

        if not servicio_venta.hay_impresora(self.conexion):
            return
        try:
            servicio_venta.imprimir_nota(self.conexion, venta_id)
        except ErrorImpresion as error:
            avisar(self, f"{error}\n\nReimprimí con F9 cuando este lista.")

    def reimprimir(self) -> None:
        """RF-39. La ultima venta, o la que se indique por numero."""
        venta_id = self.ultima_venta_id
        if venta_id is None:
            numero, acepto = QInputDialog.getInt(
                self, "Reimprimir", "Numero de venta:", 1, 1
            )
            if not acepto:
                return
            venta = servicio_venta.por_numero(self.conexion, numero)
            if venta is None:
                return self._error(f"No existe la venta numero {numero}.")
            venta_id = venta.id
        self._imprimir(venta_id)
        self.codigo.setFocus()

    # --- Anulacion (RF-41) --------------------------------------------------

    def anular(self) -> None:
        """RN-25. Motivo obligatorio y autorizacion de administrador.

        Si quien opera ya es administrador, anula directo; si es cajero, se le
        pide la clave a un administrador y se pasa como `autorizado_por`. Quien
        valida que eso alcance es el servicio.
        """
        numero, acepto = QInputDialog.getInt(
            self, "Anular venta", "Numero de venta a anular:", 1, 1
        )
        if not acepto:
            return
        venta = servicio_venta.por_numero(self.conexion, numero)
        if venta is None:
            return self._error(f"No existe la venta numero {numero}.")
        motivo, acepto = QInputDialog.getText(
            self,
            "Anular venta",
            f"Venta {numero} por {formato(venta.total_usd)} USD.\nMotivo:",
        )
        if not acepto:
            return
        autorizado_por = None
        if not servicio_usuarios.tiene_permiso(self.conexion, ANULAR_VENTAS):
            autorizado_por = pedir_autorizacion(
                self.conexion, f"Anulacion de la venta {numero}.", self
            )
            if autorizado_por is None:
                return
        try:
            servicio_venta.anular_venta(
                self.conexion, venta.id, motivo, autorizado_por=autorizado_por
            )
        except ErrorServicio as error:
            return self._error(str(error))
        avisar(self, f"La venta {numero} quedo anulada.", "Anulacion registrada")
        self.refrescar()

    # --- Caja (RF-42, RF-43) ------------------------------------------------

    def caja(self) -> None:
        sesion = servicio_caja.sesion_abierta(self.conexion)
        dialogo = (
            DialogoApertura(self.conexion, self)
            if sesion is None
            else DialogoCierre(self.conexion, sesion.id, self)
        )
        dialogo.exec()
        self.refrescar()

    def _error(self, mensaje: str) -> None:
        avisar(self, mensaje)
        self.codigo.setFocus()
        self.codigo.selectAll()


class DialogoCobro(QDialog):
    """RF-36 / RF-37. Pago combinado y vuelto (RN-22, RN-23)."""

    def __init__(
        self,
        venta: Venta,
        padre: QWidget | None = None,
        multiplo: Decimal = Decimal(1),
    ) -> None:
        super().__init__(padre)
        self.venta = venta
        self.pagos = []
        self.vueltos = []
        self.multiplo = multiplo
        self.setWindowTitle("Cobrar")
        self.resize(760, 560)

        total = QLabel(
            f"TOTAL  Bs {formato(venta.total_bs)}  ·  "
            f"{formato(venta.total_usd)} USD"
        )
        total.setObjectName("totalCobro")

        self.medio = QComboBox()
        self.medio.addItems(MEDIOS)
        self.moneda = QComboBox()
        self.moneda.addItems(MONEDAS)
        self.moneda.setCurrentText(BS)
        self.moneda.currentIndexChanged.connect(self._sugerir_monto)
        self.monto = QLineEdit()
        self.monto.setMinimumWidth(130)
        self.monto.returnPressed.connect(self.agregar)
        self.referencia = QLineEdit()
        self.referencia.setPlaceholderText("Referencia (opcional)")

        self.tabla = QTableWidget(0, len(COLUMNAS_PAGO))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS_PAGO)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)

        self.saldo = QLabel()
        self.saldo.setObjectName("saldoCobro")

        # RN-23 (1.3.0): en que sale el vuelto. Se declaran solo las partes que
        # NO son efectivo en bolivares («10 USD en efectivo», «el resto por
        # pago movil»); lo que quede sin declarar sale de la gaveta en Bs.
        self.vuelto_medio = QComboBox()
        for etiqueta, medio in (
            ("Efectivo", EFECTIVO),
            ("Pago movil", PAGO_MOVIL),
            ("Transferencia", TRANSFERENCIA),
        ):
            self.vuelto_medio.addItem(etiqueta, medio)
        self.vuelto_moneda = QComboBox()
        self.vuelto_moneda.addItems(MONEDAS)
        self.vuelto_moneda.setCurrentText(USD)
        self.vuelto_moneda.currentIndexChanged.connect(self._sugerir_vuelto)
        self.vuelto_monto = QLineEdit()
        self.vuelto_monto.setMinimumWidth(130)
        self.vuelto_monto.returnPressed.connect(self.agregar_vuelto)
        agregar_vuelto = QPushButton("Agregar parte del &vuelto")
        agregar_vuelto.clicked.connect(self.agregar_vuelto)
        quitar_vuelto = QPushButton("Quitar")
        quitar_vuelto.clicked.connect(self.quitar_vuelto)
        self.tabla_vuelto = QTableWidget(0, 4)
        self.tabla_vuelto.setHorizontalHeaderLabels(["Medio", "Moneda", "Monto", "Equivale USD"])
        self.tabla_vuelto.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_vuelto.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_vuelto.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla_vuelto.setMaximumHeight(110)
        fila_vuelto = QHBoxLayout()
        fila_vuelto.addWidget(QLabel("Entregar vuelto en:"))
        fila_vuelto.addWidget(self.vuelto_medio)
        fila_vuelto.addWidget(self.vuelto_moneda)
        fila_vuelto.addWidget(self.vuelto_monto)
        fila_vuelto.addWidget(agregar_vuelto)
        fila_vuelto.addWidget(quitar_vuelto)
        fila_vuelto.addStretch()
        self.grupo_vuelto = QGroupBox("Vuelto")
        adentro = QVBoxLayout(self.grupo_vuelto)
        adentro.addLayout(fila_vuelto)
        adentro.addWidget(self.tabla_vuelto)
        self.grupo_vuelto.setVisible(False)

        agregar = QPushButton("&Agregar pago (Enter)")
        agregar.clicked.connect(self.agregar)
        quitar = QPushButton("&Quitar (Supr)")
        quitar.clicked.connect(self.quitar)
        QShortcut(QKeySequence(Qt.Key_Delete), self.tabla, self.quitar)

        fila = QHBoxLayout()
        fila.addWidget(self.medio)
        fila.addWidget(self.moneda)
        fila.addWidget(self.monto)
        fila.addWidget(self.referencia, stretch=1)
        fila.addWidget(agregar)
        fila.addWidget(quitar)

        botones = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        confirmar_boton = botones.button(QDialogButtonBox.Save)
        confirmar_boton.setText("Confirmar cobro (F12)")
        # Verde de accion principal sin ser `default`. El nombre llega despues
        # de que QDialogButtonBox pulio el boton, asi que se repule.
        confirmar_boton.setObjectName("botonPrincipal")
        confirmar_boton.style().unpolish(confirmar_boton)
        confirmar_boton.style().polish(confirmar_boton)
        # Enter en el monto agrega el pago; confirmar es F12 y solo F12.
        confirmar_boton.setDefault(False)
        confirmar_boton.setAutoDefault(False)
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.confirmar)
        botones.rejected.connect(self.reject)
        QShortcut(QKeySequence(Qt.Key_F12), self, self.confirmar)

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(total)
        disposicion.addLayout(fila)
        disposicion.addWidget(self.tabla)
        disposicion.addWidget(self.saldo)
        disposicion.addWidget(self.grupo_vuelto)
        disposicion.addWidget(botones)

        self._pintar()
        self.monto.setFocus()

    # --- Vuelto (RN-23) -----------------------------------------------------

    def _sugerir_vuelto(self) -> None:
        """Lo que falta repartir, en la moneda elegida."""
        resto = self.venta.vuelto_por_declarar_usd
        if self.vuelto_moneda.currentText() == BS:
            resto = self.venta.tasa * resto
        self.vuelto_monto.setText(f"{max(resto, Decimal(0)):.2f}")

    def agregar_vuelto(self) -> None:
        try:
            monto = a_decimal(self.vuelto_monto.text(), "el monto del vuelto")
        except ErrorDeCampo as error:
            avisar(self, str(error))
            return
        if monto <= 0:
            avisar(self, "El monto del vuelto tiene que ser mayor que cero.")
            return
        parte = self.venta.vuelto_declarado(
            self.vuelto_medio.currentData(), self.vuelto_moneda.currentText(), monto
        )
        if self.venta.vuelto_declarado_usd + parte.monto_usd > self.venta.vuelto_usd:
            avisar(
                self,
                f"Eso supera el vuelto: quedan {formato(self.venta.vuelto_por_declarar_usd)} "
                "USD por repartir.",
            )
            return
        self.vueltos.append(parte)
        self.venta.vueltos = self.vueltos
        self._pintar()

    def quitar_vuelto(self) -> None:
        fila = self.tabla_vuelto.currentRow()
        if 0 <= fila < len(self.vueltos):
            self.vueltos.pop(fila)
            self.venta.vueltos = self.vueltos
            self._pintar()

    def _sugerir_monto(self) -> None:
        """Lo que falta, en la moneda elegida: el caso comun es pagar justo."""
        falta = self.venta.falta_usd
        if self.moneda.currentText() == BS:
            falta = self.venta.tasa * falta
        self.monto.setText(f"{falta:.2f}")
        self.monto.selectAll()

    def agregar(self) -> None:
        try:
            cobro = servicio_venta.pago(
                self.medio.currentText(),
                self.moneda.currentText(),
                a_decimal(self.monto.text(), "el monto del pago"),
                self.venta.tasa,
                self.referencia.text().strip() or None,
            )
        except (ErrorDeCampo, ErrorServicio) as error:
            avisar(self, str(error))
            return
        self.pagos.append(cobro)
        self.venta.pagos = self.pagos
        self.referencia.clear()
        self._pintar()
        self.monto.setFocus()

    def quitar(self) -> None:
        fila = self.tabla.currentRow()
        if 0 <= fila < len(self.pagos):
            self.pagos.pop(fila)
            self.venta.pagos = self.pagos
            self._pintar()

    def _pintar(self) -> None:
        self.tabla.setRowCount(len(self.pagos))
        for fila, cobro in enumerate(self.pagos):
            celdas = [
                cobro.medio,
                cobro.moneda,
                formato(cobro.monto),
                formato(cobro.monto_usd),
                cobro.referencia or "",
            ]
            for columna, texto in enumerate(celdas):
                self.tabla.setItem(fila, columna, QTableWidgetItem(texto))

        hay_vuelto = self.venta.falta_usd == 0 and self.venta.vuelto_usd > 0
        if not hay_vuelto:
            self.vueltos.clear()
            self.venta.vueltos = self.vueltos
        self.grupo_vuelto.setVisible(hay_vuelto)
        self.tabla_vuelto.setRowCount(len(self.vueltos))
        for fila, parte in enumerate(self.vueltos):
            for columna, texto in enumerate([
                NOMBRE_MEDIO_VUELTO[parte.medio],
                parte.moneda,
                formato(parte.monto),
                formato(parte.monto_usd),
            ]):
                self.tabla_vuelto.setItem(fila, columna, QTableWidgetItem(texto))

        if self.venta.falta_usd > 0:
            self.saldo.setText(f"FALTA  {formato(self.venta.falta_usd)} USD")
        elif self.venta.vuelto_usd > 0:
            resto = self.venta.vuelto_por_declarar_usd
            resto_bs = redondear_comercial(convertir_a_bs(resto, self.venta.tasa), self.multiplo)
            self.saldo.setText(
                f"VUELTO  {formato(self.venta.vuelto_usd)} USD"
                + (
                    f"  ·  el resto, {formato(resto_bs)} Bs en efectivo"
                    if resto > 0 and self.vueltos
                    else f"  ·  {formato(resto_bs)} Bs en efectivo"
                    if resto > 0
                    else "  ·  repartido"
                )
            )
            self._sugerir_vuelto()
        else:
            self.saldo.setText("Pago exacto")
        self._sugerir_monto()

    def confirmar(self) -> None:
        if self.venta.falta_usd > 0:
            avisar(self, f"Faltan {formato(self.venta.falta_usd)} USD por cobrar.")
            return
        if not self.venta.vuelto_admisible:
            # RN-23: el excedente electronico no se devuelve.
            avisar(
                self,
                "El excedente no se puede devolver: solo el efectivo genera "
                "vuelto. Corregí el monto cobrado por punto, pago movil o "
                "transferencia.",
            )
            return
        self.accept()


class DialogoCliente(QDialog):
    """RF-40. Datos fiscales del cliente cuando la venta los requiere."""

    def __init__(self, conexion: sqlite3.Connection, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.cliente: Cliente | None = None
        self.setWindowTitle("Datos fiscales del cliente")

        self.rif = QLineEdit()
        self.rif.setPlaceholderText("J-12345678-9")
        self.rif.editingFinished.connect(self._buscar)
        self.razon_social = QLineEdit()
        self.direccion = QLineEdit()
        self.telefono = QLineEdit()

        botones = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        botones.button(QDialogButtonBox.Save).setText("Usar este cliente")
        botones.button(QDialogButtonBox.Cancel).setText("Consumidor final")
        botones.accepted.connect(self.guardar)
        botones.rejected.connect(self.reject)

        formulario = QFormLayout()
        formulario.addRow("RIF:", self.rif)
        formulario.addRow("Razon social:", self.razon_social)
        formulario.addRow("Direccion fiscal:", self.direccion)
        formulario.addRow("Telefono:", self.telefono)

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(formulario)
        disposicion.addWidget(botones)

    def _buscar(self) -> None:
        """Un RIF ya cargado completa el resto solo."""
        if not self.rif.text().strip() or self.razon_social.text().strip():
            return
        existente = servicio_venta.cliente_por_rif(self.conexion, self.rif.text())
        if existente is None:
            return
        self.razon_social.setText(existente.razon_social or "")
        self.direccion.setText(existente.direccion_fiscal or "")
        self.telefono.setText(existente.telefono or "")

    def guardar(self) -> None:
        try:
            self.cliente = servicio_venta.guardar_cliente(
                self.conexion,
                Cliente(
                    razon_social=self.razon_social.text().strip(),
                    rif=self.rif.text().strip(),
                    direccion_fiscal=self.direccion.text().strip() or None,
                    telefono=self.telefono.text().strip() or None,
                    tipo="EMPRESA",
                ),
            )
        except ErrorServicio as error:
            avisar(self, str(error))
            return
        self.accept()


class DialogoApertura(QDialog):
    """RF-42. Monto inicial en cada moneda."""

    def __init__(self, conexion: sqlite3.Connection, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.setWindowTitle("Abrir caja")

        self.inicial_bs = QLineEdit("0")
        self.inicial_usd = QLineEdit("0")

        botones = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        botones.button(QDialogButtonBox.Save).setText("Abrir caja")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.guardar)
        botones.rejected.connect(self.reject)

        formulario = QFormLayout()
        formulario.addRow("Efectivo inicial en Bs:", self.inicial_bs)
        formulario.addRow("Efectivo inicial en USD:", self.inicial_usd)

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(formulario)
        disposicion.addWidget(botones)

    def guardar(self) -> None:
        try:
            servicio_caja.abrir(
                self.conexion,
                a_decimal(self.inicial_bs.text(), "el efectivo inicial en Bs"),
                a_decimal(self.inicial_usd.text(), "el efectivo inicial en USD"),
            )
        except (ErrorDeCampo, ErrorServicio) as error:
            avisar(self, str(error))
            return
        self.accept()


class DialogoCierre(QDialog):
    """RF-43 / RN-26. Esperado por medio contra el conteo fisico."""

    def __init__(
        self, conexion: sqlite3.Connection, sesion_id: int, padre: QWidget | None = None
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.sesion_id = sesion_id
        self.setWindowTitle("Cerrar caja")
        self.resize(760, 480)

        self.tabla = QTableWidget(0, len(COLUMNAS_ARQUEO))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS_ARQUEO)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        # Pedido del cliente (1.2.0): al cerrar, ver que se vendio y por donde
        # entro la plata, no solo el arqueo.
        self.vendido = QTableWidget(0, 3)
        self.vendido.setHorizontalHeaderLabels(["Producto", "Cantidad", "Total USD"])
        self.vendido.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.vendido.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.cobrado = QLabel()
        self.cobrado.setWordWrap(True)
        self._pintar_vendido()

        self.conteo_bs = QLineEdit("0")
        self.conteo_bs.textChanged.connect(self._pintar)
        self.conteo_usd = QLineEdit("0")
        self.conteo_usd.textChanged.connect(self._pintar)
        self.resumen = QLabel()

        botones = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        botones.button(QDialogButtonBox.Save).setText("Cerrar caja")
        botones.button(QDialogButtonBox.Cancel).setText("Seguir vendiendo")
        botones.accepted.connect(self.guardar)
        botones.rejected.connect(self.reject)

        formulario = QFormLayout()
        formulario.addRow("Efectivo contado en Bs:", self.conteo_bs)
        formulario.addRow("Efectivo contado en USD:", self.conteo_usd)

        arqueo = QWidget()
        adentro = QVBoxLayout(arqueo)
        adentro.addWidget(self.tabla)
        adentro.addLayout(formulario)
        vendido = QWidget()
        adentro = QVBoxLayout(vendido)
        adentro.addWidget(self.vendido)
        adentro.addWidget(self.cobrado)
        pestanas = QTabWidget()
        pestanas.addTab(arqueo, "Arqueo")
        pestanas.addTab(vendido, "Que se vendio")

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(self.resumen)
        disposicion.addWidget(pestanas)
        disposicion.addWidget(botones)

        self._pintar()

    def _pintar_vendido(self) -> None:
        from minimarket.ui.reportes import reporte_venta_del_dia

        try:
            dia = servicio_reportes.resumen_de_sesion(self.conexion, self.sesion_id)
        except ErrorServicio as error:
            self.cobrado.setText(str(error))
            return
        reporte = reporte_venta_del_dia(dia)
        self.vendido.setRowCount(len(reporte.filas))
        for numero, fila in enumerate(reporte.filas):
            for columna, texto in enumerate(fila):
                self.vendido.setItem(numero, columna, QTableWidgetItem(texto))
        self.cobrado.setText("\n".join(reporte.pie))

    def _conteos(self) -> tuple[Decimal, Decimal]:
        return (
            a_decimal(self.conteo_bs.text(), "el efectivo contado en Bs", True)
            or Decimal(0),
            a_decimal(self.conteo_usd.text(), "el efectivo contado en USD", True)
            or Decimal(0),
        )

    def _pintar(self) -> None:
        try:
            conteo_bs, conteo_usd = self._conteos()
        except ErrorDeCampo:
            return  # el usuario esta tecleando; se avisa al confirmar
        arqueo = servicio_caja.arqueo(
            self.conexion, self.sesion_id, conteo_bs, conteo_usd
        )
        self.resumen.setText(
            f"{arqueo.ventas} ventas por {formato(arqueo.total_vendido_usd)} USD "
            f"en esta sesion."
        )
        self.tabla.setRowCount(len(arqueo.lineas))
        for fila, linea in enumerate(arqueo.lineas):
            celdas = [
                linea.medio,
                linea.moneda,
                formato(linea.esperado),
                formato(linea.conteo),
                formato(linea.diferencia),
            ]
            for columna, texto in enumerate(celdas):
                self.tabla.setItem(fila, columna, QTableWidgetItem(texto))

    def guardar(self) -> None:
        try:
            conteo_bs, conteo_usd = self._conteos()
            cierre = servicio_caja.cerrar(self.conexion, conteo_bs, conteo_usd)
        except (ErrorDeCampo, ErrorServicio) as error:
            avisar(self, str(error))
            return
        # RN-26: la diferencia no impide cerrar, pero se informa.
        avisar(
            self,
            f"Caja cerrada.\n\nDiferencia en Bs: "
            f"{formato(cierre.sesion.diferencia_bs)}\n"
            f"Diferencia en USD: {formato(cierre.sesion.diferencia_usd)}",
            "Cierre de caja",
        )
        self.accept()
