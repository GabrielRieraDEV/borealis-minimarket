"""Compras, costos y proveedores (RF-14 a RF-21, RN-06, RN-07)."""

from decimal import Decimal

import pytest

from minimarket.datos.repositorios import compra as repo_compra
from minimarket.datos.repositorios import inventario as repo_inventario
from minimarket.datos.repositorios import producto as repo_producto
from minimarket.datos.repositorios import proveedor as repo_proveedor
from minimarket.dominio.compra import ANULADA, CONFIRMADA, Compra, LineaCompra, Proveedor
from minimarket.servicios import compras
from tests.conftest import (
    USUARIO_SEMILLA,
    alta,
    cargar_tasa,
    proveedor,
    registrar_compra,
)


def _compra(conexion, *lineas, fecha="2026-08-01") -> Compra:
    return Compra(
        proveedor_id=proveedor(conexion),
        fecha=fecha,
        usuario_id=USUARIO_SEMILLA,
        lineas=list(lineas),
    )


# --- RF-14: proveedores -----------------------------------------------------


def test_alta_y_modificacion_de_proveedor(conexion):
    identificador = compras.guardar_proveedor(
        conexion, Proveedor(nombre="Distribuidora", rif="J-12345678-9")
    )
    guardado = repo_proveedor.obtener(conexion, identificador)
    assert guardado.rif == "J-12345678-9"

    guardado.telefono = "0212-5551234"
    compras.guardar_proveedor(conexion, guardado)
    assert repo_proveedor.obtener(conexion, identificador).telefono == "0212-5551234"


def test_proveedor_sin_nombre_se_rechaza(conexion):
    with pytest.raises(compras.ErrorCompra):
        compras.guardar_proveedor(conexion, Proveedor(nombre="  "))


def test_la_baja_de_proveedor_es_logica(conexion):
    identificador = proveedor(conexion)
    compras.cambiar_estado_proveedor(conexion, identificador, activo=False)
    assert repo_proveedor.listar(conexion) == []
    assert repo_proveedor.obtener(conexion, identificador) is not None


# --- RN-06: costo unitario desde la presentacion ----------------------------


def test_ejemplo_a_bulto_de_veinte(conexion, categoria, exento):
    """Harina: bulto de 20 a 12,00 USD da 0,6000 USD por unidad."""
    producto = alta(conexion, categoria, exento, nombre="Harina de maiz")
    cargar_tasa(conexion)
    compras.registrar_compra(
        conexion,
        _compra(
            conexion,
            LineaCompra(producto.id, Decimal(1), Decimal(20), Decimal("12.0000")),
        ),
    )
    assert repo_producto.ultimo_costo(conexion, producto.id) == Decimal("0.6000")
    assert repo_inventario.existencia(conexion, producto.id) == Decimal("20.000")


def test_ejemplo_b_caja_de_veinticuatro(conexion, categoria, general):
    """Refresco: caja de 24 a 12,60 USD da 0,5250 USD por unidad."""
    producto = alta(conexion, categoria, general, nombre="Refresco en lata")
    cargar_tasa(conexion)
    compras.registrar_compra(
        conexion,
        _compra(
            conexion,
            LineaCompra(producto.id, Decimal(1), Decimal(24), Decimal("12.6000")),
        ),
    )
    assert repo_producto.ultimo_costo(conexion, producto.id) == Decimal("0.5250")


def test_rf17_el_mismo_producto_en_presentaciones_distintas(conexion, categoria, exento):
    """RF-17. La presentacion es de la linea, no de la ficha del producto."""
    producto = alta(conexion, categoria, exento, nombre="Harina")
    registrar_compra(
        conexion, producto.id, Decimal("0.6000"), fecha="2026-08-01", unidades=Decimal(20)
    )
    registrar_compra(
        conexion, producto.id, Decimal("0.5000"), fecha="2026-08-05", unidades=Decimal(24)
    )
    # RN-07: manda la compra confirmada mas reciente.
    assert repo_producto.ultimo_costo(conexion, producto.id) == Decimal("0.5000")
    assert repo_inventario.existencia(conexion, producto.id) == Decimal("44.000")


