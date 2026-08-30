"""Inventario: kardex, alertas y ajustes (RF-22 a RF-26, RN-11 a RN-18)."""

from decimal import Decimal

import pytest

from minimarket.datos.conexion import transaccion
from minimarket.datos.repositorios import inventario as repo_inventario
from minimarket.dominio.inventario import (
    REF_VENTA,
    VENTA,
    Movimiento,
    SaldoLote,
    costo_unitario,
    en_alerta_vencimiento,
    existencia,
    hay_alerta_minimo,
    repartir_por_lote,
    valorizar,
)
from minimarket.servicios import compras, inventario
from tests.conftest import USUARIO_SEMILLA, alta, registrar_compra


def simular_venta(
    conexion, producto_id: int, cantidad: Decimal, costo: Decimal, lote_id=None
) -> None:
    """Salida de inventario sin la Fase 3, para probar el kardex de punta a punta."""
    with transaccion(conexion):
        repo_inventario.registrar_movimiento(
            conexion,
            Movimiento(
                producto_id=producto_id,
                lote_id=lote_id,
                tipo=VENTA,
                cantidad=-cantidad,  # RN-12: salida, negativa
                costo_unitario_usd=costo,
                referencia_tipo=REF_VENTA,
                referencia_id=1,
                usuario_id=USUARIO_SEMILLA,
            ),
        )


# --- Dominio puro -----------------------------------------------------------


def test_rn06_costo_unitario():
    assert costo_unitario(Decimal("12.0000"), Decimal(20)) == Decimal("0.6000")
    assert costo_unitario(Decimal("12.6000"), Decimal(24)) == Decimal("0.5250")


def test_rn06_sin_unidades_es_un_error():
    with pytest.raises(ValueError):
        costo_unitario(Decimal(10), Decimal(0))


def test_rn11_la_existencia_es_la_suma_de_los_movimientos():
    movimientos = [
        Movimiento(1, "COMPRA", Decimal(20), Decimal(1), "COMPRA", 1, 1),
        Movimiento(1, "VENTA", Decimal(-3), Decimal(1), "VENTA", 1, 1),
        Movimiento(1, "AJUSTE", Decimal("-0.500"), Decimal(1), "AJUSTE", 1, 1),
    ]
    assert existencia(movimientos) == Decimal("16.500")
    assert existencia([]) == Decimal("0.000")


def test_rn16_alerta_de_minimo():
    assert hay_alerta_minimo(Decimal(3), Decimal(5))
    assert hay_alerta_minimo(Decimal(5), Decimal(5))  # igual tambien alerta
    assert not hay_alerta_minimo(Decimal(6), Decimal(5))


def test_rn17_alerta_de_vencimiento():
    assert en_alerta_vencimiento("2026-09-10", 15, hoy="2026-09-01")
    assert not en_alerta_vencimiento("2026-09-20", 15, hoy="2026-09-01")
    assert en_alerta_vencimiento("2026-08-01", 15, hoy="2026-09-01")  # ya vencido


def test_rn18_valorizacion_de_una_salida():
    assert valorizar(Decimal(-3), Decimal("0.5250")) == Decimal("1.58")


# --- RN-15: seleccion de lote -----------------------------------------------


def test_rn15_descuenta_primero_el_vencimiento_mas_proximo():
    saldos = [
        SaldoLote(2, "2026-12-01", Decimal(10)),
        SaldoLote(1, "2026-09-15", Decimal(4)),
    ]
    assert repartir_por_lote(Decimal(3), saldos) == [(1, Decimal(3))]


def test_rn15_reparte_la_salida_entre_varios_lotes():
    saldos = [
        SaldoLote(1, "2026-09-15", Decimal(4)),
        SaldoLote(2, "2026-12-01", Decimal(10)),
    ]
    assert repartir_por_lote(Decimal(6), saldos) == [(1, Decimal(4)), (2, Decimal(2))]


def test_rn15_el_sobrante_sale_sin_lote():
    """RF-27 decide si la venta procede; el reparto solo informa el faltante."""
    saldos = [SaldoLote(1, "2026-09-15", Decimal(4))]
    assert repartir_por_lote(Decimal(7), saldos) == [
        (1, Decimal(4)),
        (None, Decimal(3)),
    ]


def test_rn15_ignora_lotes_agotados():
    saldos = [
        SaldoLote(1, "2026-09-15", Decimal(0)),
        SaldoLote(2, "2026-12-01", Decimal(5)),
    ]
    assert repartir_por_lote(Decimal(2), saldos) == [(2, Decimal(2))]


def test_salida_por_lotes_del_producto_sin_vencimiento(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento)
    registrar_compra(conexion, producto.id, Decimal("0.6000"), unidades=Decimal(20))
    assert inventario.salida_por_lotes(conexion, producto.id, Decimal(3)) == [
        (None, Decimal(3))
    ]


def test_salida_por_lotes_toma_el_lote_que_vence_antes(conexion, categoria, exento):
    producto = alta(
        conexion, categoria, exento, nombre="Yogur", maneja_vencimiento=True
    )
    registrar_compra(
        conexion, producto.id, Decimal(1), fecha="2026-08-01",
        unidades=Decimal(6), fecha_vencimiento="2026-12-01",
    )
    registrar_compra(
        conexion, producto.id, Decimal(1), fecha="2026-08-02",
        unidades=Decimal(4), fecha_vencimiento="2026-09-15",
    )
    reparto = inventario.salida_por_lotes(conexion, producto.id, Decimal(5))
    lotes = repo_inventario.lotes_de(conexion, producto.id)
    proximo = next(lote for lote in lotes if lote.fecha_vencimiento == "2026-09-15")
    assert reparto[0] == (proximo.id, Decimal("4.000"))
    assert reparto[1][1] == Decimal(1)


