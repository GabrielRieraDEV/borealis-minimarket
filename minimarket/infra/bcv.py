"""Consulta de la tasa oficial del BCV (RF-10).

Es la unica funcion del sistema que necesita internet (RNF-01), y siempre tiene
la carga manual como alternativa: ante cualquier falla devuelve None y no
propaga la excepcion. Nunca asume la tasa del dia anterior (RN-04).
"""

import logging
import re
from decimal import Decimal, InvalidOperation

URL_POR_DEFECTO = "https://www.bcv.org.ve/"
TIMEOUT_SEGUNDOS = 5.0

# El BCV publica el dolar en un bloque con id="dolar" y formato venezolano
# (punto de miles, coma decimal). ponytail: es raspado de HTML y se va a romper
# el dia que el BCV cambie la pagina; por eso RF-11 exige la carga manual y esta
# funcion se limita a devolver None.
_PATRON = re.compile(r'id="dolar".*?([\d.]+,\d+)', re.DOTALL)

_bitacora = logging.getLogger(__name__)


def consultar(url: str = "", timeout: float = TIMEOUT_SEGUNDOS) -> Decimal | None:
    """Devuelve la tasa publicada, o None si no se pudo obtener.

    `verify=False` a proposito: el certificado de bcv.org.ve esta firmado por
    una autoridad que Windows y Python no reconocen, y con la verificacion
    puesta la consulta falla siempre. Lo que viaja es un numero publico que el
    administrador ve en pantalla antes de guardarlo; no hay credenciales ni
    datos del negocio de por medio.
    """
    try:
        import requests  # import diferido: sin red, la app no lo necesita
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        respuesta = requests.get(
            url or URL_POR_DEFECTO, timeout=timeout, verify=False
        )
        respuesta.raise_for_status()
        return _extraer(respuesta.text)
    except Exception as error:  # red, DNS, certificado, HTML inesperado
        _bitacora.warning("No se pudo consultar la tasa del BCV: %s", error)
        return None


def _extraer(html: str) -> Decimal | None:
    coincidencia = _PATRON.search(html)
    if coincidencia is None:
        _bitacora.warning("La pagina del BCV no trajo el valor del dolar.")
        return None
    crudo = coincidencia.group(1).replace(".", "").replace(",", ".")
    try:
        valor = Decimal(crudo)
    except InvalidOperation:
        return None
    return valor if valor > 0 else None
