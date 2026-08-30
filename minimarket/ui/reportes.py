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
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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
from minimarket.ui.comunes import avisar, formato


@dataclass
class Reporte:
    """Un reporte ya resuelto, listo para la tabla y para el PDF."""

    titulo: str
    columnas: list[str]
    filas: list[list[str]]
    subtitulo: str = ""
    pie: list[str] = field(default_factory=list)


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
        for permiso, etiqueta, generador in (
            (VER_REPORTES, "Ventas del periodo (RF-48)", self._ventas),
            (VER_REPORTES, "Inventario valorizado (RF-49)", self._inventario),
            (
                REPORTES_GANANCIA,
                "Ganancia por producto (RF-50)",
                self._ganancia_producto,
            ),
            (
                REPORTES_GANANCIA,
                "Ganancia por categoria (RF-50)",
                self._ganancia_categoria,
            ),
            (REPORTE_CIERRE, "Cierre de caja (RF-51)", self._cierre),
            (VER_REPORTES, "Libro de ventas (RF-52)", self._libro),
            (REPORTES_GANANCIA, "Perdidas por motivo (RF-53)", self._perdidas),
            (VER_EXISTENCIAS, "Proximos a vencer (RF-54)", self._vencimientos),
            (REPORTES_GANANCIA, "Ganancia real del periodo (RF-55)", self._real),
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
        self.resumen = QLabel()
        self.resumen.setWordWrap(True)

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(controles)
        disposicion.addWidget(self.tabla)
        disposicion.addWidget(self.resumen)

    # --- Pantalla -----------------------------------------------------------

    def refrescar(self) -> None:
        """La llama la ventana principal al cambiar de pestana."""
        self._cambiar_tipo()

    def _cambiar_tipo(self) -> None:
        es_cierre = self.tipo.currentData() == self._cierre
        self.sesion.setVisible(es_cierre)
        self.desde.setEnabled(not es_cierre)
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
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
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
            ("Ingreso sin IVA (base imponible + exento)", resultado.ingreso_usd),
            ("Costo de la mercancia vendida (RN-27)", -resultado.costo_usd),
            ("Ganancia bruta (RN-28)", resultado.ganancia_bruta_usd),
            ("Perdidas del periodo (RN-18)", -resultado.perdidas_usd),
            ("Gastos operativos", -resultado.gastos_usd),
            ("Ganancia real (RN-29)", resultado.ganancia_real_usd),
        ]
        return Reporte(
            titulo="Ganancia real del periodo",
            subtitulo=f"Del {desde} al {hasta}. Los gastos no se prorratean.",
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
            ],
        )


def _celda(fila, atributo: str, decimales: int) -> str:
    """RN-31. `COLUMNAS_LIBRO` manda: cambiarlas no toca esta pantalla."""
    valor = getattr(fila, atributo)
    return formato(valor, decimales) if decimales else str(valor)
