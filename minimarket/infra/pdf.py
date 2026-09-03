"""Exportacion de reportes a PDF con reportlab (punto 6 de la Fase 4).

Una sola funcion para todos los reportes: encabezado del negocio, titulo,
periodo, una tabla y una linea de totales. Los reportes ya llegan como texto
formateado —quien sabe cuantos decimales lleva cada columna es quien arma el
reporte, no el que lo imprime.
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from minimarket.infra import bitacora

# Mas de esto no entra legible ni en horizontal.
COLUMNAS_APAISADO = 6

ALTO_LOGO = 25 * mm  # el ancho sale de la proporcion de la imagen

_GRIS = colors.HexColor("#e8e8e8")
_LINEA = colors.HexColor("#999999")


def exportar(
    destino: str | Path,
    titulo: str,
    columnas: list[str],
    filas: list[list[str]],
    negocio: dict[str, str] | None = None,
    subtitulo: str = "",
    pie: list[str] | None = None,
) -> Path:
    """Escribe el PDF y devuelve su ruta.

    `pie` son las lineas de totales, que van despues de la tabla y no dentro:
    asi no se confunden con un renglon mas si el reporte se corta de pagina.
    """
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    estilos = getSampleStyleSheet()
    apaisado = len(columnas) > COLUMNAS_APAISADO

    documento = SimpleDocTemplate(
        str(destino),
        pagesize=landscape(A4) if apaisado else A4,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        title=titulo,
    )

    contenido = []
    logo = _logo((negocio or {}).get("logo", ""))
    if logo is not None:
        contenido.append(logo)
    for linea in _encabezado(negocio or {}):
        contenido.append(Paragraph(linea, estilos["Normal"]))
    contenido.append(Spacer(1, 6 * mm))
    contenido.append(Paragraph(titulo, estilos["Heading2"]))
    if subtitulo:
        contenido.append(Paragraph(subtitulo, estilos["Normal"]))
    contenido.append(Spacer(1, 4 * mm))

    tabla = Table([columnas, *filas] if filas else [columnas, ["Sin datos"]])
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _GRIS),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.25, _LINEA),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                # Las columnas de importes son las de la derecha en todos los
                # reportes; la primera siempre es la descripcion.
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ]
        )
    )
    contenido.append(tabla)

    for linea in pie or []:
        contenido.append(Spacer(1, 2 * mm))
        contenido.append(Paragraph(f"<b>{linea}</b>", estilos["Normal"]))

    documento.build(contenido)
    return destino


def _logo(ruta: str) -> Image | None:
    """RF-64. El logotipo configurado, escalado a `ALTO_LOGO`.

    Un logo ilegible o borrado no puede tumbar un reporte: si reportlab no lo
    puede leer, el PDF sale sin logo y el motivo queda en la bitacora.
    """
    if not ruta.strip() or not Path(ruta).is_file():
        return None
    try:
        imagen = Image(ruta)
        imagen.drawWidth *= ALTO_LOGO / imagen.drawHeight
        imagen.drawHeight = ALTO_LOGO
        imagen.hAlign = "LEFT"
        return imagen
    except Exception as error:  # formato no soportado, archivo cortado
        bitacora.anotar(f"No se pudo incrustar el logotipo {ruta}", error)
        return None


def _encabezado(negocio: dict[str, str]) -> list[str]:
    """RF-64. Lo que este cargado; el resto no ocupa renglon."""
    lineas = [f"<b>{negocio.get('nombre') or 'Minimarket'}</b>"]
    if negocio.get("rif"):
        lineas.append(f"RIF: {negocio['rif']}")
    if negocio.get("direccion"):
        lineas.append(negocio["direccion"])
    if negocio.get("telefono"):
        lineas.append(f"Telefono: {negocio['telefono']}")
    return lineas