def test_unidades_por_presentacion_en_cero_se_rechaza(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento)
    cargar_tasa(conexion)
    with pytest.raises(compras.ErrorCompra, match="unidades por presentacion"):
        compras.registrar_compra(
            conexion,
            _compra(
                conexion,
                LineaCompra(producto.id, Decimal(1), Decimal(0), Decimal(10)),
            ),
        )


# --- RF-15, RF-18: la compra entera en una transaccion ----------------------


def test_la_compra_guarda_encabezado_detalle_y_movimientos(
    conexion, categoria, exento, general
):
    harina = alta(conexion, categoria, exento, nombre="Harina")
    refresco = alta(conexion, categoria, general, nombre="Refresco")
    cargar_tasa(conexion)

    resultado = compras.registrar_compra(
        conexion,
        _compra(
            conexion,
            LineaCompra(harina.id, Decimal(2), Decimal(20), Decimal("12.0000")),
            LineaCompra(refresco.id, Decimal(1), Decimal(24), Decimal("12.6000")),
        ),
    )
    guardada = repo_compra.obtener(conexion, resultado.compra_id)
    assert guardada.estado == CONFIRMADA
    assert guardada.total_usd == Decimal("36.60")  # 2x12,00 + 1x12,60
    assert guardada.saldo_pendiente_usd == Decimal("36.60")
    assert len(guardada.lineas) == 2
    assert repo_inventario.existencia(conexion, harina.id) == Decimal("40.000")
    assert repo_inventario.existencia(conexion, refresco.id) == Decimal("24.000")


def test_el_movimiento_congela_el_costo_de_la_compra(conexion, categoria, exento):
    """RN-14. El costo del movimiento no se recalcula nunca."""
    producto = alta(conexion, categoria, exento)
    registrar_compra(conexion, producto.id, Decimal("0.6000"), unidades=Decimal(20))
    registrar_compra(
        conexion,
        producto.id,
        Decimal("0.9000"),
        fecha="2026-08-10",
        unidades=Decimal(20),
    )
    costos = [m.costo_unitario_usd for m in repo_inventario.movimientos_de(conexion, producto.id)]
    assert sorted(costos) == [Decimal("0.6000"), Decimal("0.9000")]


def test_sin_tasa_del_dia_no_se_registra_la_compra(conexion, categoria, exento):
    """RN-04. La tasa no se hereda de ayer."""
    producto = alta(conexion, categoria, exento)
    with pytest.raises(compras.ErrorCompra, match="tasa de cambio"):
        compras.registrar_compra(
            conexion,
            _compra(
                conexion,
                LineaCompra(producto.id, Decimal(1), Decimal(1), Decimal(1)),
            ),
        )


def test_compra_sin_lineas_se_rechaza(conexion):
    cargar_tasa(conexion)
    with pytest.raises(compras.ErrorCompra, match="ninguna linea"):
        compras.registrar_compra(conexion, _compra(conexion))


def test_rollback_una_compra_que_falla_no_deja_nada(
    conexion, categoria, exento, monkeypatch
):
    """RNF-06. Si la segunda linea revienta, la primera tampoco queda."""
    harina = alta(conexion, categoria, exento, nombre="Harina")
    refresco = alta(conexion, categoria, exento, nombre="Refresco")
    cargar_tasa(conexion)

    original = repo_inventario.registrar_movimiento
    llamadas = {"n": 0}

    def falla_en_la_segunda(conexion, movimiento):
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            raise RuntimeError("corte de energia")
        return original(conexion, movimiento)

    monkeypatch.setattr(
        repo_inventario, "registrar_movimiento", falla_en_la_segunda
    )
    with pytest.raises(RuntimeError):
        compras.registrar_compra(
            conexion,
            _compra(
                conexion,
                LineaCompra(harina.id, Decimal(1), Decimal(20), Decimal("12.0000")),
                LineaCompra(refresco.id, Decimal(1), Decimal(24), Decimal("12.6000")),
            ),
        )

    assert repo_compra.listar(conexion) == []
    assert conexion.execute("SELECT COUNT(*) FROM compra_detalle").fetchone()[0] == 0
    assert repo_inventario.existencia(conexion, harina.id) == Decimal("0.000")
    assert repo_inventario.existencia(conexion, refresco.id) == Decimal("0.000")


