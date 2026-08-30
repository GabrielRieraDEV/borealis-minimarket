"""Base temporal y ayudantes compartidos por las pruebas."""

from decimal import Decimal

import pytest

from minimarket.datos.conexion import abrir, transaccion
from minimarket.datos.repositorios import alicuota as repo_alicuota
from minimarket.datos.repositorios import categoria as repo_categoria
from minimarket.datos.repositorios import producto as repo_producto
from minimarket.datos.repositorios import proveedor as repo_proveedor
from minimarket.dominio.compra import Compra, LineaCompra, Proveedor
from minimarket.dominio.producto import Categoria, Producto
from minimarket.servicios import compras as servicio_compras
from minimarket.servicios import tasa as servicio_tasa

USUARIO_SEMILLA = 1  # `admin`, sembrado por esquema.sql
TASA_DEL_EJEMPLO = Decimal("210.500000")


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


def cargar_tasa(
    conexion, fecha: str = "2026-08-01", valor: Decimal = TASA_DEL_EJEMPLO
) -> None:
    """RN-02. Sin tasa de esa fecha no se puede registrar una compra."""
    servicio_tasa.registrar_manual(conexion, valor, fecha)


def proveedor(conexion, nombre: str = "Distribuidora del Sur") -> int:
    existentes = repo_proveedor.listar(conexion)
    if existentes:
        return existentes[0].id
    return servicio_compras.guardar_proveedor(conexion, Proveedor(nombre=nombre))


def registrar_compra(
    conexion,
    producto_id: int,
    costo_unitario: Decimal,
    fecha: str = "2026-08-01",
    presentaciones: Decimal = Decimal(1),
    unidades: Decimal = Decimal(1),
    fecha_vencimiento: str | None = None,
):
    """Compra de una linea por el servicio real: deja costo (RN-07) y entrada.

    `costo_unitario` es lo que se quiere obtener por unidad; el costo de la
    presentacion se deduce multiplicando, para que RN-06 lo devuelva exacto.
    """
    cargar_tasa(conexion, fecha)
    return servicio_compras.registrar_compra(
        conexion,
        Compra(
            proveedor_id=proveedor(conexion),
            fecha=fecha,
            usuario_id=USUARIO_SEMILLA,
            lineas=[
                LineaCompra(
                    producto_id=producto_id,
                    cant_presentacion=presentaciones,
                    unid_x_presentacion=unidades,
                    costo_present_usd=costo_unitario * unidades,
                    fecha_vencimiento=fecha_vencimiento,
                )
            ],
        ),
    )
