"""¿Los margenes cubren los gastos? (pedido del cliente tras la entrega).

El dominio se verifica con un ejemplo hecho a mano; el servicio, sobre la
base de demostracion, y la repeticion de gastos con sus dos negativas.
"""

from decimal import Decimal


from minimarket.dominio.reportes import ALQUILER, Equilibrio, ResultadoPeriodo
from minimarket.servicios import gastos as servicio_gastos
from minimarket.servicios import reportes as servicio_reportes
from minimarket.servicios import tasa as servicio_tasa


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


def test_gastos_recurrentes_pesan_cada_mes_sin_cargarlos(conexion, categoria, general):
    """Un fijo desde septiembre y un 3 % de lo cobrado por punto."""
    from decimal import Decimal as D

    from minimarket.dominio.reportes import FIJO, PORCENTAJE, SERVICIOS
    from minimarket.dominio.venta import PUNTO, Venta
    from minimarket.servicios import caja as servicio_caja
    from minimarket.servicios import venta as servicio_venta
    from tests.conftest import alta, cargar_tasa, registrar_compra

    servicio_gastos.registrar_recurrente(
        conexion, ALQUILER, "Alquiler", FIJO, monto_usd=D(350), desde_periodo="2026-09"
    )
    servicio_gastos.registrar_recurrente(
        conexion, SERVICIOS, "Punto", PORCENTAJE, porcentaje=D(3), medio=PUNTO,
        desde_periodo="2026-09",
    )
    # Agosto: el alquiler todavia no regia.
    assert servicio_gastos.total(conexion, "2026-08-01", "2026-08-31") == 0
    # Septiembre sin ventas: solo el fijo.
    assert servicio_gastos.total(conexion, "2026-09-01", "2026-09-30") == D(350)

    # Una venta de 100 USD cobrada por punto, hoy → 3 USD de comision.
    producto = alta(conexion, categoria, general, precio_venta_usd=D(100))
    registrar_compra(conexion, producto.id, D(60))
    hoy = servicio_tasa.hoy()
    cargar_tasa(conexion, hoy)
    servicio_caja.abrir(conexion)
    venta = Venta(usuario_id=1, tasa=D(1))
    venta.lineas = [servicio_venta.nueva_linea(conexion, producto.id, D(1))]
    venta.pagos = [servicio_venta.pago(PUNTO, "USD", venta.total_usd, D(1))]
    servicio_venta.registrar_venta(conexion, venta)
    mes = hoy[:7]
    total = servicio_gastos.total(conexion, f"{mes}-01", f"{mes}-31")
    assert total == D(350) + D(3)
    origenes = {r.origen for r in servicio_gastos.desglose_del_mes(conexion, mes)}
    assert origenes == {"fijo mensual", "3 % de lo cobrado por punto"}

    # Dar de baja: sigue contando este mes, no el que viene.
    alquiler = servicio_gastos.listar_recurrentes(conexion)[0]
    servicio_gastos.dar_de_baja_recurrente(conexion, alquiler.id, mes)
    siguiente = f"{int(mes[:4]) + (mes[5:] == '12')}-{(int(mes[5:]) % 12) + 1:02d}"
    assert servicio_gastos.total(conexion, f"{siguiente}-01", f"{siguiente}-28") == 0


def _margen(ventas, fijos, variable, ganancia, origen="real"):
    from minimarket.dominio.reportes import MargenSugerido

    return MargenSugerido(
        ventas_mes_usd=Decimal(ventas),
        gastos_fijos_usd=Decimal(fijos),
        tasa_variable=Decimal(variable),
        ganancia_pct=Decimal(ganancia),
        origen_ventas=origen,
    )


