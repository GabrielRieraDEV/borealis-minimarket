"""Hoja de estilo de la aplicacion.

Una sola paleta, sacada del logotipo de Provisiones Jireh: el verde de la
cinta, el crema del sello, el dorado de las letras y la tinta marron. Todo
lo que se ve pasa por aca; ninguna pantalla trae colores propios, asi que
cambiar la identidad es tocar este archivo.

Las fuentes son las que trae Windows 10: Segoe UI para todo y Bahnschrift
—condensada, de etiqueta de precio— para los totales que lee el cliente del
otro lado del mostrador. Sin archivos de fuente que empaquetar.

Los widgets que necesitan un trato distinto se nombran con `setObjectName` y
se seleccionan aca por `#nombre`: el campo del lector, el total en bolivares.
"""

from PySide6.QtWidgets import QApplication

CREMA = "#FBF7EE"       # fondo de ventana: el papel del sello
PAPEL = "#FFFFFF"       # tablas y campos
TRIGO = "#E6D9B8"       # bordes y separadores: las espigas
TRIGO_SUAVE = "#F2EBDA"
VERDE = "#2F7A3E"       # la cinta del logo: accion principal
VERDE_OSCURO = "#1F5A2B"
VERDE_CLARO = "#DDEBDD"  # seleccion en tablas
DORADO = "#D9901F"      # las letras del logo: el foco del teclado
TINTA = "#2B2416"
TINTA_SUAVE = "#6B5F4A"
ROJO = "#B3261E"

# Los dos que las pantallas usan para pintar estado (tasa cargada o no,
# respaldo al dia o no). Se exponen para que `ui/inicio.py` no invente otros.
ESTILO_BIEN = f"color: {VERDE_OSCURO}; font-weight: 600;"
ESTILO_MAL = f"color: {ROJO}; font-weight: 600;"

