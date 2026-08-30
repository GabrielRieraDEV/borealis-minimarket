"""Bitacora de operaciones sensibles (RF-59).

Anulaciones, ajustes de inventario, cambios de precio y modificaciones de
usuarios. Se escribe DENTRO de la transaccion de la operacion que la origina:
si la operacion se revierte, su asiento tampoco queda.

`datos_antes` y `datos_despues` son JSON de texto libre. No hay esquema fijo
porque cada operacion registra lo suyo, y el asiento se lee con ojos humanos.
"""

import json
import sqlite3
from dataclasses import dataclass

# `auditoria.accion`. Texto, no una tabla: son etiquetas, no entidades.
ANULACION_VENTA = "ANULACION_VENTA"
ANULACION_COMPRA = "ANULACION_COMPRA"
AJUSTE_INVENTARIO = "AJUSTE_INVENTARIO"
PERDIDA = "PERDIDA"
CAMBIO_PRECIO = "CAMBIO_PRECIO"
RECALCULO_PRECIOS = "RECALCULO_PRECIOS"
ALTA_USUARIO = "ALTA_USUARIO"
CAMBIO_USUARIO = "CAMBIO_USUARIO"
CAMBIO_CLAVE = "CAMBIO_CLAVE"
CAMBIO_CONFIGURACION = "CAMBIO_CONFIGURACION"
RESTAURACION = "RESTAURACION"


@dataclass(frozen=True)
class Asiento:
    """Una linea de la bitacora, ya lista para mostrar."""

    id: int
    usuario_id: int
    usuario: str
    accion: str
    entidad: str
    entidad_id: int | None
    datos_antes: str | None
    datos_despues: str | None
    fecha_hora: str


def _texto(datos: dict | None) -> str | None:
    # `default=str` deja pasar los Decimal sin convertirlos a float.
    return None if datos is None else json.dumps(datos, ensure_ascii=False, default=str)


def registrar(
    conexion: sqlite3.Connection,
    usuario_id: int,
    accion: str,
    entidad: str,
    entidad_id: int | None = None,
    antes: dict | None = None,
    despues: dict | None = None,
) -> int:
    """RF-59. Deja constancia de quien hizo que y sobre que.

    Se llama dentro de la transaccion de la operacion registrada.
    """
    return conexion.execute(
        """INSERT INTO auditoria (usuario_id, accion, entidad, entidad_id,
                                  datos_antes, datos_despues)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (usuario_id, accion, entidad, entidad_id, _texto(antes), _texto(despues)),
    ).lastrowid


def listar(
    conexion: sqlite3.Connection,
    desde: str | None = None,
    hasta: str | None = None,
    accion: str | None = None,
    limite: int = 300,
) -> list[Asiento]:
    """Lo ultimo primero: la consulta tipica es «que paso recien»."""
    sql = """SELECT a.id, a.usuario_id, u.usuario, a.accion, a.entidad,
                    a.entidad_id, a.datos_antes, a.datos_despues, a.fecha_hora
               FROM auditoria a JOIN usuario u ON u.id = a.usuario_id
              WHERE 1 = 1"""
    parametros: list[object] = []
    if desde:
        sql += " AND a.fecha_hora >= ?"
        parametros.append(desde)
    if hasta:
        sql += " AND a.fecha_hora <= ?"
        parametros.append(f"{hasta} 23:59:59")
    if accion:
        sql += " AND a.accion = ?"
        parametros.append(accion)
    sql += " ORDER BY a.id DESC LIMIT ?"
    parametros.append(limite)
    return [
        Asiento(
            id=f["id"],
            usuario_id=f["usuario_id"],
            usuario=f["usuario"],
            accion=f["accion"],
            entidad=f["entidad"],
            entidad_id=f["entidad_id"],
            datos_antes=f["datos_antes"],
            datos_despues=f["datos_despues"],
            fecha_hora=f["fecha_hora"],
        )
        for f in conexion.execute(sql, parametros)
    ]
