"""Utilidades compartidas por las pantallas.

Los importes se leen de la pantalla como texto y se convierten a `Decimal`.
No se usa QDoubleSpinBox para dinero: guarda el valor como `float`.
"""

import sqlite3
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QMessageBox, QWidget

from minimarket.servicios import catalogo


class ErrorDeCampo(Exception):
    """Dato mal cargado en un formulario. El mensaje ya es para el usuario."""


def a_decimal(texto: str, campo: str, opcional: bool = False) -> Decimal | None:
    """Convierte el texto de un campo a Decimal. Acepta coma o punto decimal."""
    texto = texto.strip().replace(",", ".")
    if not texto:
        if opcional:
            return None
        raise ErrorDeCampo(f"Falta completar {campo}.")
    try:
        return Decimal(texto)
    except InvalidOperation as error:
        raise ErrorDeCampo(f"{campo.capitalize()} tiene que ser un numero.") from error


def formato(valor: Decimal | None, decimales: int = 2) -> str:
    """Muestra un importe con separador de miles, o un guion si no hay valor."""
    if valor is None:
        return "—"
    return f"{valor:,.{decimales}f}"


def combo_productos(conexion: sqlite3.Connection) -> QComboBox:
    """Selector con autocompletado por nombre; el catalogo entra entero.

    `currentData()` devuelve el id del producto, o None si no se eligio nada.
    """
    combo = QComboBox()
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.completer().setFilterMode(Qt.MatchContains)
    for producto in catalogo.listado_completo(conexion):
        combo.addItem(producto.nombre, producto.id)
    combo.setCurrentIndex(-1)
    return combo


def avisar(padre: QWidget, mensaje: str, titulo: str = "Atencion") -> None:
    QMessageBox.warning(padre, titulo, mensaje)


def confirmar(padre: QWidget, mensaje: str, titulo: str = "Confirmar") -> bool:
    return QMessageBox.question(padre, titulo, mensaje) == QMessageBox.Yes