def test_margen_sugerido_a_mano():
    """Vende 3.000 al mes, 600 de gastos fijos, 1 % de comisiones, quiere 10 %.

    Sobre ventas: piso 0,20 + 0,01 = 0,21 → sobre costo 26,58 %.
    Sugerido: 0,31 → 44,93 %. Con el doble de ventas el sugerido baja a 26,58 %.
    """
    m = _margen("3000", "600", "0.01", "10")
    assert m.piso_pct == Decimal("26.58")
    assert m.sugerido_pct == Decimal("44.93")
    assert m.sugerido_si_vendiera(Decimal(6000)) == Decimal("26.58")


def test_margen_sugerido_sin_salida():
    """Gastos por encima de las ventas: ningun margen alcanza."""
    m = _margen("500", "600", "0", "10")
    assert m.piso_pct is None and m.sugerido_pct is None
    assert _margen("0", "600", "0", "10").piso_pct is None


def test_el_servicio_proyecta_los_primeros_dias(conexion, categoria, general):
    from decimal import Decimal as D

    from minimarket.dominio.reportes import FIJO
    from minimarket.dominio.venta import EFECTIVO, Venta
    from minimarket.servicios import caja as servicio_caja
    from minimarket.servicios import venta as servicio_venta
    from tests.conftest import alta, cargar_tasa, registrar_compra

    hoy = servicio_tasa.hoy()
    assert servicio_reportes.margen_sugerido(conexion, hoy) is None  # nada aun

    servicio_gastos.registrar_recurrente(
        conexion, ALQUILER, "Alquiler", FIJO, monto_usd=D(300), desde_periodo=hoy[:7]
    )
    producto = alta(conexion, categoria, general, precio_venta_usd=D("116"))
    registrar_compra(conexion, producto.id, D(70))
    cargar_tasa(conexion, hoy)
    servicio_caja.abrir(conexion)
    venta = Venta(usuario_id=1, tasa=D(1))
    venta.lineas = [servicio_venta.nueva_linea(conexion, producto.id, D(1))]
    venta.pagos = [servicio_venta.pago(EFECTIVO, "USD", venta.total_usd, D(1))]
    servicio_venta.registrar_venta(conexion, venta)

    m = servicio_reportes.margen_sugerido(conexion, hoy)
    # Primera venta hoy: 1 dia de historia, 100 sin IVA → 3.000 al mes proyectados.
    assert (m.origen_ventas, m.dias_de_ventas) == ("proyectado", 1)
    assert m.ventas_mes_usd == D("3000.00")
    assert m.gastos_fijos_usd == D(300)
    assert m.ganancia_pct == D(10)  # el default de la configuracion
    assert m.piso_pct == D("11.11")  # 300/3000 = 0,10 → 0,10/0,90


def test_aplicar_el_margen_sube_solo_lo_que_esta_por_debajo(conexion, categoria, general):
    """Viveres tiene 30 %. Con piso 25 no se toca; con piso 40 sube y recalcula."""
    from decimal import Decimal as D

    from minimarket.servicios import catalogo
    from tests.conftest import alta, registrar_compra

    producto = alta(conexion, categoria, general, precio_venta_usd=D("1.00"))
    registrar_compra(conexion, producto.id, D("1.00"))

    plan = catalogo.previsualizar_margen(conexion, D(25))
    assert plan.categorias == [] and plan.productos == []
    assert len(plan.cambios) == 1  # el precio 1,00 no respeta ni el 30 % de la categoria

    plan = catalogo.previsualizar_margen(conexion, D(40))
    assert [(c.nombre, m) for c, m in plan.categorias] == [("Viveres", D(30))]
    (cambiado, precio), = plan.cambios
    assert precio == D("1.6240")  # 1,00 × 1,40 = 1,40 base; + 16 % IVA
    catalogo.aplicar_margen(conexion, plan)
    assert catalogo.listar_categorias(conexion)[0].margen_objetivo == D(40)
    assert catalogo.obtener_producto(conexion, producto.id).precio_venta_usd == D("1.6240")
    assert catalogo.margenes_actuales(conexion)[producto.id] == D("40.00")