HOJA = f"""
QWidget {{
    background: {CREMA};
    color: {TINTA};
    font-family: "Segoe UI", sans-serif;
    font-size: 10pt;
}}
QToolTip {{
    background: {TINTA};
    color: {CREMA};
    border: none;
    padding: 4px 8px;
}}

/* --- Navegacion: la cinta verde ---------------------------------------- */
QMenuBar {{
    background: {CREMA};
    border-bottom: 1px solid {TRIGO};
    padding: 2px 6px;
}}
QMenuBar::item {{ padding: 4px 10px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {TRIGO_SUAVE}; }}
QMenu {{
    background: {PAPEL};
    border: 1px solid {TRIGO};
    padding: 4px;
}}
QMenu::item {{ padding: 6px 28px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {VERDE}; color: {PAPEL}; }}
QMenu::separator {{ height: 1px; background: {TRIGO}; margin: 4px 8px; }}

QTabWidget::pane {{
    border: 1px solid {TRIGO};
    border-top: 3px solid {VERDE};
    background: {CREMA};
}}
QTabBar {{ background: {CREMA}; }}
QTabBar::tab {{
    background: {TRIGO_SUAVE};
    color: {TINTA_SUAVE};
    padding: 7px 11px;
    margin-right: 2px;
    border: 1px solid {TRIGO};
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    font-weight: 600;
}}
QTabBar::tab:hover {{ color: {TINTA}; }}
QTabBar::tab:selected {{
    background: {VERDE};
    color: {PAPEL};
    border-color: {VERDE};
}}

QStatusBar {{
    background: {VERDE_OSCURO};
    color: {CREMA};
    font-weight: 600;
}}
QStatusBar::item {{ border: none; }}

/* --- Campos ------------------------------------------------------------ */
QLineEdit, QComboBox, QDateEdit, QTextEdit, QPlainTextEdit {{
    background: {PAPEL};
    border: 1px solid {TRIGO};
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: {VERDE};
    selection-color: {PAPEL};
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus,
QPlainTextEdit:focus {{
    border: 2px solid {DORADO};
    padding: 4px 7px;
}}
QLineEdit:read-only {{ background: {TRIGO_SUAVE}; color: {TINTA_SUAVE}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {PAPEL};
    border: 1px solid {TRIGO};
    selection-background-color: {VERDE};
    selection-color: {PAPEL};
}}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {TRIGO};
    border-radius: 3px;
    background: {PAPEL};
}}
QCheckBox::indicator:checked {{ background: {VERDE}; border-color: {VERDE_OSCURO}; }}

/* --- Botones ----------------------------------------------------------- */
QPushButton {{
    background: {PAPEL};
    border: 1px solid #CDBE9A;
    border-radius: 4px;
    padding: 6px 14px;
    min-height: 16px;
}}
QPushButton:hover {{ background: {TRIGO_SUAVE}; }}
QPushButton:pressed {{ background: {TRIGO}; }}
QPushButton:focus {{ border: 2px solid {DORADO}; padding: 5px 13px; }}
QPushButton:disabled {{ color: #A89C86; border-color: {TRIGO}; }}
QPushButton:default, #botonPrincipal {{
    background: {VERDE};
    color: {PAPEL};
    border-color: {VERDE_OSCURO};
    font-weight: 600;
}}
QPushButton:default:hover, #botonPrincipal:hover {{ background: {VERDE_OSCURO}; }}

/* --- Tablas ------------------------------------------------------------ */
QTableWidget, QTableView {{
    background: {PAPEL};
    alternate-background-color: {CREMA};
    gridline-color: {TRIGO_SUAVE};
    border: 1px solid {TRIGO};
    selection-background-color: {VERDE_CLARO};
    selection-color: {TINTA};
}}
QTableWidget::item {{ padding: 3px 6px; }}
QHeaderView::section {{
    background: {TRIGO_SUAVE};
    color: {TINTA_SUAVE};
    padding: 6px;
    border: none;
    border-bottom: 1px solid {TRIGO};
    border-right: 1px solid {CREMA};
    font-weight: 600;
}}
QTableCornerButton::section {{ background: {TRIGO_SUAVE}; border: none; }}
QScrollBar:vertical {{ background: {CREMA}; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {TRIGO}; border-radius: 5px; min-height: 24px; margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background: #CDBE9A; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: {CREMA}; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: {TRIGO}; border-radius: 5px; min-width: 24px; margin: 2px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* --- Agrupadores ------------------------------------------------------- */
QGroupBox {{
    border: 1px solid {TRIGO};
    border-radius: 6px;
    margin-top: 16px;
    padding: 10px 6px 6px 6px;
    font-weight: 600;
    color: {VERDE_OSCURO};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}}

/* --- Punto de venta ---------------------------------------------------- */
#codigo {{
    font-size: 15pt;
    padding: 9px 12px;
    border: 2px solid {VERDE};
}}
#codigo:focus {{ border: 2px solid {DORADO}; padding: 9px 12px; }}
#estadoCaja {{ color: {TINTA_SUAVE}; }}
#panelTotales {{
    background: {VERDE};
    border-radius: 8px;
}}
#panelTotales QLabel {{ background: transparent; color: {PAPEL}; }}
#totalBs {{
    font-family: "Bahnschrift SemiBold Condensed", "Bahnschrift", "Segoe UI";
    font-size: 40pt;
    font-weight: 600;
}}
#totalUsd {{
    font-family: "Bahnschrift", "Segoe UI";
    font-size: 18pt;
    color: {VERDE_CLARO};
}}
#etiquetaTotal {{ font-size: 9pt; color: {VERDE_CLARO}; letter-spacing: 2px; }}
#totalCobro, #saldoCobro {{
    font-family: "Bahnschrift SemiBold Condensed", "Bahnschrift", "Segoe UI";
    font-size: 20pt;
    font-weight: 600;
    color: {VERDE_OSCURO};
}}

/* --- Ingreso ----------------------------------------------------------- */
#tarjetaIngreso {{
    background: {PAPEL};
    border: 1px solid {TRIGO};
    border-radius: 10px;
}}
#tarjetaIngreso QLabel {{ background: transparent; }}
#tituloIngreso {{
    font-family: "Bahnschrift SemiBold", "Bahnschrift", "Segoe UI";
    font-size: 16pt;
    color: {VERDE_OSCURO};
}}
#subtituloIngreso {{ color: {TINTA_SUAVE}; }}
"""


def aplicar(aplicacion: QApplication) -> None:
    """Fusion como base: el estilo nativo de Windows ignora media hoja."""
    aplicacion.setStyle("Fusion")
    aplicacion.setStyleSheet(HOJA)
