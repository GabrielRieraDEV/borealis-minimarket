"""Utilidades compartidas por las pantallas.

Los importes se leen de la pantalla como texto y se convierten a `Decimal`.
No se usa QDoubleSpinBox para dinero: guarda el valor como `float`.
"""

import sqlite3
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QMessageBox, QWidget

from minimarket.dominio.fechas import a_iso
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


def a_fecha(texto: str, campo: str, opcional: bool = False) -> str | None:
    """Convierte el texto de un campo a fecha ISO. Acepta AAAA-MM-DD o DD-MM-AAAA.

    Sin esto, lo que el cajero teclea entra crudo a la base y revienta despues,
    lejos de donde se cargo.
    """
    texto = texto.strip()
    if not texto:
        if opcional:
            return None
        raise ErrorDeCampo(f"Falta completar {campo}.")
    fecha = a_iso(texto)
    if fecha is None:
        raise ErrorDeCampo(
            f"{campo.capitalize()} no es una fecha valida. "
            "Escribila como 2027-02-01 o 01-02-2027."
        )
    return fecha


def formato(valor: Decimal | None, decimales: int = 2) -> str:
    """Muestra un importe con separador de miles, o un guion si no hay valor."""
    if valor is None:
        return "—"
    return f"{valor:,.{decimales}f}"


def combo_productos(
    conexion: sqlite3.Connection, combo: QComboBox | None = None
) -> QComboBox:
    """Selector con autocompletado por nombre; el catalogo entra entero.

    `currentData()` devuelve el id del producto, o None si no se eligio nada.
    Con `combo`, lo vuelve a llenar y conserva lo que estaba escrito.
    """
    escrito = combo.currentText() if combo is not None else ""
    if combo is None:
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.completer().setFilterMode(Qt.MatchContains)
    combo.clear()
    for producto in catalogo.listado_completo(conexion):
        combo.addItem(producto.nombre, producto.id)
    combo.setCurrentIndex(combo.findText(escrito) if escrito else -1)
    if escrito and combo.currentIndex() < 0:
        combo.setEditText(escrito)
    return combo


def avisar(padre: QWidget, mensaje: str, titulo: str = "Atencion") -> None:
    QMessageBox.warning(padre, titulo, mensaje)


def detallar(
    padre: QWidget, mensaje: str, detalle: list[str], titulo: str = "Atencion"
) -> None:
    """Aviso con el detalle largo plegado, para listas de errores por fila."""
    caja = QMessageBox(QMessageBox.Warning, titulo, mensaje, parent=padre)
    caja.setDetailedText("\n".join(detalle))
    caja.exec()


def avisar_error_no_controlado(archivo) -> None:
    """RNF-09 / RNF-13. Lo que se muestra cuando revienta algo no previsto.

    Se llama desde el manejador de `infra/bitacora.py`, que puede dispararse
    antes de que exista la ventana: sin QApplication no hay donde dibujar y el
    error ya quedo en el archivo, que es lo que importa.
    """
    if QApplication.instance() is None:
        return
    QMessageBox.critical(
        None,
        "Ocurrio un error inesperado",
        "La operacion no se pudo completar. Volve a intentarla; si el "
        "problema se repite, cerra y volve a abrir el sistema.\n\n"
        f"El detalle quedo anotado en:\n{archivo}",
    )


def confirmar(padre: QWidget, mensaje: str, titulo: str = "Confirmar") -> bool:
    return QMessageBox.question(padre, titulo, mensaje) == QMessageBox.Yes
