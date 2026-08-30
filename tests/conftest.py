"""Base temporal y ayudantes compartidos por las pruebas de la Fase 1."""

from decimal import Decimal

import pytest

from minimarket.datos.conexion import abrir, transaccion
from minimarket.datos.repositorios import alicuota as repo_alicuota
from minimarket.datos.repositorios import categoria as repo_categoria
from minimarket.datos.repositorios import producto as repo_producto
from minimarket.dominio.dinero import ESCALA_PRECIO, ESCALA_TASA, a_entero
from minimarket.dominio.producto import Categoria, Producto

USUARIO_SEMILLA = 1  # `admin`, sembrado por esquema.sql


@pytest.fixture
def conexion(tmp_path):
    con = abrir(tmp_path / "prueba.db")
    yield con
    con.close()


@pytest.fixture
def categoria(conexion) -> Categoria:
    with transaccion(conexion):
        identificador = repo_categoria.crear(
            conexion, Categoria(None, "Viveres", Decimal(30))
        )
    return repo_categoria.obtener(conexion, identificador)


@pytest.fixture
def exento(conexion):
    return repo_alicuota.obtener_por_codigo(conexion, "EXENTO")


@pytest.fixture
def general(conexion):
    return repo_alicuota.obtener_por_codigo(conexion, "GENERAL")


def alta(conexion, categoria, alicuota, **campos) -> Producto:
    """Crea un producto con valores por defecto razonables y lo devuelve."""
    datos = {
        "nombre": "Producto de prueba",
        "categoria_id": categoria.id,
        "alicuota_iva_id": alicuota.id,
        "precio_venta_usd": Decimal("1.0000"),
    }
    datos.update(campos)
    with transaccion(conexion):
        identificador = repo_producto.crear(conexion, Producto(**datos))
    return repo_producto.obtener(conexion, identificador)


def registrar_compra(
    conexion,
    producto_id: int,
    costo_unitario: Decimal,
    fecha: str = "2026-08-01",
) -> None:
    """Compra minima para que exista un ultimo costo (RN-07).

    Las Fases 2 y 3 traen los repositorios de compra; aca alcanza con las filas
    que alimentan la vista `v_ultimo_costo`.
    """
    with transaccion(conexion):
        conexion.execute(
            "INSERT OR IGNORE INTO proveedor (id, nombre) VALUES (1, 'Proveedor')"
        )
        conexion.execute(
            """INSERT INTO tasa_cambio (fecha, valor, origen)
                    VALUES (?, ?, 'MANUAL')
               ON CONFLICT(fecha) DO UPDATE SET valor = excluded.valor""",
            (fecha, a_entero(Decimal("210.500000"), ESCALA_TASA)),
        )
        tasa_id = conexion.execute(
            "SELECT id FROM tasa_cambio WHERE fecha = ?", (fecha,)
        ).fetchone()[0]
        compra_id = conexion.execute(
            """INSERT INTO compra (proveedor_id, fecha, tasa_id, usuario_id)
               VALUES (1, ?, ?, ?)""",
            (fecha, tasa_id, USUARIO_SEMILLA),
        ).lastrowid
        conexion.execute(
            """INSERT INTO compra_detalle
                   (compra_id, producto_id, cant_presentacion, unid_x_presentacion,
                    cantidad_unidades, costo_present_usd, costo_unitario_usd)
               VALUES (?, ?, 1000, 1000, 1000, ?, ?)""",
            (
                compra_id,
                producto_id,
                a_entero(costo_unitario, ESCALA_PRECIO),
                a_entero(costo_unitario, ESCALA_PRECIO),
            ),
        )
