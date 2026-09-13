"""Menu de reportes con vista previa y exportacion a PDF (RF-48 a RF-52).

Cada reporte se arma como columnas + filas de texto ya formateado y un pie de
totales. Con eso alcanza para la tabla de la pantalla y para el PDF, que no
tienen por que saber nada de Decimales ni de reglas de negocio.
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from minimarket.dominio.reportes import COLUMNAS_LIBRO
from minimarket.dominio.usuario import (
    REPORTE_CIERRE,
    REPORTES_GANANCIA,
    VER_EXISTENCIAS,
    VER_REPORTES,
)
from minimarket.dominio.venta import EFECTIVO
from minimarket.infra import bitacora
from minimarket.servicios import ErrorServicio
from minimarket.servicios import configuracion as servicio_configuracion
from minimarket.servicios import reportes as servicio_reportes
from minimarket.servicios import usuarios as servicio_usuarios
from minimarket.servicios import venta as servicio_venta
from minimarket.ui.comunes import avisar, combo_productos, formato


@dataclass
class Reporte:
    """Un reporte ya resuelto, listo para la tabla y para el PDF."""

    titulo: str
    columnas: list[str]
    filas: list[list[str]]
    subtitulo: str = ""
    pie: list[str] = field(default_factory=list)
    estirar: int = 0  # la columna que se lleva el ancho sobrante: la del nombre


class PantallaReportes(QWidget):
    """RF-48 a RF-52. Rango de fechas, vista previa y PDF."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self.reporte: Reporte | None = None

        # Al cajero solo le queda el cierre de su sesion (seccion 6 de las
        # reglas). El servicio lo verifica igual: esto es para no ofrecerle un
        # reporte que le va a dar error.
        self.tipo = QComboBox()
        # Nombres en el idioma del dueno, sin codigos de requisito: los RF-xx
        # estan en el docstring de cada metodo, que es donde le sirven a quien
        # programa.
        for permiso, etiqueta, generador in (
            (VER_REPORTES, "Ventas del dia: que se vendio y como se cobro", self._dia),
            (VER_REPORTES, "Ventas una por una: por cliente, producto o numero", self._una_por_una),
            (VER_REPORTES, "Ventas del periodo, por medio de pago", self._ventas),
            (REPORTE_CIERRE, "Cierre de caja (arqueo)", self._cierre),
            (REPORTES_GANANCIA, "Ganancia por producto", self._ganancia_producto),
            (REPORTES_GANANCIA, "Ganancia por categoria", self._ganancia_categoria),
            (REPORTES_GANANCIA, "Resultado del periodo: ganancia real", self._real),
            (VER_REPORTES, "Inventario valorizado", self._inventario),
            (VER_EXISTENCIAS, "Proximos a vencer", self._vencimientos),
            (REPORTES_GANANCIA, "Perdidas por motivo", self._perdidas),
            (VER_REPORTES, "Libro de ventas (para el contador)", self._libro),
        ):
            if servicio_usuarios.tiene_permiso(conexion, permiso):
                self.tipo.addItem(etiqueta, generador)
        self.tipo.currentIndexChanged.connect(self._cambiar_tipo)

        primero = date.today().replace(day=1)
        self.desde = QDateEdit(QDate(primero.year, primero.month, 1))
        self.hasta = QDateEdit(QDate.currentDate())
        for campo in (self.desde, self.hasta):
            campo.setCalendarPopup(True)
            campo.setDisplayFormat("yyyy-MM-dd")

        self.sesion = QComboBox()
        self.sesion.setVisible(False)

        # Filtros de «Ventas una por una» (1.4.0); todos opcionales.
        self.numero = QLineEdit()
        self.numero.setPlaceholderText("N° de venta")
        self.numero.setMaximumWidth(110)
        self.cliente = QLineEdit()
        self.cliente.setPlaceholderText("Cliente o RIF")
        self.producto = combo_productos(conexion)
        self.producto.lineEdit().setPlaceholderText("Cualquier producto")
        self.filtros = QWidget()
        fila_filtros = QHBoxLayout(self.filtros)
        fila_filtros.setContentsMargins(0, 0, 0, 0)
        for etiqueta, campo in (
            ("Numero:", self.numero),
            ("Cliente:", self.cliente),
            ("Producto:", self.producto),
        ):
            fila_filtros.addWidget(QLabel(etiqueta))
            fila_filtros.addWidget(campo, 1 if campo is not self.numero else 0)
        self.filtros.setVisible(False)
        self.ventas: list = []  # las filas de «una por una», para el doble clic

        boton_ver = QPushButton("&Ver reporte")
        boton_ver.clicked.connect(self.generar)
        self.boton_pdf = QPushButton("Exportar a &PDF")
        self.boton_pdf.clicked.connect(self.exportar)
        self.boton_pdf.setEnabled(False)

        controles = QHBoxLayout()
        controles.addWidget(QLabel("Reporte:"))
        controles.addWidget(self.tipo, 1)
        controles.addWidget(QLabel("Desde:"))
        controles.addWidget(self.desde)
        controles.addWidget(QLabel("Hasta:"))
        controles.addWidget(self.hasta)
        controles.addWidget(self.sesion)
        controles.addWidget(boton_ver)
        controles.addWidget(self.boton_pdf)

        self.tabla = QTableWidget(0, 0)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.cellDoubleClicked.connect(self.abrir_venta)
        self.resumen = QLabel()
        self.resumen.setWordWrap(True)

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(controles)
        disposicion.addWidget(self.filtros)
        disposicion.addWidget(self.tabla)
        disposicion.addWidget(self.resumen)

    # --- Pantalla -----------------------------------------------------------

    def refrescar(self) -> None:
        """La llama la ventana principal al cambiar de pestana."""
        combo_productos(self.conexion, self.producto)  # los dados de alta mientras tanto
        self._cambiar_tipo()

    def _cambiar_tipo(self) -> None:
        es_cierre = self.tipo.currentData() == self._cierre
        es_dia = self.tipo.currentData() == self._dia
        self.sesion.setVisible(es_cierre)
        self.filtros.setVisible(self.tipo.currentData() == self._una_por_una)
        self.desde.setEnabled(not es_cierre and not es_dia)  # el dia es «hasta»
        self.hasta.setEnabled(not es_cierre)
        if es_cierre:
            self._cargar_sesiones()

    def _cargar_sesiones(self) -> None:
        self.sesion.clear()
        try:
            for sesion in servicio_reportes.sesiones(self.conexion):
                estado = "abierta" if sesion.abierta else sesion.fecha_cierre
                self.sesion.addItem(
                    f"#{sesion.id} · {sesion.fecha_apertura} → {estado}", sesion.id
                )
        except ErrorServicio as error:
            avisar(self, str(error))

    def generar(self) -> None:
        if self.tipo.currentData() is None:
            avisar(self, "Tu perfil no tiene reportes habilitados.")
            return
        try:
            self.reporte = self.tipo.currentData()()
        except ErrorServicio as error:
            self.reporte = None
            self.boton_pdf.setEnabled(False)
            avisar(self, str(error))
            return
        self._dibujar(self.reporte)
        self.boton_pdf.setEnabled(True)

    def _dibujar(self, reporte: Reporte) -> None:
        self.tabla.setColumnCount(len(reporte.columnas))
        self.tabla.setHorizontalHeaderLabels(reporte.columnas)
        self.tabla.setRowCount(len(reporte.filas))
        for numero, fila in enumerate(reporte.filas):
            for columna, texto in enumerate(fila):
                self.tabla.setItem(numero, columna, QTableWidgetItem(texto))
        encabezado = self.tabla.horizontalHeader()
        encabezado.setSectionResizeMode(QHeaderView.Interactive)
        self.tabla.resizeColumnsToContents()
        encabezado.setSectionResizeMode(reporte.estirar, QHeaderView.Stretch)
        self.resumen.setText(" · ".join(reporte.pie) or reporte.subtitulo)

    def exportar(self) -> None:
        """Punto 6 de la fase: PDF con encabezado del negocio."""
        if self.reporte is None:
            return
        destino, _ = QFileDialog.getSaveFileName(
            self, "Guardar reporte", f"{self.reporte.titulo}.pdf", "PDF (*.pdf)"
        )
        if not destino:
            return
        from minimarket.infra import pdf  # import diferido: solo al exportar

        try:
            pdf.exportar(
                destino,
                self.reporte.titulo,
                self.reporte.columnas,
                self.reporte.filas,
                negocio=servicio_configuracion.datos_del_negocio(self.conexion),
                subtitulo=self.reporte.subtitulo,
                pie=self.reporte.pie,
            )
        except OSError as error:
            bitacora.anotar(f"Fallo la exportacion a {destino}", error)  # RNF-09
            avisar(
                self,
                "No se pudo guardar el PDF en esa carpeta. Elegi otra "
                "ubicacion o cerra el archivo si ya lo tenes abierto.",
            )
            return
        avisar(self, f"Reporte guardado en {destino}.", "Exportado")

    # --- Los reportes -------------------------------------------------------

    def _rango(self) -> tuple[str, str]:
        return (
            self.desde.date().toString("yyyy-MM-dd"),
            self.hasta.date().toString("yyyy-MM-dd"),
        )

    def _dia(self) -> Reporte:
        """Ventas del dia (1.2.0): productos vendidos y lo cobrado por medio."""
        _, fecha = self._rango()
        return reporte_venta_del_dia(
            servicio_reportes.ventas_del_dia(self.conexion, fecha)
        )

    def _una_por_una(self) -> Reporte:
        """Pedido del cliente (1.4.0): cada venta; doble clic abre su detalle."""
        desde, hasta = self._rango()
        numero = self.numero.text().strip()
        if numero and not numero.isdigit():
            raise ErrorServicio("El numero de venta son solo digitos.")
        texto = self.producto.currentText().strip()
        indice = self.producto.findText(texto) if texto else -1
        if texto and indice < 0:
            raise ErrorServicio(f"No hay ningun producto que se llame «{texto}».")
        self.ventas = servicio_reportes.ventas_una_por_una(
            self.conexion,
            desde,
            hasta,
            numero=int(numero) if numero else None,
            cliente=self.cliente.text(),
            producto_id=self.producto.itemData(indice) if indice >= 0 else None,
        )
        con_producto = indice >= 0
        validas = [v for v in self.ventas if not v.anulada]
        return Reporte(
            titulo="Ventas una por una",
            estirar=3,  # el cliente
            subtitulo=(
                f"Venta N° {numero}" if numero else f"Del {desde} al {hasta}"
            ) + (f" · con {texto}" if con_producto else "")
            + (f" · cliente «{self.cliente.text().strip()}»" if self.cliente.text().strip() else ""),
            columnas=[
                "Numero", "Fecha y hora", "Cajero", "Cliente",
                *(["Cantidad"] if con_producto else []),
                "Total Bs", "Total USD", "Cobrado con", "Estado",
            ],
            filas=[
                [
                    str(v.numero),
                    v.fecha_hora,
                    v.cajero,
                    v.cliente or "Mostrador",
                    *([formato(v.cantidad, 3)] if con_producto else []),
                    formato(v.total_bs),
                    formato(v.total_usd),
                    v.medios,
                    f"ANULADA: {v.motivo_anulacion}" if v.anulada else "",
                ]
                for v in self.ventas
            ],
            pie=[
                f"{len(validas)} ventas",
                *([f"{len(self.ventas) - len(validas)} anuladas"] if len(validas) < len(self.ventas) else []),
                f"Total {formato(sum((v.total_bs for v in validas), Decimal(0)))} Bs",
                f"{formato(sum((v.total_usd for v in validas), Decimal(0)))} USD",
                "Doble clic en una venta para ver su detalle",
            ],
        )

    def abrir_venta(self, fila: int, _columna: int = 0) -> None:
        """El detalle de la venta: la nota de entrega, y reimprimirla."""
        if self.reporte is None or self.reporte.titulo != "Ventas una por una":
            return
        if 0 <= fila < len(self.ventas):
            DialogoDetalleVenta(self.conexion, self.ventas[fila], self).exec()

    def _ventas(self) -> Reporte:
        desde, hasta = self._rango()
        resumen = servicio_reportes.ventas_por_periodo(self.conexion, desde, hasta)
        filas = [
            [
                linea.medio,
                linea.moneda,
                formato(linea.monto),
                formato(linea.monto_usd),
            ]
            for linea in resumen.por_medio
        ]
        return Reporte(
            titulo="Ventas del periodo",
            subtitulo=f"Del {desde} al {hasta}",
            columnas=["Medio de pago", "Moneda", "Cobrado", "Equivale USD"],
            filas=filas,
            pie=[
                f"{resumen.cantidad} ventas",
                f"Exento {formato(resumen.exento_usd)} USD",
                f"Base imponible {formato(resumen.base_imponible_usd)} USD",
                f"IVA {formato(resumen.iva_usd)} USD",
                f"Total {formato(resumen.total_usd)} USD",
            ],
        )

    def _inventario(self) -> Reporte:
        valorizado = servicio_reportes.inventario_valorizado(self.conexion)
        filas = [
            [
                fila.nombre,
                formato(fila.existencia, 3),
                formato(fila.ultimo_costo, 4),
                formato(fila.valorizacion),
            ]
            for fila in valorizado.filas
        ]
        return Reporte(
            titulo="Inventario valorizado",
            subtitulo=f"Al {date.today().isoformat()}, al ultimo costo (RN-30)",
            columnas=["Producto", "Existencia", "Ultimo costo USD", "Valorizado USD"],
            filas=filas,
            pie=[
                f"{len(filas)} productos con existencia",
                f"Valor total {formato(valorizado.total_usd)} USD",
            ],
        )

    def _ganancia_producto(self) -> Reporte:
        desde, hasta = self._rango()
        return self._reporte_ganancia(
            "Ganancia por producto",
            "Producto",
            servicio_reportes.ganancia_por_producto(self.conexion, desde, hasta),
            desde,
            hasta,
        )

    def _ganancia_categoria(self) -> Reporte:
        desde, hasta = self._rango()
        return self._reporte_ganancia(
            "Ganancia por categoria",
            "Categoria",
            servicio_reportes.ganancia_por_categoria(self.conexion, desde, hasta),
            desde,
            hasta,
        )

    def _reporte_ganancia(
        self, titulo: str, encabezado: str, filas, desde: str, hasta: str
    ) -> Reporte:
        ingreso = sum(f.ingreso_usd for f in filas)
        costo = sum(f.costo_usd for f in filas)
        return Reporte(
            titulo=titulo,
            subtitulo=f"Del {desde} al {hasta}, con el costo congelado (RN-27)",
            columnas=[
                encabezado,
                "Cantidad",
                "Ingreso USD",
                "Costo USD",
                "Ganancia USD",
                "Margen %",
            ],
            filas=[
                [
                    fila.nombre,
                    formato(fila.cantidad, 3),
                    formato(fila.ingreso_usd),
                    formato(fila.costo_usd),
                    formato(fila.ganancia_usd),
                    formato(fila.margen_pct)
                    if fila.determinable
                    else "no determinable",
                ]
                for fila in filas
            ],
            pie=[
                f"Ingreso {formato(ingreso)} USD",
                f"CMV {formato(costo)} USD",
                f"Ganancia bruta {formato(ingreso - costo)} USD",
            ],
        )

    def _perdidas(self) -> Reporte:
        desde, hasta = self._rango()
        filas = servicio_reportes.perdidas_por_motivo(self.conexion, desde, hasta)
        total = sum((f.costo_usd for f in filas), Decimal(0))
        return Reporte(
            titulo="Perdidas por motivo",
            subtitulo=(
                f"Del {desde} al {hasta}, al costo vigente en la fecha de cada "
                "baja (RN-18)"
            ),
            columnas=["Motivo", "Cantidad", "Costo USD"],
            filas=[
                [fila.motivo, formato(fila.cantidad, 3), formato(fila.costo_usd)]
                for fila in filas
            ],
            pie=[f"Total perdido {formato(total)} USD"],
        )

    def _vencimientos(self) -> Reporte:
        lotes = servicio_reportes.proximos_a_vencer(self.conexion)
        expuesto = sum((lote.valorizacion for lote in lotes), Decimal(0))
        return Reporte(
            titulo="Productos proximos a vencer",
            subtitulo=(
                f"Al {date.today().isoformat()}, dentro del plazo de aviso de "
                "cada producto (RN-17)"
            ),
            columnas=["Producto", "Vence", "Dias", "Cantidad", "Valorizado USD"],
            filas=[
                [
                    lote.producto,
                    lote.fecha_vencimiento,
                    str(lote.dias_para_vencer()),
                    formato(lote.cantidad, 3),
                    formato(lote.valorizacion),
                ]
                for lote in lotes
            ],
            pie=[
                f"{len(lotes)} lotes en alerta",
                f"{sum(1 for lote in lotes if lote.vencido())} ya vencidos",
                f"{formato(expuesto)} USD en juego",
            ],
        )

    def _real(self) -> Reporte:
        desde, hasta = self._rango()
        resultado = servicio_reportes.ganancia_real(self.conexion, desde, hasta)
        # El reporte es una cuenta corta: cada renglon es un termino de RN-29.
        renglones = [
            ("Vendido, sin IVA", resultado.ingreso_usd),
            ("Lo que costo esa mercancia", -resultado.costo_usd),
            ("Ganancia bruta (lo que dejaron las ventas)", resultado.ganancia_bruta_usd),
            ("Perdidas (vencido, roto, faltante)", -resultado.perdidas_usd),
            ("Gastos del mes (fijos y comisiones)", -resultado.gastos_usd),
            ("Ganancia real (lo que queda)", resultado.ganancia_real_usd),
        ]
        return Reporte(
            titulo="Resultado del periodo",
            subtitulo=f"Del {desde} al {hasta}. Los gastos del mes se cuentan enteros.",
            columnas=["Concepto", "USD"],
            filas=[[concepto, formato(monto)] for concepto, monto in renglones],
            pie=[
                f"Ganancia real {formato(resultado.ganancia_real_usd)} USD",
                f"Margen real {formato(resultado.margen_real_pct)} %"
                if resultado.margen_real_pct is not None
                else "Margen real no determinable: no hubo ventas",
            ],
        )

    def _cierre(self) -> Reporte:
        if self.sesion.currentData() is None:
            raise servicio_reportes.ErrorReporte("No hay sesiones de caja todavia.")
        resumen = servicio_reportes.cierre_de_caja(
            self.conexion, self.sesion.currentData()
        )
        sesion = resumen.sesion
        return Reporte(
            titulo=f"Cierre de caja #{sesion.id}",
            subtitulo=(
                f"Apertura {sesion.fecha_apertura} · "
                f"Cierre {sesion.fecha_cierre or 'sesion abierta'}"
            ),
            columnas=["Medio", "Moneda", "Esperado", "Contado", "Diferencia"],
            filas=[
                [
                    linea.medio,
                    linea.moneda,
                    formato(linea.esperado),
                    formato(linea.conteo) if linea.medio == EFECTIVO else "—",
                    formato(linea.diferencia),
                ]
                for linea in resumen.lineas
            ],
            pie=[
                f"{resumen.ventas} ventas",
                f"Vendido {formato(resumen.total_vendido_usd)} USD",
            ],
        )

    def _libro(self) -> Reporte:
        desde, hasta = self._rango()
        libro = servicio_reportes.libro_de_ventas(self.conexion, desde, hasta)
        totales = libro.totales
        return Reporte(
            titulo="Libro de ventas",
            subtitulo=(
                f"Del {desde} al {hasta}. Importes en bolivares a la tasa de "
                "cada operacion (RN-31)."
            ),
            columnas=[titulo for titulo, _, _ in COLUMNAS_LIBRO],
            filas=[
                [
                    _celda(fila, atributo, decimales)
                    for _, atributo, decimales in COLUMNAS_LIBRO
                ]
                for fila in libro.filas
            ],
            pie=[
                f"{len(libro.filas)} documentos",
                f"Exento {formato(totales.exento_bs)} Bs",
                f"Base imponible {formato(totales.base_imponible_bs)} Bs",
                f"IVA {formato(totales.iva_bs)} Bs",
                f"Total {formato(totales.total_bs)} Bs",
                f"Cobrado {formato(totales.cobrado_bs)} Bs",
            ],
        )


