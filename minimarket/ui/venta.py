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
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from minimarket.dominio.usuario import ANULAR_VENTAS
from minimarket.dominio.venta import BS, MEDIOS, MONEDAS, Cliente, LineaVenta, Venta
from minimarket.servicios import ErrorServicio, usuario_actual
from minimarket.servicios import caja as servicio_caja
from minimarket.servicios import catalogo
from minimarket.servicios import tasa as servicio_tasa
from minimarket.servicios import usuarios as servicio_usuarios
from minimarket.servicios import venta as servicio_venta
from minimarket.ui.comunes import ErrorDeCampo, a_decimal, avisar, confirmar, formato
from minimarket.ui.usuarios import pedir_autorizacion

COLUMNAS = ["Producto", "Cantidad", "Precio USD", "IVA %", "Total USD"]
COLUMNAS_PAGO = ["Medio", "Moneda", "Monto", "Equivale USD", "Referencia"]
COLUMNAS_ARQUEO = ["Medio", "Moneda", "Esperado", "Contado", "Diferencia"]


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
                f"tasa {formato(self.tasa, 6)} Bs/USD"
            )
        self._pintar()

    def _pintar(self) -> None:
        venta = self._venta_en_curso()
        self.tabla.setRowCount(len(self.lineas))
        for fila, linea in enumerate(self.lineas):
            celdas = [
                linea.descripcion,
                formato(linea.cantidad, 3),
                formato(linea.precio_unit_usd, 4),
                formato(linea.alicuota_pct),
                formato(linea.total_linea_usd),
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
        dialogo = DialogoCobro(venta, self)
        if dialogo.exec() != QDialog.Accepted:
            self.codigo.setFocus()
            return
        venta.pagos = dialogo.pagos
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

    def __init__(self, venta: Venta, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self.venta = venta
        self.pagos = []
        self.setWindowTitle("Cobrar")
        self.resize(760, 460)

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
        disposicion.addWidget(botones)

        self._pintar()
        self.monto.setFocus()

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

        if self.venta.falta_usd > 0:
            self.saldo.setText(f"FALTA  {formato(self.venta.falta_usd)} USD")
        elif self.venta.vuelto_usd > 0:
            self.saldo.setText(
                f"VUELTO  {formato(self.venta.vuelto_usd)} USD  ·  "
                f"{formato(self.venta.vuelto_bs())} Bs"
            )
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
        self.resize(620, 420)

        self.tabla = QTableWidget(0, len(COLUMNAS_ARQUEO))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS_ARQUEO)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

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

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(self.resumen)
        disposicion.addWidget(self.tabla)
        disposicion.addLayout(formulario)
        disposicion.addWidget(botones)

        self._pintar()

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
