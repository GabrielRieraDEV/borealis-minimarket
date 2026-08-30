"""Nota de entrega por impresora termica ESC/POS (RF-39).

El comprobante se arma en dos pasos a proposito:

  1. `nota_de_entrega` devuelve el texto, sin tocar hardware. Es lo que se
     prueba, lo que se previsualiza y lo que reimprime la pantalla.
  2. `imprimir` lo manda a la impresora.

El dia que entre una maquina fiscal, el paso 1 no cambia: el desglose de
exento, base imponible e IVA que exige RF-39 ya esta separado, y solo hay que
reemplazar el paso 2 por el driver fiscal.

Si la impresora no responde, la venta YA esta registrada: `imprimir` levanta
`ErrorImpresion` y la pantalla ofrece reimprimir. Nunca se pierde la venta.
"""

import logging
import os
import sys
from decimal import Decimal

from minimarket.dominio.venta import Cliente, Venta

ANCHO = 42  # columnas de una termica de 80 mm en fuente A

_bitacora = logging.getLogger(__name__)


class ErrorImpresion(Exception):
    """La venta esta registrada; solo fallo la impresion."""


def nota_de_entrega(
    venta: Venta,
    negocio: dict[str, str],
    cliente: Cliente | None = None,
    multiplo: Decimal = Decimal(1),
) -> list[str]:
    """RF-39. El comprobante completo, linea por linea."""
    lineas = _encabezado(negocio)
    lineas += [
        _separador(),
        f"NOTA DE ENTREGA N° {venta.numero:06d}",
        f"Fecha: {venta.fecha_hora or ''}",
    ]
    if cliente is not None:
        lineas += [
            f"Cliente: {cliente.razon_social or ''}",
            f"RIF: {cliente.rif or ''}",
        ]
        if cliente.direccion_fiscal:
            lineas.append(f"Direccion: {cliente.direccion_fiscal}")
    lineas += [_separador(), _columnas("CANT x PRECIO", "TOTAL USD")]

    for linea in venta.lineas:
        lineas.append(linea.descripcion[:ANCHO])
        detalle = (
            f"  {_importe(linea.cantidad, 3)} x {_importe(linea.precio_unit_usd, 4)}"
            f"{'' if linea.exenta else ' (G)'}"
        )
        lineas.append(_columnas(detalle, _importe(linea.total_linea_usd)))

    # RN-21: el desglose separado es requisito del libro de ventas.
    lineas += [
        _separador(),
        _columnas("Exento", _importe(venta.exento_usd)),
        _columnas("Base imponible", _importe(venta.base_imponible_usd)),
        _columnas("IVA", _importe(venta.iva_usd)),
        _columnas("TOTAL USD", _importe(venta.total_usd)),
        _columnas("TOTAL Bs", _importe(venta.total_bs)),
        f"Tasa: {_importe(venta.tasa, 6)} Bs/USD",
        _separador(),
        "FORMA DE PAGO",
    ]
    for cobro in venta.pagos:
        etiqueta = f"{cobro.medio.replace('_', ' ').title()} {cobro.moneda}"
        lineas.append(
            _columnas(etiqueta, f"{_importe(cobro.monto)} {cobro.moneda}")
        )
    if venta.vuelto_usd > 0:
        # RN-23: el vuelto se entrega en bolivares, ya redondeado.
        lineas.append(
            _columnas(
                f"Vuelto ({_importe(venta.vuelto_usd)} USD)",
                f"{_importe(venta.vuelto_bs(multiplo))} Bs",
            )
        )
    lineas += [
        _separador(),
        _centrado("Este documento no es una factura"),
        _centrado("Gracias por su compra"),
        "",
    ]
    return lineas


def imprimir(lineas: list[str], destino: str) -> None:
    """Manda el comprobante a la impresora ESC/POS configurada."""
    if not destino.strip():
        raise ErrorImpresion(
            "No hay impresora configurada. Cargala en la configuracion del "
            "negocio para poder imprimir la nota de entrega."
        )
    try:
        impresora = _abrir(destino.strip())
        impresora.text("\n".join(lineas) + "\n")
        impresora.cut()
        impresora.close()
    except Exception as error:  # papel, puerto ocupado, impresora apagada
        _bitacora.warning("No se pudo imprimir la nota de entrega: %s", error)
        raise ErrorImpresion(
            f"No se pudo imprimir en «{destino}»: {error}. La venta quedo "
            "registrada; podes reimprimir la nota cuando la impresora responda."
        ) from error


def _abrir(destino: str):
    """Nombre de impresora de Windows, o ruta de dispositivo en cualquier SO."""
    from escpos import printer  # import diferido: sin impresora no hace falta

    if sys.platform == "win32" and os.sep not in destino:
        return printer.Win32Raw(destino)
    return printer.File(destino)


# --- Maquetado --------------------------------------------------------------


def _encabezado(negocio: dict[str, str]) -> list[str]:
    """RF-39. Datos fiscales del negocio."""
    lineas = [_centrado((negocio.get("nombre") or "MINIMARKET").upper())]
    for clave, prefijo in (
        ("rif", "RIF: "),
        ("direccion", ""),
        ("telefono", "Tel: "),
    ):
        valor = (negocio.get(clave) or "").strip()
        if valor:
            lineas.append(_centrado(f"{prefijo}{valor}"))
    return lineas


def _separador() -> str:
    return "-" * ANCHO


def _centrado(texto: str) -> str:
    return texto[:ANCHO].center(ANCHO).rstrip()


def _columnas(izquierda: str, derecha: str) -> str:
    """Etiqueta a la izquierda, importe pegado al margen derecho."""
    espacio = max(ANCHO - len(derecha) - 1, 1)
    return f"{izquierda[:espacio]:<{espacio}} {derecha:>{ANCHO - espacio - 1}}"


def _importe(valor: Decimal, decimales: int = 2) -> str:
    return f"{valor:,.{decimales}f}"
