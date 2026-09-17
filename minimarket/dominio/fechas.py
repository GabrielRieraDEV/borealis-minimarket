"""Normalizacion de fechas escritas a mano.

Las fechas se guardan como texto ISO (RNF-14) porque asi ordenan y comparan
solas en SQLite. Quien las teclea escribe «01-02-2027», que en Venezuela es el
1 de febrero. Esta funcion es el unico lugar que traduce lo uno a lo otro.
"""

import re
from datetime import date

# Repetido, para que «01 - 02 - 2027» y «01/ 02/2027» sean la misma fecha:
# quien teclea separa como le queda comodo.
SEPARADORES = re.compile(r"[\s/.-]+")


def a_iso(texto: str) -> str | None:
    """Devuelve la fecha como AAAA-MM-DD, o None si no se entiende.

    Acepta AAAA-MM-DD y DD-MM-AAAA separado por guion, barra, punto o espacio,
    en cualquier combinacion. El año de dos digitos se rechaza: «01-02-27» no
    dice si es 1927 o 2027.
    """
    partes = SEPARADORES.split(texto.strip())
    if len(partes) != 3 or not all(p.isdigit() for p in partes):
        return None
    if len(partes[0]) == 4:
        anio, mes, dia = partes
    elif len(partes[2]) == 4:
        dia, mes, anio = partes
    else:
        return None
    try:
        return date(int(anio), int(mes), int(dia)).isoformat()
    except ValueError:  # 31 de febrero
        return None
