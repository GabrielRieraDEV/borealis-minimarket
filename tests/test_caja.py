"""Caja: RF-42 a RF-45 y RN-26."""

from decimal import Decimal

import pytest

from minimarket.dominio.venta import BS, EFECTIVO, PUNTO, USD, Venta
from minimarket.servicios import caja as servicio_caja
from minimarket.servicios import tasa as servicio_tasa
from minimarket.servicios import venta as servicio_venta
from tests.conftest import TASA_DEL_EJEMPLO, USUARIO_SEMILLA, alta, cargar_tasa
from tests.conftest import registrar_compra


@pytest.fixture
def producto(conexion, categoria, exento):
    """Exento a 1,00 USD con diez unidades en existencia."""
    creado = alta(
        conexion, categoria, exento, precio_venta_usd=Decimal("1.0000")
    )
    registrar_compra(
        conexion, creado.id, Decimal("0.5000"), presentaciones=Decimal(100)
    )
    return creado


def _vender(conexion, producto, cantidad, pagos) -> Venta:
    return servicio_venta.registrar_venta(
        conexion,
        Venta(
            usuario_id=USUARIO_SEMILLA,
            tasa=TASA_DEL_EJEMPLO,
            lineas=[servicio_venta.nueva_linea(conexion, producto.id, cantidad)],
            pagos=pagos,
        ),
    )


# --- Apertura (RF-42, RF-44) ------------------------------------------------


def test_sin_tasa_del_dia_no_se_abre_la_caja(conexion):
    """RN-04. La tasa no se hereda del dia anterior."""
    with pytest.raises(servicio_tasa.ErrorTasa):
        servicio_caja.abrir(conexion, Decimal(100), Decimal(20))


def test_una_sola_sesion_abierta_a_la_vez(conexion):
    """RF-42."""
    cargar_tasa(conexion, servicio_tasa.hoy())
    servicio_caja.abrir(conexion, Decimal(100), Decimal(20))
    with pytest.raises(servicio_caja.ErrorCaja, match="Ya hay una caja abierta"):
        servicio_caja.abrir(conexion, Decimal(50), Decimal(0))


def test_exigir_sesion_falla_con_la_caja_cerrada(conexion):
    """RF-44."""
    with pytest.raises(servicio_caja.ErrorCaja):
        servicio_caja.exigir_sesion(conexion)


# --- Secuencia completa apertura → ventas → cierre (RN-26) ------------------


def test_apertura_varias_ventas_y_cierre(conexion, producto):
    cargar_tasa(conexion, servicio_tasa.hoy())
    sesion = servicio_caja.abrir(conexion, Decimal("500.00"), Decimal("20.00"))

    _vender(  # 2,00 USD cobrados en bolivares
        conexion,
        producto,
        Decimal(2),
        [servicio_venta.pago(EFECTIVO, BS, Decimal("421.00"), TASA_DEL_EJEMPLO)],
    )
    _vender(  # 3,00 USD en efectivo, sin vuelto
        conexion,
        producto,
        Decimal(3),
        [servicio_venta.pago(EFECTIVO, USD, Decimal("3.00"), TASA_DEL_EJEMPLO)],
    )
    _vender(  # 5,00 USD por punto de venta, monto exacto
        conexion,
        producto,
        Decimal(5),
        [servicio_venta.pago(PUNTO, BS, Decimal("1052.50"), TASA_DEL_EJEMPLO)],
    )

    resumen = servicio_caja.arqueo(conexion, sesion.id)
    assert resumen.ventas == 3
    assert resumen.total_vendido_usd == Decimal("10.00")
    assert resumen.linea(EFECTIVO, BS).esperado == Decimal("921.00")  # 500 + 421
    assert resumen.linea(EFECTIVO, USD).esperado == Decimal("23.00")  # 20 + 3
    assert resumen.linea(PUNTO, BS).esperado == Decimal("1052.50")
    assert resumen.linea(PUNTO, BS).conteo is None  # se concilia con el banco

    cierre = servicio_caja.cerrar(conexion, Decimal("921.00"), Decimal("23.00"))
    assert cierre.linea(EFECTIVO, BS).diferencia == Decimal(0)
    assert cierre.linea(EFECTIVO, USD).diferencia == Decimal(0)
    assert cierre.sesion.estado == "CERRADA"
    assert cierre.sesion.fecha_cierre is not None
    assert servicio_caja.sesion_abierta(conexion) is None


def test_el_vuelto_sale_del_efectivo_en_bolivares(conexion, producto):
    """RN-23 + RN-26."""
    cargar_tasa(conexion, servicio_tasa.hoy())
    sesion = servicio_caja.abrir(conexion, Decimal("500.00"), Decimal("0.00"))
    venta = _vender(
        conexion,
        producto,
        Decimal(4),
        [servicio_venta.pago(EFECTIVO, USD, Decimal("5.00"), TASA_DEL_EJEMPLO)],
    )
    assert venta.vuelto_usd == Decimal("1.00")

    resumen = servicio_caja.arqueo(conexion, sesion.id)
    # 1,00 USD de vuelto son 210,50 Bs, que RN-10 redondea a 211,00 al
    # entregarlos. Eso es lo que salio de la gaveta.
    assert resumen.linea(EFECTIVO, BS).esperado == Decimal("289.00")
    assert resumen.linea(EFECTIVO, USD).esperado == Decimal("5.00")


def test_la_venta_anulada_no_entra_en_el_esperado(conexion, producto):
    """RN-25 + RN-26. El dinero se devolvio: no esta en la gaveta."""
    cargar_tasa(conexion, servicio_tasa.hoy())
    sesion = servicio_caja.abrir(conexion, Decimal("0.00"), Decimal("0.00"))
    venta = _vender(
        conexion,
        producto,
        Decimal(2),
        [servicio_venta.pago(EFECTIVO, USD, Decimal("2.00"), TASA_DEL_EJEMPLO)],
    )
    servicio_venta.anular_venta(conexion, venta.id, "Cliente se arrepintio")

    resumen = servicio_caja.arqueo(conexion, sesion.id)
    assert resumen.ventas == 0
    assert resumen.linea(EFECTIVO, USD).esperado == Decimal(0)


def test_una_diferencia_no_impide_cerrar_pero_queda_registrada(conexion, producto):
    """RN-26."""
    cargar_tasa(conexion, servicio_tasa.hoy())
    servicio_caja.abrir(conexion, Decimal("0.00"), Decimal("10.00"))
    _vender(
        conexion,
        producto,
        Decimal(2),
        [servicio_venta.pago(EFECTIVO, USD, Decimal("2.00"), TASA_DEL_EJEMPLO)],
    )
    cierre = servicio_caja.cerrar(conexion, Decimal("0.00"), Decimal("11.50"))
    assert cierre.linea(EFECTIVO, USD).esperado == Decimal("12.00")
    assert cierre.linea(EFECTIVO, USD).diferencia == Decimal("-0.50")
    assert cierre.sesion.diferencia_usd == Decimal("-0.50")


def test_tras_cerrar_se_puede_abrir_otra_sesion(conexion):
    cargar_tasa(conexion, servicio_tasa.hoy())
    primera = servicio_caja.abrir(conexion, Decimal(0), Decimal(0))
    servicio_caja.cerrar(conexion, Decimal(0), Decimal(0))
    segunda = servicio_caja.abrir(conexion, Decimal(0), Decimal(0))
    assert segunda.id != primera.id
    assert servicio_caja.sesion_abierta(conexion).id == segunda.id