# --- RF-22 y RF-24: consulta de existencias y alertas -----------------------


def test_rf24_alerta_de_existencia_minima(conexion, categoria, exento):
    escaso = alta(
        conexion, categoria, exento, nombre="Harina",
        existencia_minima=Decimal(10),
    )
    sobrado = alta(
        conexion, categoria, exento, nombre="Refresco",
        existencia_minima=Decimal(5),
    )
    registrar_compra(conexion, escaso.id, Decimal("0.6000"), unidades=Decimal(8))
    registrar_compra(
        conexion, sobrado.id, Decimal("0.5000"), fecha="2026-08-02",
        unidades=Decimal(20),
    )

    nombres = [fila.nombre for fila in inventario.bajo_minimo(conexion)]
    assert nombres == ["Harina"]


def test_la_consulta_valoriza_al_ultimo_costo(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento, nombre="Harina")
    registrar_compra(conexion, producto.id, Decimal("0.6000"), unidades=Decimal(20))
    fila = inventario.consultar(conexion, texto="Harina")[0]
    assert fila.existencia == Decimal("20.000")
    assert fila.ultimo_costo == Decimal("0.6000")
    assert fila.valorizacion == Decimal("12.00")


def test_el_producto_sin_movimientos_aparece_en_cero(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento, nombre="Cafe")
    fila = inventario.consultar(conexion, texto="Cafe")[0]
    assert fila.producto_id == producto.id
    assert fila.existencia == Decimal("0.000")
    assert fila.ultimo_costo is None
    assert fila.valorizacion == Decimal("0.00")


# --- RF-25 y RF-26: ajuste por conteo fisico --------------------------------


def test_rf25_el_ajuste_registra_la_diferencia_como_movimiento(
    conexion, categoria, exento
):
    producto = alta(conexion, categoria, exento)
    registrar_compra(conexion, producto.id, Decimal("0.6000"), unidades=Decimal(20))

    diferencia = inventario.ajustar_por_conteo(
        conexion, producto.id, Decimal(18), "Faltante en el conteo mensual"
    )
    assert diferencia == Decimal(-2)
    assert repo_inventario.existencia(conexion, producto.id) == Decimal("18.000")

    fila = conexion.execute(
        """SELECT cantidad_sistema, cantidad_fisica, diferencia, motivo
             FROM ajuste_inventario WHERE producto_id = ?""",
        (producto.id,),
    ).fetchone()
    assert (fila[0], fila[1], fila[2]) == (20000, 18000, -2000)


def test_el_conteo_que_coincide_no_genera_movimiento(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento)
    registrar_compra(conexion, producto.id, Decimal("0.6000"), unidades=Decimal(20))

    assert inventario.ajustar_por_conteo(
        conexion, producto.id, Decimal(20), "Conteo mensual"
    ) == Decimal(0)
    assert len(repo_inventario.movimientos_de(conexion, producto.id)) == 1
    assert conexion.execute("SELECT COUNT(*) FROM ajuste_inventario").fetchone()[0] == 1


def test_rf26_el_ajuste_es_solo_del_administrador(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento)
    registrar_compra(conexion, producto.id, Decimal("0.6000"), unidades=Decimal(20))
    cajero = conexion.execute(
        """INSERT INTO usuario (usuario, nombre, hash_clave, rol)
           VALUES ('cajera', 'Cajera', '', 'CAJERO')"""
    ).lastrowid

    with pytest.raises(inventario.ErrorInventario, match="administrador"):
        inventario.ajustar_por_conteo(
            conexion, producto.id, Decimal(18), "Faltante", usuario_id=cajero
        )
    assert repo_inventario.existencia(conexion, producto.id) == Decimal("20.000")


def test_el_ajuste_exige_motivo(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento)
    with pytest.raises(inventario.ErrorInventario, match="motivo"):
        inventario.ajustar_por_conteo(conexion, producto.id, Decimal(1), "   ")


# --- RN-11 de punta a punta -------------------------------------------------


def test_la_existencia_coincide_con_la_suma_tras_toda_la_secuencia(
    conexion, categoria, exento
):
    """Compras, ventas, ajuste y anulacion: la vista y la suma no se separan."""
    producto = alta(conexion, categoria, exento, nombre="Harina")

    primera = registrar_compra(
        conexion, producto.id, Decimal("0.6000"), fecha="2026-08-01",
        unidades=Decimal(20),
    )
    registrar_compra(
        conexion, producto.id, Decimal("0.7000"), fecha="2026-08-05",
        unidades=Decimal(30),
    )
    simular_venta(conexion, producto.id, Decimal(12), Decimal("0.7000"))
    inventario.ajustar_por_conteo(
        conexion, producto.id, Decimal(36), "Faltante detectado en el conteo"
    )
    # La primera compra sigue entera en el deposito: se puede anular.
    compras.anular_compra(conexion, primera.compra_id, "Devuelta al proveedor")

    movimientos = repo_inventario.movimientos_de(conexion, producto.id)
    assert repo_inventario.existencia(conexion, producto.id) == existencia(movimientos)
    # 20 + 30 - 12 - 2 - 20
    assert repo_inventario.existencia(conexion, producto.id) == Decimal("16.000")
    assert len(movimientos) == 5
