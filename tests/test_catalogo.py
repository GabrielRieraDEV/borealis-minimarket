"""Catalogo: repositorios y servicios (RF-01 a RF-08)."""

from decimal import Decimal

import pytest

from minimarket.datos.repositorios import producto as repo_producto
from minimarket.dominio.producto import (
    Categoria,
    Producto,
    margen_aplicable,
    margen_resultante,
    precio_publico_bs,
    precio_sugerido,
)
from minimarket.servicios import catalogo
from tests.conftest import alta, registrar_compra


# --- RF-01: alta, modificacion y viaje de ida y vuelta de los importes -------


def test_alta_conserva_los_decimales_del_precio(conexion, categoria, general):
    identificador = catalogo.crear_producto(
        conexion,
        Producto(
            nombre="Refresco en lata",
            categoria_id=categoria.id,
            alicuota_iva_id=general.id,
            precio_venta_usd=Decimal("0.8222"),
            existencia_minima=Decimal("2.500"),
        ),
    )
    guardado = repo_producto.obtener(conexion, identificador)
    assert guardado.precio_venta_usd == Decimal("0.8222")
    assert guardado.existencia_minima == Decimal("2.500")
    assert guardado.margen_objetivo is None
    assert guardado.activo


def test_modificar_producto(conexion, categoria, general):
    producto = alta(conexion, categoria, general, nombre="Cafe")
    producto.nombre = "Cafe molido"
    producto.precio_venta_usd = Decimal("3.5000")
    catalogo.modificar_producto(conexion, producto)
    assert repo_producto.obtener(conexion, producto.id).nombre == "Cafe molido"


def test_nombre_vacio_se_rechaza(conexion, categoria, exento):
    with pytest.raises(catalogo.ErrorCatalogo):
        catalogo.crear_producto(
            conexion,
            Producto(nombre="   ", categoria_id=categoria.id, alicuota_iva_id=exento.id),
        )


def test_categoria_inexistente_se_rechaza(conexion, exento):
    with pytest.raises(catalogo.ErrorCatalogo):
        catalogo.crear_producto(
            conexion, Producto(nombre="X", categoria_id=999, alicuota_iva_id=exento.id)
        )


# --- RF-02: la baja es logica -----------------------------------------------


def test_baja_logica_no_borra_el_registro(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento, nombre="Harina")
    catalogo.desactivar_producto(conexion, producto.id)
    assert repo_producto.obtener(conexion, producto.id).activo is False
    assert catalogo.buscar(conexion, "Harina") == []
    assert len(catalogo.buscar(conexion, "Harina", solo_activos=False)) == 1
    catalogo.reactivar_producto(conexion, producto.id)
    assert len(catalogo.buscar(conexion, "Harina")) == 1


# --- RF-03: productos sin codigo de barras ----------------------------------


def test_varios_productos_sin_codigo_de_barras(conexion, categoria, exento):
    alta(conexion, categoria, exento, nombre="Tomate", codigo_barras=None)
    alta(conexion, categoria, exento, nombre="Cebolla", codigo_barras="")
    assert len(catalogo.buscar(conexion, "")) == 2


def test_codigo_de_barras_repetido_da_mensaje_claro(conexion, categoria, exento):
    alta(conexion, categoria, exento, nombre="Arroz", codigo_barras="7591234567890")
    with pytest.raises(catalogo.ErrorCatalogo, match="ya esta en uso"):
        catalogo.crear_producto(
            conexion,
            Producto(
                nombre="Arroz importado",
                categoria_id=categoria.id,
                alicuota_iva_id=exento.id,
                codigo_barras="7591234567890",
            ),
        )


# --- RF-04: busqueda ---------------------------------------------------------


def test_busqueda_por_codigo_exacto_y_por_nombre_parcial(conexion, categoria, exento):
    alta(conexion, categoria, exento, nombre="Harina de maiz", codigo_barras="111")
    alta(conexion, categoria, exento, nombre="Harina de trigo", codigo_barras="222")

    exacto = catalogo.buscar(conexion, "111")
    assert [p.nombre for p in exacto] == ["Harina de maiz"]

    parcial = catalogo.buscar(conexion, "harina")
    assert len(parcial) == 2

    assert catalogo.buscar(conexion, "maiz")[0].codigo_barras == "111"


def test_el_comodin_no_trae_el_catalogo_entero(conexion, categoria, exento):
    alta(conexion, categoria, exento, nombre="Harina")
    assert catalogo.buscar(conexion, "%") == []


# --- RF-05 / RN-09: margen aplicable ----------------------------------------


def test_el_producto_sin_margen_hereda_el_de_su_categoria():
    categoria = Categoria(1, "Viveres", Decimal(30))
    generico = Producto(nombre="X", categoria_id=1, alicuota_iva_id=1)
    propio = Producto(
        nombre="Y", categoria_id=1, alicuota_iva_id=1, margen_objetivo=Decimal(35)
    )
    assert margen_aplicable(generico, categoria) == Decimal(30)
    assert margen_aplicable(propio, categoria) == Decimal(35)


