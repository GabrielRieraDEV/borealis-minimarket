"""Utilidades compartidas por las pantallas.

Los importes se leen de la pantalla como texto y se convierten a `Decimal`.
No se usa QDoubleSpinBox para dinero: guarda el valor como `float`.
"""

from decimal import Decimal, InvalidOperation

from PySide6.QtWidgets import QMessageBox, QWidget


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


def avisar(padre: QWidget, mensaje: str, titulo: str = "Atencion") -> None:
    QMessageBox.warning(padre, titulo, mensaje)


def confirmar(padre: QWidget, mensaje: str, titulo: str = "Confirmar") -> bool:
    return QMessageBox.question(padre, titulo, mensaje) == QMessageBox.Yes