# --- RF-21: lotes por vencimiento -------------------------------------------


def test_el_producto_con_vencimiento_crea_su_lote(conexion, categoria, exento):
    producto = alta(
        conexion, categoria, exento, nombre="Yogur", maneja_vencimiento=True
    )
    registrar_compra(
        conexion,
        producto.id,
        Decimal("1.0000"),
        unidades=Decimal(12),
        fecha_vencimiento="2026-09-15",
    )
    lotes = repo_inventario.lotes_de(conexion, producto.id)
    assert [lote.fecha_vencimiento for lote in lotes] == ["2026-09-15"]
    saldos = repo_inventario.saldos_por_lote(conexion, producto.id)
    assert saldos[0].cantidad == Decimal("12.000")


def test_dos_compras_con_el_mismo_vencimiento_comparten_lote(
    conexion, categoria, exento
):
    producto = alta(
        conexion, categoria, exento, nombre="Yogur", maneja_vencimiento=True
    )
    for fecha in ("2026-08-01", "2026-08-02"):
        registrar_compra(
            conexion,
            producto.id,
            Decimal("1.0000"),
            fecha=fecha,
            unidades=Decimal(10),
            fecha_vencimiento="2026-09-15",
        )
    assert len(repo_inventario.lotes_de(conexion, producto.id)) == 1
    assert repo_inventario.saldos_por_lote(conexion, producto.id)[0].cantidad == (
        Decimal("20.000")
    )


def test_sin_fecha_de_vencimiento_no_se_registra(conexion, categoria, exento):
    producto = alta(
        conexion, categoria, exento, nombre="Yogur", maneja_vencimiento=True
    )
    cargar_tasa(conexion)
    with pytest.raises(compras.ErrorCompra, match="vencimiento"):
        compras.registrar_compra(
            conexion,
            _compra(
                conexion,
                LineaCompra(producto.id, Decimal(1), Decimal(12), Decimal(12)),
            ),
        )


# --- RF-19: pagos a proveedores ---------------------------------------------


def test_pagos_parciales_bajan_el_saldo(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento)
    resultado = registrar_compra(
        conexion, producto.id, Decimal("0.6000"), unidades=Decimal(20)
    )
    compra_id = resultado.compra_id

    compras.registrar_pago(
        conexion, compra_id, Decimal("5.00"), "EFECTIVO", fecha="2026-08-01"
    )
    assert repo_compra.obtener(conexion, compra_id).saldo_pendiente_usd == Decimal(
        "7.00"
    )
    compras.registrar_pago(
        conexion, compra_id, Decimal("7.00"), "TRANSFERENCIA", fecha="2026-08-01"
    )
    assert repo_compra.obtener(conexion, compra_id).saldo_pendiente_usd == Decimal(
        "0.00"
    )
    assert len(repo_compra.pagos_de(conexion, compra_id)) == 2


def test_no_se_puede_pagar_mas_que_el_saldo(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento)
    resultado = registrar_compra(
        conexion, producto.id, Decimal("0.6000"), unidades=Decimal(20)
    )
    with pytest.raises(compras.ErrorCompra, match="supera el saldo"):
        compras.registrar_pago(
            conexion, resultado.compra_id, Decimal("13.00"), "EFECTIVO",
            fecha="2026-08-01",
        )


# --- RF-20: anulacion con movimientos inversos ------------------------------