class DialogoDetalleVenta(QDialog):
    """Una venta completa (1.4.0): productos, pagos, vuelto y cliente.

    Muestra la misma nota de entrega que se imprime: un solo formato para
    el papel y la pantalla, y lo que el cliente reclama es lo que tiene en
    la mano.
    """

    def __init__(self, conexion: sqlite3.Connection, venta, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.venta_id = venta.venta_id
        self.setWindowTitle(f"Venta N° {venta.numero}")
        self.resize(460, 620)

        encabezado = [f"Cajero: {venta.cajero}"]
        if venta.anulada:
            encabezado.insert(0, f"*** ANULADA: {venta.motivo_anulacion or ''} ***")
        texto = QPlainTextEdit(
            "\n".join(encabezado + servicio_venta.nota_de_entrega(conexion, venta.venta_id))
        )
        texto.setReadOnly(True)
        texto.setObjectName("notaDeEntrega")  # letra de ancho fijo: `ui/estilo.py`

        botones = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        botones.button(QDialogButtonBox.Close).setText("Cerrar")
        botones.rejected.connect(self.reject)
        if servicio_venta.hay_impresora(conexion):
            reimprimir = botones.addButton("&Reimprimir", QDialogButtonBox.ActionRole)
            reimprimir.clicked.connect(self.reimprimir)

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(texto)
        disposicion.addWidget(botones)

    def reimprimir(self) -> None:
        """RF-39."""
        from minimarket.infra.impresora import ErrorImpresion

        try:
            servicio_venta.imprimir_nota(self.conexion, self.venta_id)
        except ErrorImpresion as error:
            avisar(self, str(error))


def _celda(fila, atributo: str, decimales: int) -> str:
    """RN-31. `COLUMNAS_LIBRO` manda: cambiarlas no toca esta pantalla."""
    valor = getattr(fila, atributo)
    return formato(valor, decimales) if decimales else str(valor)



def reporte_venta_del_dia(dia) -> Reporte:
    """La misma tabla en Reportes y en el cierre de caja: «se vendieron tantas
    harinas y son 23 de pago movil»."""
    medios = " · ".join(
        f"{NOMBRE_MEDIO.get(m.medio, m.medio)} {formato(m.monto)} {m.moneda}"
        for m in dia.por_medio
    )
    return Reporte(
        titulo=dia.titulo,
        subtitulo=f"{dia.ventas} ventas · {formato(dia.total_usd)} USD",
        columnas=["Producto", "Cantidad", "Total USD"],
        filas=[
            [p.nombre, formato(p.cantidad, 3), formato(p.total_usd)]
            for p in dia.productos
        ],
        pie=[
            f"{dia.ventas} ventas por {formato(dia.total_usd)} USD",
            f"Cobrado: {medios}" if medios else "Sin cobros",
        ],
    )


NOMBRE_MEDIO = {
    "EFECTIVO": "Efectivo",
    "PAGO_MOVIL": "Pago movil",
    "PUNTO": "Punto",
    "TRANSFERENCIA": "Transferencia",
}
