"""Repositorio de perdidas y sus motivos (RF-28 a RF-30, RF-32).

`motivo_perdida` entra aca y no en un modulo propio: son cuatro consultas
sobre una tabla de cinco filas que solo usa la perdida.

Escalas: cantidades x1.000, costos unitarios x10.000.
"""

import sqlite3

from minimarket.dominio.dinero import (
    ESCALA_CANTIDAD,
    ESCALA_PRECIO,
    a_entero,
    desde_entero,
)
from minimarket.dominio.inventario import MotivoPerdida, Perdida

_CAMPOS = """p.id, p.producto_id, p.lote_id, p.motivo_id, p.cantidad,
             p.costo_unitario_usd, p.fecha, p.usuario_id, p.observacion,
             pr.nombre AS producto, m.nombre AS motivo"""


def _entidad(fila: sqlite3.Row) -> Perdida:
    return Perdida(
        id=fila["id"],
        producto_id=fila["producto_id"],
        lote_id=fila["lote_id"],
        motivo_id=fila["motivo_id"],
        cantidad=desde_entero(fila["cantidad"], ESCALA_CANTIDAD),
        costo_unitario_usd=desde_entero(fila["costo_unitario_usd"], ESCALA_PRECIO),
        fecha=fila["fecha"],
        usuario_id=fila["usuario_id"],
        observacion=fila["observacion"],
        producto=fila["producto"],
        motivo=fila["motivo"],
    )


# --- Motivos (RF-29) --------------------------------------------------------


def listar_motivos(
    conexion: sqlite3.Connection, solo_activos: bool = True
) -> list[MotivoPerdida]:
    sql = "SELECT id, codigo, nombre, activo FROM motivo_perdida"
    if solo_activos:
        sql += " WHERE activo = 1"
    return [
        MotivoPerdida(
            id=f["id"],
            codigo=f["codigo"],
            nombre=f["nombre"],
            activo=bool(f["activo"]),
        )
        for f in conexion.execute(sql + " ORDER BY nombre")
    ]


def obtener_motivo(
    conexion: sqlite3.Connection, motivo_id: int
) -> MotivoPerdida | None:
    fila = conexion.execute(
        "SELECT id, codigo, nombre, activo FROM motivo_perdida WHERE id = ?",
        (motivo_id,),
    ).fetchone()
    return (
        MotivoPerdida(
            id=fila["id"],
            codigo=fila["codigo"],
            nombre=fila["nombre"],
            activo=bool(fila["activo"]),
        )
        if fila
        else None
    )


def motivo_por_codigo(
    conexion: sqlite3.Connection, codigo: str
) -> MotivoPerdida | None:
    """RF-32 usa el motivo VENCIDO, que siembra `esquema.sql`."""
    fila = conexion.execute(
        "SELECT id FROM motivo_perdida WHERE codigo = ?", (codigo,)
    ).fetchone()
    return obtener_motivo(conexion, fila[0]) if fila else None


def crear_motivo(conexion: sqlite3.Connection, motivo: MotivoPerdida) -> int:
    """RF-29. Los motivos son ampliables."""
    return conexion.execute(
        "INSERT INTO motivo_perdida (codigo, nombre, activo) VALUES (?, ?, ?)",
        (motivo.codigo, motivo.nombre, int(motivo.activo)),
    ).lastrowid


# --- Perdidas (RF-28, RF-30) ------------------------------------------------


def crear(conexion: sqlite3.Connection, perdida: Perdida) -> int:
    """RN-18. El costo unitario ya viene resuelto a la fecha de la perdida."""
    return conexion.execute(
        """INSERT INTO perdida (producto_id, lote_id, motivo_id, cantidad,
                                costo_unitario_usd, fecha, usuario_id,
                                observacion)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            perdida.producto_id,
            perdida.lote_id,
            perdida.motivo_id,
            a_entero(perdida.cantidad, ESCALA_CANTIDAD),
            a_entero(perdida.costo_unitario_usd, ESCALA_PRECIO),
            perdida.fecha,
            perdida.usuario_id,
            (perdida.observacion or "").strip() or None,
        ),
    ).lastrowid


def obtener(conexion: sqlite3.Connection, perdida_id: int) -> Perdida | None:
    fila = conexion.execute(
        f"""SELECT {_CAMPOS} FROM perdida p
              JOIN producto pr ON pr.id = p.producto_id
              JOIN motivo_perdida m ON m.id = p.motivo_id
             WHERE p.id = ?""",
        (perdida_id,),
    ).fetchone()
    return _entidad(fila) if fila else None


def listar(
    conexion: sqlite3.Connection,
    desde: str | None = None,
    hasta: str | None = None,
    motivo_id: int | None = None,
    limite: int = 500,
) -> list[Perdida]:
    """RF-53 en su version de detalle; el agrupado esta en `reportes`."""
    sql = f"""SELECT {_CAMPOS} FROM perdida p
                JOIN producto pr ON pr.id = p.producto_id
                JOIN motivo_perdida m ON m.id = p.motivo_id
               WHERE 1 = 1"""
    parametros: list[object] = []
    if desde:
        sql += " AND p.fecha >= ?"
        parametros.append(desde)
    if hasta:
        sql += " AND p.fecha <= ?"
        parametros.append(hasta)
    if motivo_id is not None:
        sql += " AND p.motivo_id = ?"
        parametros.append(motivo_id)
    sql += " ORDER BY p.fecha DESC, p.id DESC LIMIT ?"
    parametros.append(limite)
    return [_entidad(f) for f in conexion.execute(sql, parametros)]
