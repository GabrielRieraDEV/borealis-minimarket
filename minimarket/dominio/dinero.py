"""Representación y redondeo de importes.

Única puerta del sistema para redondear y para convertir entre `Decimal` y el
entero escalado que guarda SQLite. Ningún otro módulo debe llamar a `quantize`
ni multiplicar por una escala a mano.

Ver seccion 5.2 de docs/requisitos.md y el principio de precision de
docs/reglas-de-negocio.md.
"""

from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

# Decimales de cada magnitud, segun la seccion 5.2 de docs/requisitos.md.
DECIMALES_PRECIO = 4  # precios y costos unitarios
DECIMALES_TOTAL = 2  # totales monetarios
DECIMALES_CANTIDAD = 3  # cantidades
DECIMALES_TASA = 6  # tasa de cambio
DECIMALES_PORCENTAJE = 2  # alicuotas y margenes

# Factor por el que se multiplica el Decimal para guardarlo como entero.
ESCALA_PRECIO = 10_000
ESCALA_TOTAL = 100
ESCALA_CANTIDAD = 1_000
ESCALA_TASA = 1_000_000
ESCALA_PORCENTAJE = 100


def redondear(valor: Decimal, decimales: int) -> Decimal:
    """Redondea medio hacia arriba. La unica funcion autorizada a redondear.

    El modo por defecto de Python es ROUND_HALF_EVEN (redondeo bancario) y
    contradice la especificacion, por eso ROUND_HALF_UP va explicito.
    """
    return valor.quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)


def a_entero(valor: Decimal, escala: int) -> int:
    """Convierte un Decimal al entero escalado que se guarda en SQLite."""
    return int(redondear(valor * escala, 0))


def desde_entero(entero: int, escala: int) -> Decimal:
    """Convierte el entero escalado leido de SQLite a Decimal."""
    return Decimal(entero) / escala


def convertir_a_bs(monto_usd: Decimal, tasa: Decimal) -> Decimal:
    """RN-03. Convierte un importe en dolares a bolivares a la tasa indicada."""
    return redondear(monto_usd * tasa, DECIMALES_TOTAL)


def redondear_comercial(monto_bs: Decimal, multiplo: Decimal = Decimal(1)) -> Decimal:
    """RN-10. Redondea el importe en bolivares al multiplo configurado.

    Siempre hacia arriba, para evitar la necesidad de sencillo. Se aplica al
    importe en bolivares que se muestra al publico, nunca al precio en dolares
    almacenado.
    """
    # ponytail: RN-10 solo define el sentido "hacia arriba", asi que no se lee
    # configuracion.precio_modo_redondeo. Si alguna vez hace falta otro sentido,
    # entra como parametro `modo` aca y en ningun otro lado.
    if multiplo <= 0:
        raise ValueError("El multiplo de redondeo debe ser mayor que cero.")
    multiplos = (monto_bs / multiplo).to_integral_value(rounding=ROUND_CEILING)
    return redondear(multiplos * multiplo, DECIMALES_TOTAL)