# --- RF-07: precio desde margen y margen desde precio ------------------------


def test_ejemplo_a_precio_desde_el_margen_de_la_categoria(conexion, categoria, exento):
    """Harina exenta, bulto de 20 a 12 USD, margen 30 %: 0,7800 USD."""
    producto = alta(conexion, categoria, exento, nombre="Harina de maiz")
    registrar_compra(conexion, producto.id, Decimal("0.6000"))

    assert catalogo.calcular_precio(conexion, producto) == Decimal("0.7800")


def test_ejemplo_b_precio_desde_el_margen_propio(conexion, categoria, general):
    """Refresco gravado 16 %, costo 0,5250 USD, margen 35 %: 0,8222 USD."""
    producto = alta(
        conexion,
        categoria,
        general,
        nombre="Refresco en lata",
        margen_objetivo=Decimal(35),
    )
    registrar_compra(conexion, producto.id, Decimal("0.5250"))

    assert catalogo.calcular_precio(conexion, producto) == Decimal("0.8222")


def test_margen_resultante_del_ejemplo_b(conexion, categoria, general):
    """RN-08 sobre la base imponible, no sobre el precio con IVA: 35,01 %."""
    producto = alta(
        conexion, categoria, general, precio_venta_usd=Decimal("0.8222")
    )
    registrar_compra(conexion, producto.id, Decimal("0.5250"))

    assert catalogo.calcular_margen(conexion, producto) == Decimal("35.01")


def test_sin_costo_el_margen_no_es_determinable(conexion, categoria, general):
    producto = alta(conexion, categoria, general, precio_venta_usd=Decimal("0.8222"))
    assert catalogo.calcular_precio(conexion, producto) is None
    assert catalogo.calcular_margen(conexion, producto) is None


def test_el_margen_no_se_calcula_sobre_el_precio_con_iva():
    """Confundir precio con base inflaria el margen a 56,61 %."""
    inflado = margen_resultante(Decimal("0.8222"), Decimal(0), Decimal("0.5250"))
    correcto = margen_resultante(Decimal("0.8222"), Decimal(16), Decimal("0.5250"))
    assert inflado == Decimal("56.61")
    assert correcto == Decimal("35.01")


# --- RN-10: precio al publico en bolivares ----------------------------------


def test_precio_al_publico_de_los_ejemplos_a_y_b():
    tasa = Decimal("210.500000")
    assert precio_publico_bs(Decimal("0.7800"), tasa) == Decimal("165.00")
    assert precio_publico_bs(Decimal("0.8222"), tasa) == Decimal("174.00")


# --- RF-08: recalculo en bloque ---------------------------------------------


def test_recalculo_en_bloque_de_una_categoria(conexion, categoria, exento, general):
    con_costo = alta(
        conexion, categoria, exento, nombre="Harina", precio_venta_usd=Decimal("0.5000")
    )
    registrar_compra(conexion, con_costo.id, Decimal("0.6000"))
    sin_costo = alta(
        conexion, categoria, general, nombre="Refresco", precio_venta_usd=Decimal(1)
    )

    cambios = catalogo.previsualizar_recalculo(conexion, categoria.id)
    assert [(p.id, nuevo) for p, nuevo in cambios] == [(con_costo.id, Decimal("0.7800"))]

    # Previsualizar no toca nada.
    assert repo_producto.obtener(conexion, con_costo.id).precio_venta_usd == Decimal(
        "0.5000"
    )

    assert catalogo.aplicar_recalculo(conexion, cambios) == 1
    assert repo_producto.obtener(conexion, con_costo.id).precio_venta_usd == Decimal(
        "0.7800"
    )
    # El producto sin costo de compra queda como estaba.
    assert repo_producto.obtener(conexion, sin_costo.id).precio_venta_usd == Decimal(1)


def test_el_recalculo_usa_el_margen_nuevo_de_la_categoria(
    conexion, categoria, general
):
    producto = alta(conexion, categoria, general, nombre="Refresco")
    registrar_compra(conexion, producto.id, Decimal("0.5250"))

    catalogo.guardar_categoria(
        conexion, Categoria(categoria.id, categoria.nombre, Decimal(35))
    )
    catalogo.aplicar_recalculo(
        conexion, catalogo.previsualizar_recalculo(conexion, categoria.id)
    )
    assert repo_producto.obtener(conexion, producto.id).precio_venta_usd == Decimal(
        "0.8222"
    )


def test_categoria_repetida_da_mensaje_claro(conexion, categoria):
    with pytest.raises(catalogo.ErrorCatalogo, match="Ya existe una categoria"):
        catalogo.guardar_categoria(conexion, Categoria(None, "Viveres", Decimal(30)))


def test_el_precio_sugerido_es_independiente_de_la_base_de_datos():
    """El dominio no necesita SQL para calcular: RN-09 puro."""
    categoria = Categoria(1, "Bebidas", Decimal(35))
    producto = Producto(nombre="Refresco", categoria_id=1, alicuota_iva_id=2)
    assert precio_sugerido(
        Decimal("0.5250"), producto, categoria, Decimal(16)
    ) == Decimal("0.8222")
