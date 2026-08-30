"""Perdidas, vencimientos y gastos (RF-28 a RF-33, RF-46, RN-17, RN-18)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from minimarket.datos.repositorios import inventario as repo_inventario
from minimarket.datos.repositorios import perdida as repo_perdida
from minimarket.dominio.inventario import PERDIDA, REF_PERDIDA
from minimarket.dominio.reportes import ALQUILER, SUELDOS
from minimarket.dominio.usuario import CAJERO, Usuario
from minimarket.infra import auditoria
from minimarket.servicios import cerrar_sesion, iniciar_sesion
from minimarket.servicios import gastos as servicio_gastos
from minimarket.servicios import inventario as servicio_inventario
from minimarket.servicios import perdidas as servicio_perdidas
from minimarket.servicios import usuarios as servicio_usuarios
from tests.conftest import alta, registrar_compra


@pytest.fixture(autouse=True)
def sin_sesion():
    cerrar_sesion()
    yield
    cerrar_sesion()


@pytest.fixture
def cajero(conexion) -> Usuario:
    identificador = servicio_usuarios.crear(
        conexion, Usuario(usuario="cajera", nombre="Cajera", rol=CAJERO), "clave1234"
    )
    return servicio_usuarios.obtener(conexion, identificador)


def motivo(conexion, codigo: str = "DANADO") -> int:
    return repo_perdida.motivo_por_codigo(conexion, codigo).id


def en_dias(cantidad: int) -> str:
    return (date.today() + timedelta(days=cantidad)).isoformat()


# --- RF-28 / RF-30 / RN-18 --------------------------------------------------


def test_rf28_la_perdida_descuenta_la_existencia(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento)
    registrar_compra(conexion, producto.id, Decimal("1.2000"), unidades=Decimal(20))

    perdida = servicio_perdidas.registrar(
        conexion, producto.id, Decimal(3), motivo(conexion), observacion="se cayo"
    )

    assert servicio_inventario.existencia(conexion, producto.id) == Decimal("17.000")
    assert perdida.cantidad == Decimal("3.000")
    assert perdida.motivo == "Producto danado o roto"
    assert perdida.observacion == "se cayo"


def test_rf30_la_perdida_se_valoriza_al_ultimo_costo(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento)
    registrar_compra(conexion, producto.id, Decimal("1.2000"), unidades=Decimal(20))

    perdida = servicio_perdidas.registrar(
        conexion, producto.id, Decimal(3), motivo(conexion)
    )
    assert perdida.costo_unitario_usd == Decimal("1.2000")
    assert perdida.costo_total_usd == Decimal("3.60")


def test_rn18_se_usa_el_costo_vigente_en_la_fecha_de_la_perdida(
    conexion, categoria, exento
):
    """Una perdida de marzo no se encarece por una compra de julio."""
    producto = alta(conexion, categoria, exento)
    registrar_compra(
        conexion,
        producto.id,
        Decimal("1.0000"),
        fecha="2026-03-01",
        unidades=Decimal(20),
    )
    registrar_compra(
        conexion,
        producto.id,
        Decimal("5.0000"),
        fecha="2026-07-01",
        unidades=Decimal(20),
    )

    vieja = servicio_perdidas.registrar(
        conexion, producto.id, Decimal(2), motivo(conexion), fecha="2026-03-15"
    )
    nueva = servicio_perdidas.registrar(
        conexion, producto.id, Decimal(2), motivo(conexion), fecha="2026-07-15"
    )
    assert vieja.costo_unitario_usd == Decimal("1.0000")
    assert nueva.costo_unitario_usd == Decimal("5.0000")


def test_el_producto_sin_compra_previa_se_valoriza_en_cero(
    conexion, categoria, exento
):
    producto = alta(conexion, categoria, exento)
    servicio_inventario.ajustar_por_conteo(
        conexion, producto.id, Decimal(5), "carga inicial"
    )
    perdida = servicio_perdidas.registrar(
        conexion, producto.id, Decimal(1), motivo(conexion)
    )
    assert perdida.costo_unitario_usd == Decimal(0)
    assert not perdida.determinable


def test_la_perdida_y_su_movimiento_viajan_juntos(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento)
    registrar_compra(conexion, producto.id, Decimal("1.2000"), unidades=Decimal(20))
    perdida = servicio_perdidas.registrar(
        conexion, producto.id, Decimal(3), motivo(conexion)
    )

    movimientos = repo_inventario.movimientos_de_referencia(
        conexion, REF_PERDIDA, perdida.id
    )
    assert len(movimientos) == 1
    assert movimientos[0].tipo == PERDIDA
    assert movimientos[0].cantidad == Decimal("-3.000")  # RN-12: salida
    assert movimientos[0].costo_unitario_usd == Decimal("1.2000")  # RN-14


def test_no_se_puede_perder_mas_de_lo_que_hay(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento)
    registrar_compra(conexion, producto.id, Decimal("1.0000"), unidades=Decimal(5))
    with pytest.raises(servicio_perdidas.ErrorPerdida, match="hay"):
        servicio_perdidas.registrar(conexion, producto.id, Decimal(9), motivo(conexion))
    assert servicio_inventario.existencia(conexion, producto.id) == Decimal("5.000")


def test_la_cantidad_y_el_motivo_se_validan(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento)
    registrar_compra(conexion, producto.id, Decimal("1.0000"), unidades=Decimal(5))
    with pytest.raises(servicio_perdidas.ErrorPerdida, match="mayor que cero"):
        servicio_perdidas.registrar(conexion, producto.id, Decimal(0), motivo(conexion))
    with pytest.raises(servicio_perdidas.ErrorPerdida, match="motivo"):
        servicio_perdidas.registrar(conexion, producto.id, Decimal(1), 999)


def test_rf58_el_cajero_no_registra_perdidas(conexion, categoria, exento, cajero):
    producto = alta(conexion, categoria, exento)
    registrar_compra(conexion, producto.id, Decimal("1.0000"), unidades=Decimal(5))
    iniciar_sesion(cajero)
    with pytest.raises(servicio_usuarios.ErrorPermiso, match="registrar perdidas"):
        servicio_perdidas.registrar(conexion, producto.id, Decimal(1), motivo(conexion))


def test_rf59_la_perdida_queda_en_la_bitacora(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento)
    registrar_compra(conexion, producto.id, Decimal("1.0000"), unidades=Decimal(5))
    servicio_perdidas.registrar(conexion, producto.id, Decimal(1), motivo(conexion))
    assert auditoria.listar(conexion, accion=auditoria.PERDIDA)


# --- RF-29 -----------------------------------------------------------------


def test_rf29_los_motivos_de_fabrica_estan_y_se_pueden_ampliar(conexion):
    codigos = {m.codigo for m in servicio_perdidas.motivos(conexion)}
    assert {
        "VENCIDO",
        "DANADO",
        "FALTANTE",
        "MERMA_CHARCUTERIA",
        "CONSUMO_PROPIO",
    } <= codigos

    servicio_perdidas.crear_motivo(conexion, "Robo en góndola")
    nuevos = {m.codigo: m.nombre for m in servicio_perdidas.motivos(conexion)}
    assert nuevos["ROBO_EN_GONDOLA"] == "Robo en góndola"


def test_el_motivo_repetido_se_rechaza(conexion):
    servicio_perdidas.crear_motivo(conexion, "Robo")
    with pytest.raises(servicio_perdidas.ErrorPerdida, match="Ya existe"):
        servicio_perdidas.crear_motivo(conexion, "robo")


# --- RF-31 / RF-32 / RF-33 / RN-15 / RN-17 ---------------------------------


@pytest.fixture
def con_lotes(conexion, categoria, exento):
    """Un producto con dos lotes: uno por vencer y uno lejano."""
    producto = alta(
        conexion, categoria, exento, maneja_vencimiento=True, dias_alerta_venc=15
    )
    registrar_compra(
        conexion,
        producto.id,
        Decimal("1.0000"),
        unidades=Decimal(10),
        fecha_vencimiento=en_dias(5),
    )
    registrar_compra(
        conexion,
        producto.id,
        Decimal("2.0000"),
        unidades=Decimal(10),
        fecha_vencimiento=en_dias(90),
    )
    return producto


def test_rf31_solo_alerta_el_lote_dentro_del_plazo(conexion, con_lotes):
    alerta = servicio_perdidas.proximos_a_vencer(conexion)
    assert len(alerta) == 1
    assert alerta[0].fecha_vencimiento == en_dias(5)
    assert alerta[0].dias_para_vencer() == 5
    assert not alerta[0].vencido()

    todos = servicio_perdidas.proximos_a_vencer(conexion, solo_alerta=False)
    assert len(todos) == 2


def test_rn17_el_plazo_es_el_configurado_por_producto(conexion, categoria, exento):
    lejos = alta(
        conexion,
        categoria,
        exento,
        nombre="Aviso corto",
        maneja_vencimiento=True,
        dias_alerta_venc=3,
    )
    registrar_compra(
        conexion, lejos.id, Decimal("1.0000"), fecha_vencimiento=en_dias(10)
    )
    assert servicio_perdidas.proximos_a_vencer(conexion) == []

    cerca = alta(
        conexion,
        categoria,
        exento,
        nombre="Aviso largo",
        maneja_vencimiento=True,
        dias_alerta_venc=30,
    )
    registrar_compra(
        conexion, cerca.id, Decimal("1.0000"), fecha_vencimiento=en_dias(10)
    )
    alerta = servicio_perdidas.proximos_a_vencer(conexion)
    assert [lote.producto for lote in alerta] == ["Aviso largo"]


def test_el_lote_ya_vencido_sigue_apareciendo_en_la_alerta(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento, maneja_vencimiento=True)
    registrar_compra(
        conexion, producto.id, Decimal("1.0000"), fecha_vencimiento=en_dias(-3)
    )
    alerta = servicio_perdidas.proximos_a_vencer(conexion)
    assert alerta[0].vencido()
    assert alerta[0].dias_para_vencer() == -3


def test_rf32_dar_de_baja_el_lote_lo_registra_como_perdida(conexion, con_lotes):
    lote = servicio_perdidas.proximos_a_vencer(conexion)[0]
    perdida = servicio_perdidas.dar_de_baja_lote(conexion, lote.lote_id)

    assert perdida.motivo == "Producto vencido"
    assert perdida.cantidad == Decimal("10.000")
    assert perdida.costo_unitario_usd == Decimal("2.0000")  # RN-07: el ultimo
    assert perdida.lote_id == lote.lote_id
    # El lote queda sin saldo y desaparece de la alerta; el otro sigue.
    assert repo_inventario.saldo_de_lote(conexion, lote.lote_id) == Decimal(0)
    assert servicio_perdidas.proximos_a_vencer(conexion) == []
    assert servicio_inventario.existencia(conexion, con_lotes.id) == Decimal("10.000")


def test_el_lote_vacio_no_se_da_de_baja_dos_veces(conexion, con_lotes):
    lote = servicio_perdidas.proximos_a_vencer(conexion)[0]
    servicio_perdidas.dar_de_baja_lote(conexion, lote.lote_id)
    with pytest.raises(servicio_perdidas.ErrorPerdida, match="existencia"):
        servicio_perdidas.dar_de_baja_lote(conexion, lote.lote_id)


def test_rn15_la_perdida_sin_lote_descuenta_el_mas_proximo_a_vencer(
    conexion, con_lotes
):
    """RF-33. La perdida es una salida y sigue la misma regla que la venta."""
    proximo = servicio_perdidas.proximos_a_vencer(conexion)[0]
    perdida = servicio_perdidas.registrar(
        conexion, con_lotes.id, Decimal(4), motivo(conexion)
    )
    assert perdida.lote_id == proximo.lote_id
    assert repo_inventario.saldo_de_lote(conexion, proximo.lote_id) == Decimal("6.000")


def test_la_salida_que_toca_dos_lotes_deja_la_cabecera_sin_lote(conexion, con_lotes):
    saldos = repo_inventario.saldos_por_lote(conexion, con_lotes.id)
    perdida = servicio_perdidas.registrar(
        conexion, con_lotes.id, Decimal(15), motivo(conexion)
    )
    assert perdida.lote_id is None  # el reparto real vive en los movimientos
    movimientos = repo_inventario.movimientos_de_referencia(
        conexion, REF_PERDIDA, perdida.id
    )
    assert sorted(m.cantidad for m in movimientos) == [
        Decimal("-10.000"),
        Decimal("-5.000"),
    ]
    assert {m.lote_id for m in movimientos} == {s.lote_id for s in saldos}


def test_el_lote_de_otro_producto_se_rechaza(conexion, con_lotes, categoria, exento):
    otro = alta(conexion, categoria, exento, nombre="Otro")
    registrar_compra(conexion, otro.id, Decimal("1.0000"), unidades=Decimal(5))
    lote = servicio_perdidas.proximos_a_vencer(conexion)[0]
    with pytest.raises(servicio_perdidas.ErrorPerdida, match="otro producto"):
        servicio_perdidas.registrar(
            conexion, otro.id, Decimal(1), motivo(conexion), lote_id=lote.lote_id
        )


# --- RF-46 ------------------------------------------------------------------


def test_rf46_el_gasto_se_registra_con_su_periodo(conexion):
    gasto = servicio_gastos.registrar(
        conexion,
        ALQUILER,
        "Alquiler del local",
        Decimal("350.00"),
        periodo="2026-08",
        fecha="2026-09-03",
    )
    assert gasto.periodo == "2026-08"  # el mes al que corresponde
    assert gasto.fecha == "2026-09-03"  # el dia en que se pago
    assert gasto.monto_usd == Decimal("350.00")


def test_el_periodo_por_defecto_es_el_mes_de_la_fecha(conexion):
    gasto = servicio_gastos.registrar(
        conexion, SUELDOS, "Sueldos", Decimal(200), fecha="2026-08-30"
    )
    assert gasto.periodo == "2026-08"


def test_el_gasto_valida_categoria_monto_y_periodo(conexion):
    with pytest.raises(servicio_gastos.ErrorGasto, match="categoria"):
        servicio_gastos.registrar(conexion, "CRIPTOMONEDAS", "x", Decimal(1))
    with pytest.raises(servicio_gastos.ErrorGasto, match="descripcion"):
        servicio_gastos.registrar(conexion, ALQUILER, "  ", Decimal(1))
    with pytest.raises(servicio_gastos.ErrorGasto, match="mayor que cero"):
        servicio_gastos.registrar(conexion, ALQUILER, "x", Decimal(0))
    with pytest.raises(servicio_gastos.ErrorGasto, match="AAAA-MM"):
        servicio_gastos.registrar(
            conexion, ALQUILER, "x", Decimal(1), periodo="2026-13"
        )


def test_rf58_el_cajero_no_registra_gastos(conexion, cajero):
    iniciar_sesion(cajero)
    with pytest.raises(servicio_usuarios.ErrorPermiso, match="gastos"):
        servicio_gastos.registrar(conexion, ALQUILER, "Alquiler", Decimal(100))


def test_rn29_los_gastos_del_rango_no_se_prorratean(conexion):
    servicio_gastos.registrar(conexion, ALQUILER, "Julio", Decimal(300), "2026-07")
    servicio_gastos.registrar(conexion, ALQUILER, "Agosto", Decimal(350), "2026-08")
    servicio_gastos.registrar(conexion, SUELDOS, "Agosto", Decimal(500), "2026-08")
    servicio_gastos.registrar(conexion, ALQUILER, "Septiembre", Decimal(400), "2026-09")

    # Un rango que arranca a mitad de agosto se lleva agosto entero.
    assert servicio_gastos.total(conexion, "2026-08-15", "2026-08-31") == Decimal(850)
    assert servicio_gastos.total(conexion, "2026-07-01", "2026-08-31") == Decimal(1150)
    assert servicio_gastos.total(conexion, "2026-01-01", "2026-06-30") == Decimal(0)
