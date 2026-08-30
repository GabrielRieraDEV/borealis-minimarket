"""Repositorio de alicuotas de IVA (RF-06).

Las tres alicuotas las siembra `esquema.sql`. Solo se leen: cambiar un
porcentaje es configuracion del negocio (RF-64, Fase 4), no alta de catalogo.
"""

import sqlite3

from minimarket.dominio.dinero import ESCALA_PORCENTAJE, desde_entero
from minimarket.dominio.producto import AlicuotaIva

_CAMPOS = "id, codigo, nombre, porcentaje, activo"


def _entidad(fila: sqlite3.Row) -> AlicuotaIva:
    return AlicuotaIva(
        id=fila["id"],
        codigo=fila["codigo"],
        nombre=fila["nombre"],
        porcentaje=desde_entero(fila["porcentaje"], ESCALA_PORCENTAJE),
        activo=bool(fila["activo"]),
    )


def listar(conexion: sqlite3.Connection) -> list[AlicuotaIva]:
    return [
        _entidad(f)
        for f in conexion.execute(
            f"SELECT {_CAMPOS} FROM alicuota_iva WHERE activo = 1 ORDER BY porcentaje"
        )
    ]


def obtener(conexion: sqlite3.Connection, alicuota_id: int) -> AlicuotaIva | None:
    fila = conexion.execute(
        f"SELECT {_CAMPOS} FROM alicuota_iva WHERE id = ?", (alicuota_id,)
    ).fetchone()
    return _entidad(fila) if fila else None


def obtener_por_codigo(conexion: sqlite3.Connection, codigo: str) -> AlicuotaIva | None:
    fila = conexion.execute(
        f"SELECT {_CAMPOS} FROM alicuota_iva WHERE codigo = ?", (codigo,)
    ).fetchone()
    return _entidad(fila) if fila else None