def test_la_anulacion_invierte_el_inventario_y_conserva_el_registro(
    conexion, categoria, exento
):
    producto = alta(conexion, categoria, exento)
    resultado = registrar_compra(
        conexion, producto.id, Decimal("0.6000"), unidades=Decimal(20)
    )
    compras.anular_compra(conexion, resultado.compra_id, "Mercancia devuelta")

    anulada = repo_compra.obtener(conexion, resultado.compra_id)
    assert anulada is not None  # RN-13: nada se borra
    assert anulada.estado == ANULADA
    assert anulada.saldo_pendiente_usd == Decimal("0.00")
    assert repo_inventario.existencia(conexion, producto.id) == Decimal("0.000")
    assert len(repo_inventario.movimientos_de(conexion, producto.id)) == 2


def test_la_compra_anulada_sale_del_ultimo_costo(conexion, categoria, exento):
    """RN-07. Las compras anuladas se excluyen del costo vigente."""
    producto = alta(conexion, categoria, exento)
    registrar_compra(
        conexion, producto.id, Decimal("0.6000"), fecha="2026-08-01",
        unidades=Decimal(20),
    )
    segunda = registrar_compra(
        conexion, producto.id, Decimal("0.9000"), fecha="2026-08-10",
        unidades=Decimal(20),
    )
    assert repo_producto.ultimo_costo(conexion, producto.id) == Decimal("0.9000")

    compras.anular_compra(conexion, segunda.compra_id, "Cargada por error")
    assert repo_producto.ultimo_costo(conexion, producto.id) == Decimal("0.6000")


def test_no_se_anula_dos_veces(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento)
    resultado = registrar_compra(
        conexion, producto.id, Decimal("0.6000"), unidades=Decimal(20)
    )
    compras.anular_compra(conexion, resultado.compra_id, "Error")
    with pytest.raises(compras.ErrorCompra, match="ya fue anulada"):
        compras.anular_compra(conexion, resultado.compra_id, "Otra vez")


def test_no_se_anula_una_compra_con_pagos(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento)
    resultado = registrar_compra(
        conexion, producto.id, Decimal("0.6000"), unidades=Decimal(20)
    )
    compras.registrar_pago(
        conexion, resultado.compra_id, Decimal("1.00"), "EFECTIVO", fecha="2026-08-01"
    )
    with pytest.raises(compras.ErrorCompra, match="pagos registrados"):
        compras.anular_compra(conexion, resultado.compra_id, "Error")


def test_no_se_anula_si_la_mercancia_ya_salio(conexion, categoria, exento):
    from minimarket.servicios import inventario as servicio_inventario

    producto = alta(conexion, categoria, exento)
    resultado = registrar_compra(
        conexion, producto.id, Decimal("0.6000"), unidades=Decimal(20)
    )
    servicio_inventario.ajustar_por_conteo(
        conexion, producto.id, Decimal(5), "Conteo fisico"
    )
    with pytest.raises(compras.ErrorCompra, match="No se puede anular"):
        compras.anular_compra(conexion, resultado.compra_id, "Error")


# --- Aviso de margen tras cargar el costo -----------------------------------


def test_avisa_los_precios_que_quedaron_bajo_el_margen(conexion, categoria, exento):
    """El costo nuevo deja el precio corto: se informa, no se cambia solo."""
    producto = alta(
        conexion, categoria, exento, nombre="Harina", precio_venta_usd=Decimal("0.7000")
    )
    resultado = registrar_compra(
        conexion, producto.id, Decimal("0.6000"), unidades=Decimal(20)
    )
    assert len(resultado.avisos) == 1
    aviso = resultado.avisos[0]
    assert aviso.margen_objetivo == Decimal(30)  # el de la categoria
    assert aviso.margen_actual == Decimal("16.67")
    assert aviso.precio_sugerido_usd == Decimal("0.7800")
    # El precio guardado no se toco.
    assert repo_producto.obtener(conexion, producto.id).precio_venta_usd == Decimal(
        "0.7000"
    )


def test_no_avisa_cuando_el_margen_alcanza(conexion, categoria, exento):
    producto = alta(
        conexion, categoria, exento, nombre="Harina", precio_venta_usd=Decimal("0.7800")
    )
    resultado = registrar_compra(
        conexion, producto.id, Decimal("0.6000"), unidades=Decimal(20)
    )
    assert resultado.avisos == []
