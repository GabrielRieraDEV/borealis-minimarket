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
        [servicio_venta.pago(EFECTIVO, BS, Decimal("422.00"), TASA_DEL_EJEMPLO)],
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
        [servicio_venta.pago(PUNTO, BS, Decimal("1055.00"), TASA_DEL_EJEMPLO)],
    )

    resumen = servicio_caja.arqueo(conexion, sesion.id)
    assert resumen.ventas == 3
    assert resumen.total_vendido_usd == Decimal("10.00")
    assert resumen.linea(EFECTIVO, BS).esperado == Decimal("922.00")  # 500 + 2 × 211 al publico
    assert resumen.linea(EFECTIVO, USD).esperado == Decimal("23.00")  # 20 + 3
    assert resumen.linea(PUNTO, BS).esperado == Decimal("1055.00")
    assert resumen.linea(PUNTO, BS).conteo is None  # se concilia con el banco

    cierre = servicio_caja.cerrar(conexion, Decimal("922.00"), Decimal("23.00"))
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


# --- Vuelto en dolares, por pago movil o repartido (RN-23, 1.3.0) ------------


def _vender_con_vuelto(conexion, producto, cantidad, pagos, vueltos) -> Venta:
    from minimarket.dominio.venta import Venta as _Venta

    venta = _Venta(
        usuario_id=USUARIO_SEMILLA,
        tasa=TASA_DEL_EJEMPLO,
        lineas=[servicio_venta.nueva_linea(conexion, producto.id, cantidad)],
        pagos=pagos,
    )
    venta.vueltos = [venta.vuelto_declarado(m, mo, monto) for m, mo, monto in vueltos]
    return servicio_venta.registrar_venta(conexion, venta)


def test_el_vuelto_en_dolares_sale_de_la_gaveta_de_dolares(conexion, producto):
    """Producto de 1 USD × 4 = 4 USD; paga 5 USD; vuelto 1 USD en dolares."""
    cargar_tasa(conexion, servicio_tasa.hoy())
    sesion = servicio_caja.abrir(conexion, Decimal("500.00"), Decimal("20.00"))
    venta = _vender_con_vuelto(
        conexion, producto, Decimal(4),
        [servicio_venta.pago(EFECTIVO, USD, Decimal("5.00"), TASA_DEL_EJEMPLO)],
        [(EFECTIVO, USD, Decimal("1.00"))],
    )
    assert [(v.medio, v.moneda, v.monto) for v in venta.vueltos] == [
        (EFECTIVO, USD, Decimal("1.00"))
    ]
    resumen = servicio_caja.arqueo(conexion, sesion.id)
    assert resumen.linea(EFECTIVO, BS).esperado == Decimal("500.00")  # intacta
    assert resumen.linea(EFECTIVO, USD).esperado == Decimal("24.00")  # 20 + 5 − 1


def test_el_vuelto_por_pago_movil_no_toca_la_gaveta(conexion, producto):
    """Paga 5 USD en efectivo, el vuelto de 1 USD se le manda por pago movil."""
    from minimarket.dominio.venta import PAGO_MOVIL

    cargar_tasa(conexion, servicio_tasa.hoy())
    sesion = servicio_caja.abrir(conexion, Decimal("500.00"), Decimal("0.00"))
    _vender_con_vuelto(
        conexion, producto, Decimal(4),
        [servicio_venta.pago(EFECTIVO, USD, Decimal("5.00"), TASA_DEL_EJEMPLO)],
        [(PAGO_MOVIL, BS, Decimal("210.50"))],  # 1,00 USD a 210,50, exacto
    )
    resumen = servicio_caja.arqueo(conexion, sesion.id)
    assert resumen.linea(EFECTIVO, BS).esperado == Decimal("500.00")
    assert resumen.linea(EFECTIVO, USD).esperado == Decimal("5.00")
    # Salio de la cuenta: el renglon electronico queda en negativo.
    assert resumen.linea(PAGO_MOVIL, BS).esperado == Decimal("-210.50")


def test_el_vuelto_repartido_y_el_resto_en_bolivares(conexion, producto):
    """El ejemplo del cliente: parte en dolares y el resto en bolivares.

    Producto de 1 USD × 2; paga 20 USD; vuelto 18 USD. Declara 10 USD en
    efectivo; los 8 USD restantes salen en Bs: 1.684,00 → 1.684 al publico.
    """
    cargar_tasa(conexion, servicio_tasa.hoy())
    sesion = servicio_caja.abrir(conexion, Decimal("5000.00"), Decimal("0.00"))
    venta = _vender_con_vuelto(
        conexion, producto, Decimal(2),
        [servicio_venta.pago(EFECTIVO, USD, Decimal("20.00"), TASA_DEL_EJEMPLO)],
        [(EFECTIVO, USD, Decimal("10.00"))],
    )
    assert [(v.moneda, v.monto, v.monto_usd) for v in venta.vueltos] == [
        (USD, Decimal("10.00"), Decimal("10.00")),
        (BS, Decimal("1684.00"), Decimal("8.00")),
    ]
    resumen = servicio_caja.arqueo(conexion, sesion.id)
    assert resumen.linea(EFECTIVO, USD).esperado == Decimal("10.00")  # 20 − 10
    assert resumen.linea(EFECTIVO, BS).esperado == Decimal("3316.00")  # 5000 − 1684


def test_no_se_puede_declarar_mas_vuelto_del_que_hay(conexion, producto):
    cargar_tasa(conexion, servicio_tasa.hoy())
    servicio_caja.abrir(conexion)
    with pytest.raises(servicio_venta.ErrorVenta, match="supera el vuelto"):
        _vender_con_vuelto(
            conexion, producto, Decimal(4),
            [servicio_venta.pago(EFECTIVO, USD, Decimal("5.00"), TASA_DEL_EJEMPLO)],
            [(EFECTIVO, USD, Decimal("2.00"))],
        )
    with pytest.raises(servicio_venta.ErrorVenta, match="punto de venta"):
        _vender_con_vuelto(
            conexion, producto, Decimal(4),
            [servicio_venta.pago(EFECTIVO, USD, Decimal("5.00"), TASA_DEL_EJEMPLO)],
            [(PUNTO, USD, Decimal("1.00"))],
        )


def test_las_ventas_viejas_sin_vuelto_declarado_siguen_en_bolivares(conexion, producto):
    """Una venta anterior a 1.3.0 no tiene filas de vuelto: el arqueo la trata
    como siempre, efectivo en Bs redondeado al publico."""
    cargar_tasa(conexion, servicio_tasa.hoy())
    sesion = servicio_caja.abrir(conexion, Decimal("500.00"), Decimal("0.00"))
    venta = _vender(
        conexion, producto, Decimal(4),
        [servicio_venta.pago(EFECTIVO, USD, Decimal("5.00"), TASA_DEL_EJEMPLO)],
    )
    conexion.execute("DELETE FROM venta_vuelto WHERE venta_id = ?", (venta.id,))
    conexion.commit()
    resumen = servicio_caja.arqueo(conexion, sesion.id)
    assert resumen.linea(EFECTIVO, BS).esperado == Decimal("289.00")  # 500 − 211
