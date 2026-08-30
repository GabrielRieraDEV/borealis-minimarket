"""Pantalla de categorias y recalculo en bloque de precios (RF-05, RF-08)."""

import sqlite3

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from minimarket.datos.repositorios import categoria as repo_categoria
from minimarket.dominio.producto import Categoria
from minimarket.servicios import ErrorServicio
from minimarket.servicios import catalogo
from minimarket.ui.comunes import ErrorDeCampo, a_decimal, avisar, confirmar, formato

COLUMNAS = ["Nombre", "Margen objetivo %", "Productos", "Estado"]


class PantallaCategorias(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self.categorias: list[Categoria] = []

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla.itemActivated.connect(lambda _: self.editar())

        boton_nueva = QPushButton("&Nueva")
        boton_nueva.clicked.connect(self.nueva)
        boton_editar = QPushButton("&Editar")
        boton_editar.clicked.connect(self.editar)
        boton_recalcular = QPushButton("&Recalcular precios de la categoria")
        boton_recalcular.clicked.connect(self.recalcular)

        botones = QHBoxLayout()
        for boton in (boton_nueva, boton_editar, boton_recalcular):
            botones.addWidget(boton)
        botones.addStretch()

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(self.tabla)
        disposicion.addLayout(botones)
        self.refrescar()

    def refrescar(self) -> None:
        self.categorias = repo_categoria.listar(self.conexion, solo_activas=False)
        self.tabla.setRowCount(len(self.categorias))
        for fila, categoria in enumerate(self.categorias):
            celdas = [
                categoria.nombre,
                formato(categoria.margen_objetivo),
                str(repo_categoria.cantidad_productos(self.conexion, categoria.id)),
                "Activa" if categoria.activo else "De baja",
            ]
            for columna, texto in enumerate(celdas):
                self.tabla.setItem(fila, columna, QTableWidgetItem(texto))

    def seleccionada(self) -> Categoria | None:
        fila = self.tabla.currentRow()
        return self.categorias[fila] if 0 <= fila < len(self.categorias) else None

    def nueva(self) -> None:
        self._abrir_formulario(None)

    def editar(self) -> None:
        categoria = self.seleccionada()
        if categoria is None:
            avisar(self, "Elegi una categoria de la lista.")
            return
        self._abrir_formulario(categoria)

    def recalcular(self) -> None:
        """RF-08. Se muestra que cambiaria y recien despues se aplica."""
        categoria = self.seleccionada()
        if categoria is None:
            avisar(self, "Elegi una categoria de la lista.")
            return
        cambios = catalogo.previsualizar_recalculo(self.conexion, categoria.id)
        if not cambios:
            avisar(
                self,
                "No hay precios para recalcular en esta categoria. Los productos "
                "sin costo de compra registrado quedan fuera del calculo.",
            )
            return
        muestra = "\n".join(
            f"· {producto.nombre}: {formato(producto.precio_venta_usd, 4)} → "
            f"{formato(nuevo, 4)} USD"
            for producto, nuevo in cambios[:15]
        )
        if len(cambios) > 15:
            muestra += f"\n… y {len(cambios) - 15} producto(s) mas."
        if confirmar(
            self,
            f"Se van a actualizar {len(cambios)} precio(s) con el margen "
            f"objetivo de «{categoria.nombre}»:\n\n{muestra}\n\n¿Continuar?",
        ):
            catalogo.aplicar_recalculo(self.conexion, cambios)

    def _abrir_formulario(self, categoria: Categoria | None) -> None:
        dialogo = DialogoCategoria(self.conexion, categoria, self)
        if dialogo.exec() == QDialog.Accepted:
            self.refrescar()


class DialogoCategoria(QDialog):
    def __init__(
        self,
        conexion: sqlite3.Connection,
        categoria: Categoria | None,
        padre: QWidget | None = None,
    ) -> None:
        super().__init__(padre)
        self.conexion = conexion
        self.categoria = categoria
        self.setWindowTitle(
            "Nueva categoria" if categoria is None else "Editar categoria"
        )

        self.nombre = QLineEdit()
        self.margen = QLineEdit("30")
        if categoria is not None:
            self.nombre.setText(categoria.nombre)
            self.margen.setText(str(categoria.margen_objetivo))

        botones = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        botones.button(QDialogButtonBox.Save).setText("Guardar")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.guardar)
        botones.rejected.connect(self.reject)

        formulario = QFormLayout()
        formulario.addRow("Nombre:", self.nombre)
        formulario.addRow("Margen objetivo (%):", self.margen)

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(formulario)
        disposicion.addWidget(botones)

    def guardar(self) -> None:
        try:
            catalogo.guardar_categoria(
                self.conexion,
                Categoria(
                    id=None if self.categoria is None else self.categoria.id,
                    nombre=self.nombre.text().strip(),
                    margen_objetivo=a_decimal(self.margen.text(), "el margen objetivo"),
                    activo=True if self.categoria is None else self.categoria.activo,
                ),
            )
        except (ErrorDeCampo, ErrorServicio) as error:
            avisar(self, str(error))
            return
        self.accept()
