"""Panel de inicio del administrador: todo lo que hay que mirar hoy.

Reune las tres alertas que se revisan a diario y no tienen pantalla propia:
lo que hay que reponer (RF-24), lo que esta por vencer (RF-31) y si el
respaldo corrio bien (RF-62). No calcula nada: pregunta a los servicios que ya
existen y lo pone junto.
"""

import sqlite3
from datetime import date, timedelta
from decimal import Decimal

from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from minimarket.servicios import ErrorServicio
from minimarket.servicios import configuracion as servicio_configuracion
from minimarket.servicios import inventario as servicio_inventario
from minimarket.servicios import perdidas as servicio_perdidas
from minimarket.servicios import reportes as servicio_reportes
from minimarket.servicios import tasa as servicio_tasa
from minimarket.ui.comunes import formato
from minimarket.ui.estilo import ESTILO_BIEN, ESTILO_MAL

VERDE = ESTILO_BIEN
ROJO = ESTILO_MAL
FILAS_VISIBLES = 8


class PantallaInicio(QWidget):
    """Punto 7 de la Fase 5. Solo lectura: cada accion vive en su pantalla."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion

        self.tasa = QLabel()
        self.respaldo = QLabel()
        self.respaldo.setWordWrap(True)
        self.reponer = _tabla(["Producto", "Existencia", "Minima"])
        self.vencer = _tabla(["Producto", "Vence", "Dias", "Cantidad"])
        self.titulo_reponer = QGroupBox()
        self.titulo_vencer = QGroupBox()

        _envolver(self.titulo_reponer, self.reponer)
        _envolver(self.titulo_vencer, self.vencer)

        estado = QGroupBox("Estado del sistema")
        interior = QVBoxLayout(estado)
        interior.addWidget(self.tasa)
        interior.addWidget(self.respaldo)

        # Lo que el cliente pregunta todos los meses: ¿los margenes alcanzan?
        self.equilibrio_titulo = QGroupBox()
        self.equilibrio_margen = QLabel()
        self.equilibrio_veredicto = QLabel()
        self.equilibrio_veredicto.setWordWrap(True)
        adentro = QVBoxLayout(self.equilibrio_titulo)
        adentro.addWidget(self.equilibrio_margen)
        adentro.addWidget(self.equilibrio_veredicto)

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(estado)
        disposicion.addWidget(self.equilibrio_titulo)
        disposicion.addWidget(self.titulo_reponer)
        disposicion.addWidget(self.titulo_vencer)

        self.refrescar()

    def refrescar(self) -> None:
        self._estado()
        self._equilibrio()
        self._reponer()
        self._vencer()

    def _equilibrio(self) -> None:
        """¿Al ritmo de este mes, las ventas pagan los gastos?"""
        try:
            equilibrio = servicio_reportes.equilibrio_del_mes(self.conexion)
        except ErrorServicio:
            self.equilibrio_titulo.setVisible(False)
            return
        mes = _nombre_mes(equilibrio.resultado.desde)
        self.equilibrio_titulo.setTitle(f"¿Los margenes cubren los gastos de {mes}?")
        margen, veredicto, bien = _texto_equilibrio(equilibrio, mes)
        self.equilibrio_margen.setText(margen)
        self.equilibrio_veredicto.setText(veredicto)
        self.equilibrio_veredicto.setStyleSheet(
            "" if bien is None else (ESTILO_BIEN if bien else ESTILO_MAL)
        )

    def _estado(self) -> None:
        vigente = servicio_tasa.tasa_del_dia(self.conexion)
        self.tasa.setText(
            f"Tasa de hoy: {formato(vigente, 2)} Bs/USD"
            if vigente is not None
            else "Sin tasa del dia. No se puede abrir la caja ni vender (RN-04)."
        )
        self.tasa.setStyleSheet(VERDE if vigente is not None else ROJO)

        try:
            ultimo = servicio_configuracion.ultimo_respaldo(self.conexion)
        except ErrorServicio:
            ultimo = None
            self.respaldo.setText("El estado del respaldo lo ve el administrador.")
            self.respaldo.setStyleSheet("")
            return
        self.respaldo.setText(_texto_respaldo(ultimo))
        self.respaldo.setStyleSheet(VERDE if _respaldo_al_dia(ultimo) else ROJO)

    def _reponer(self) -> None:
        try:
            filas = servicio_inventario.bajo_minimo(self.conexion)
        except ErrorServicio:
            filas = []
        self.titulo_reponer.setTitle(f"Productos por reponer ({len(filas)})")
        _llenar(
            self.reponer,
            [
                [f.nombre, formato(f.existencia, 3), formato(f.existencia_minima, 3)]
                for f in filas
            ],
        )

    def _vencer(self) -> None:
        try:
            filas = servicio_perdidas.proximos_a_vencer(self.conexion)
        except ErrorServicio:
            filas = []
        expuesto = sum((f.valorizacion for f in filas), start=Decimal(0))
        self.titulo_vencer.setTitle(
            f"Lotes por vencer ({len(filas)}) · {formato(expuesto)} USD en juego"
        )
        _llenar(
            self.vencer,
            [
                [
                    f.producto,
                    f.fecha_vencimiento,
                    str(f.dias_para_vencer()),
                    formato(f.cantidad, 3),
                ]
                for f in filas
            ],
        )


def _texto_equilibrio(equilibrio, mes: str) -> tuple[str, str, bool | None]:
    """Dos renglones: que dejan las ventas, y si alcanza. Sin jerga contable."""
    resultado = equilibrio.resultado
    gastos = resultado.gastos_usd
    if resultado.ingreso_usd <= 0:
        return (
            f"Todavia no hay ventas en {mes}.",
            f"Gastos cargados: {formato(gastos)} USD."
            if gastos > 0
            else "Tampoco hay gastos cargados. Cargalos en Gastos (Ctrl+G).",
            None,
        )
    margen = (
        f"En {equilibrio.dias_transcurridos} dias se vendieron "
        f"{formato(resultado.ingreso_usd)} USD y dejaron "
        f"{formato(equilibrio.contribucion_usd)} USD: un margen bruto de "
        f"{formato(equilibrio.margen_bruto_pct)} %."
    )
    if gastos <= 0:
        return (
            margen,
            f"No hay gastos cargados para {mes}, asi que no se puede saber si "
            "alcanzan. Cargalos en Gastos (Ctrl+G); si son los mismos del mes "
            "pasado, ahi esta «Repetir los del mes anterior».",
            None,
        )
    proyectado = equilibrio.resultado_proyectado_usd
    if equilibrio.cubre:
        return (
            margen,
            f"Al mismo ritmo, {mes} cierra con {formato(gastos)} USD de gastos "
            f"pagados y {formato(proyectado)} USD de ganancia.",
            True,
        )
    faltante = -proyectado
    remedio = ""
    if equilibrio.ventas_necesarias_usd is not None:
        remedio = (
            f" Para empatar hace falta vender {formato(equilibrio.ventas_necesarias_usd)} "
            f"USD en el mes (van {formato(resultado.ingreso_usd)}), o llevar el "
            f"margen bruto a {formato(equilibrio.margen_necesario_pct)} % "
            "subiendo precios."
        )
    return (
        margen,
        f"Al mismo ritmo, {mes} cierra con {formato(faltante)} USD de gastos "
        f"sin cubrir." + remedio,
        False,
    )


MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _nombre_mes(fecha: str) -> str:
    return MESES[int(fecha[5:7]) - 1]


def _texto_respaldo(ultimo) -> str:
    """RF-62. Que paso con el ultimo respaldo, en una linea."""
    if ultimo is None:
        return (
            "Todavia no se respaldo nunca. Configura la carpeta en "
            "Archivo → Configuracion."
        )
    if not ultimo.ok:
        return f"El ultimo respaldo ({ultimo.fecha_hora}) fallo: {ultimo.mensaje}"
    if _respaldo_al_dia(ultimo):
        return f"Ultimo respaldo correcto: {ultimo.fecha_hora}"
    return (
        f"El ultimo respaldo correcto es del {ultimo.fecha_hora}. "
        "Hace mas de un dia que no se respalda."
    )


def _respaldo_al_dia(ultimo) -> bool:
    """Corrio bien hoy o ayer. Mas viejo que eso ya es un aviso."""
    if ultimo is None or not ultimo.ok:
        return False
    return ultimo.fecha_hora[:10] >= (date.today() - timedelta(days=1)).isoformat()


def _tabla(columnas: list[str]) -> QTableWidget:
    tabla = QTableWidget(0, len(columnas))
    tabla.setHorizontalHeaderLabels(columnas)
    tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
    tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    return tabla


def _envolver(caja: QGroupBox, tabla: QTableWidget) -> None:
    interior = QVBoxLayout(caja)
    interior.addWidget(tabla)


def _llenar(tabla: QTableWidget, filas: list[list[str]]) -> None:
    """Muestra las primeras; el detalle completo esta en su propia pantalla."""
    visibles = filas[:FILAS_VISIBLES]
    tabla.setRowCount(len(visibles))
    for numero, fila in enumerate(visibles):
        for columna, texto in enumerate(fila):
            tabla.setItem(numero, columna, QTableWidgetItem(texto))
