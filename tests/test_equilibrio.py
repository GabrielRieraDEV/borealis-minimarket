"""¿Los margenes cubren los gastos? (pedido del cliente tras la entrega).

El dominio se verifica con un ejemplo hecho a mano; el servicio, sobre la
base de demostracion, y la repeticion de gastos con sus dos negativas.
"""

from decimal import Decimal

import pytest

from minimarket.dominio.reportes import ALQUILER, Equilibrio, ResultadoPeriodo
from minimarket.servicios import gastos as servicio_gastos
from minimarket.servicios import reportes as servicio_reportes


def _equilibrio(ingreso, costo, perdidas, gastos, dia, dias_del_mes=30):
    return Equilibrio(
        resultado=ResultadoPeriodo(
            desde="2026-09-01",
            hasta=f"2026-09-{dia:02d}",
            ingreso_usd=Decimal(ingreso),
            costo_usd=Decimal(costo),
            perdidas_usd=Decimal(perdidas),
            gastos_usd=Decimal(gastos),
        ),
        dias_transcurridos=dia,
        dias_del_mes=dias_del_mes,
    )


def test_ejemplo_a_mano_que_cubre():
    """10 dias: 1.000 vendidos, 700 de costo, 20 de perdidas → 280 (28 %).

    A 30 dias: 840 de contribucion contra 600 de gastos → sobran 240.
    """
    e = _equilibrio("1000", "700", "20", "600", dia=10)
    assert e.contribucion_usd == Decimal("280")
    assert e.margen_bruto_pct == Decimal("28.00")
    assert e.ingreso_proyectado_usd == Decimal("3000.00")
    assert e.contribucion_proyectada_usd == Decimal("840.00")
    assert e.resultado_proyectado_usd == Decimal("240.00")
    assert e.cubre
    # Para empatar con 28 % alcanza vender 2.142,86 en el mes.
    assert e.ventas_necesarias_usd == Decimal("2142.86")
    # O, vendiendo los 3.000 proyectados, bastaria un 20 % de margen.
    assert e.margen_necesario_pct == Decimal("20.00")


def test_ejemplo_a_mano_que_no_cubre():
    """Mismas ventas, gastos de 1.000: faltan 160 y hay que vender 3.571,43."""
    e = _equilibrio("1000", "700", "20", "1000", dia=10)
    assert not e.cubre
    assert e.resultado_proyectado_usd == Decimal("-160.00")
    assert e.ventas_necesarias_usd == Decimal("3571.43")
    assert e.margen_necesario_pct == Decimal("33.33")


def test_sin_ventas_no_inventa_porcentajes():
    e = _equilibrio("0", "0", "0", "600", dia=3)
    assert e.margen_bruto_pct is None
    assert e.ventas_necesarias_usd is None
    assert e.margen_necesario_pct is None
    assert not e.cubre  # 0 de contribucion contra 600 de gastos


def test_el_servicio_arma_el_mes_hasta_hoy(conexion, categoria, general):
    from tests.conftest import alta, registrar_compra

    producto = alta(conexion, categoria, general, precio_venta_usd=Decimal("2.32"))
    registrar_compra(conexion, producto.id, Decimal("1.00"), fecha="2026-09-01")
    servicio_gastos.registrar(
        conexion, ALQUILER, "Alquiler", Decimal(300), periodo="2026-09"
    )
    e = servicio_reportes.equilibrio_del_mes(conexion, hoy="2026-09-10")
    assert (e.resultado.desde, e.resultado.hasta) == ("2026-09-01", "2026-09-10")
    assert (e.dias_transcurridos, e.dias_del_mes) == (10, 30)
    assert e.resultado.gastos_usd == Decimal(300)  # el mes entero, RN-29


def test_repetir_los_gastos_del_mes_anterior(conexion):
    servicio_gastos.registrar(conexion, ALQUILER, "Alquiler", Decimal(350), periodo="2026-08")
    servicio_gastos.registrar(conexion, ALQUILER, "Luz", Decimal(40), periodo="2026-08")

    copiados = servicio_gastos.repetir_mes_anterior(conexion, "2026-09")
    assert {(g.descripcion, g.monto_usd, g.periodo) for g in copiados} == {
        ("Alquiler", Decimal(350), "2026-09"),
        ("Luz", Decimal(40), "2026-09"),
    }
    assert servicio_gastos.total(conexion, "2026-09-01", "2026-09-30") == Decimal(390)

    with pytest.raises(servicio_gastos.ErrorGasto, match="ya tiene gastos"):
        servicio_gastos.repetir_mes_anterior(conexion, "2026-09")  # no duplica
    with pytest.raises(servicio_gastos.ErrorGasto, match="no tiene gastos"):
        servicio_gastos.repetir_mes_anterior(conexion, "2026-11")  # octubre vacio
    assert servicio_gastos._mes_anterior("2027-01") == "2026-12"
