"""Ventas: RN-19 a RN-25, RF-27, RF-34 a RF-41, RF-44 y RF-45."""

from decimal import Decimal

import pytest

from minimarket.datos.repositorios import inventario as repo_inventario
from minimarket.datos.repositorios import venta as repo_venta
from minimarket.dominio.venta import (
    ANULADA,
    BS,
    COMPLETADA,
    EFECTIVO,
    PUNTO,
    USD,
    Cliente,
    LineaVenta,
    Venta,
)
from minimarket.servicios import caja as servicio_caja
from minimarket.servicios import venta as servicio_venta
from tests.conftest import TASA_DEL_EJEMPLO, USUARIO_SEMILLA, alta, cargar_tasa
from tests.conftest import registrar_compra

def _hoy() -> str:
    from minimarket.servicios import tasa as servicio_tasa

    return servicio_tasa.hoy()


@pytest.fixture
def caja_abierta(conexion):
    """RF-42. Tasa del dia cargada y caja abierta: lo minimo para vender."""
    cargar_tasa(conexion, _hoy())
    return servicio_caja.abrir(conexion, Decimal(100), Decimal(20))


def _venta(lineas, pagos=()) -> Venta:
    return Venta(
        usuario_id=USUARIO_SEMILLA,
        tasa=TASA_DEL_EJEMPLO,
        lineas=list(lineas),
        pagos=list(pagos),
    )


def _con_existencia(conexion, categoria, alicuota, precio, costo, **campos):
    """Producto con precio de venta y diez unidades compradas."""
    producto = alta(
        conexion, categoria, alicuota, precio_venta_usd=precio, **campos
    )
    registrar_compra(conexion, producto.id, costo, presentaciones=Decimal(10))
    return producto


# --- Ejemplo trabajado C (RN-20 a RN-23) ------------------------------------


def test_ejemplo_c_totales_de_la_venta():
    """Cuatro harinas exentas a 0,7800 y dos refrescos gravados a 0,8222."""
    venta = Venta(
        usuario_id=1,
        tasa=TASA_DEL_EJEMPLO,
        lineas=[
            LineaVenta(
                producto_id=1,
                descripcion="Harina de maiz",
                cantidad=Decimal(4),
                precio_unit_usd=Decimal("0.7800"),
                alicuota_pct=Decimal(0),
                costo_unitario_usd=Decimal("0.6000"),
            ),
            LineaVenta(
                producto_id=2,
                descripcion="Refresco 2 L",
                cantidad=Decimal(2),
                precio_unit_usd=Decimal("0.8222"),
                alicuota_pct=Decimal(16),
                costo_unitario_usd=Decimal("0.5000"),
            ),
        ],
    )
    assert venta.lineas[0].total_linea_usd == Decimal("3.12")
    assert venta.lineas[1].total_linea_usd == Decimal("1.64")
    assert venta.lineas[1].base_imponible_usd == Decimal("1.41")
    assert venta.lineas[1].iva_usd == Decimal("0.23")
    assert venta.exento_usd == Decimal("3.12")
    assert venta.base_imponible_usd == Decimal("1.41")
    assert venta.iva_usd == Decimal("0.23")
    assert venta.total_usd == Decimal("4.76")
    assert venta.total_bs == Decimal("1001.98")


def test_ejemplo_c_vuelto_en_bolivares():
    """RN-23. Cinco dolares en efectivo contra un total de 4,76."""
    venta = Venta(usuario_id=1, tasa=TASA_DEL_EJEMPLO)
    venta.lineas = [
        LineaVenta(1, "Harina", Decimal(4), Decimal("0.7800"), Decimal(0), Decimal(0)),
        LineaVenta(2, "Refresco", Decimal(2), Decimal("0.8222"), Decimal(16), Decimal(0)),
    ]
    venta.pagos = [
        servicio_venta.pago(EFECTIVO, USD, Decimal("5.00"), TASA_DEL_EJEMPLO)
    ]
    assert venta.pagado_usd == Decimal("5.00")
    assert venta.vuelto_usd == Decimal("0.24")
    assert venta.vuelto_bs() == Decimal("51.00")  # 50,52 redondeado hacia arriba
    assert venta.vuelto_admisible


def test_el_iva_no_se_recalcula_sobre_el_total_del_documento():
    """RN-20. La suma de las partes no coincide con el IVA del total."""
    venta = Venta(
        usuario_id=1,
        tasa=TASA_DEL_EJEMPLO,
        lineas=[
            LineaVenta(1, "Exento", Decimal(1), Decimal("10.00"), Decimal(0), Decimal(0)),
            LineaVenta(2, "Gravado", Decimal(1), Decimal("10.00"), Decimal(16), Decimal(0)),
        ],
    )
    assert venta.total_usd == Decimal("20.00")
    assert venta.exento_usd == Decimal("10.00")
    assert venta.iva_usd == Decimal("1.38")  # 10,00 − 8,62
    # Recalcular sobre el documento daria 2,76: por eso RN-20 lo prohibe.
    assert venta.iva_usd != Decimal("2.76")


def test_pago_en_bolivares_se_convierte_a_la_tasa_de_la_venta():
    """RN-22."""
    cobro = servicio_venta.pago(EFECTIVO, BS, Decimal("1001.98"), TASA_DEL_EJEMPLO)
    assert cobro.monto_usd == Decimal("4.76")


# --- Registro completo (RF-34 a RF-38, RF-45) -------------------------------


def test_registrar_venta_descuenta_inventario_y_guarda_pagos(
    conexion, categoria, general, caja_abierta
):
    producto = _con_existencia(
        conexion, categoria, general, Decimal("1.1600"), Decimal("0.5000")
    )
    venta = _venta(
        [servicio_venta.nueva_linea(conexion, producto.id, Decimal(2))],
        [servicio_venta.pago(EFECTIVO, USD, Decimal("2.32"), TASA_DEL_EJEMPLO)],
    )
    registrada = servicio_venta.registrar_venta(conexion, venta)

    assert registrada.numero == 1
    assert registrada.caja_sesion_id == caja_abierta.id  # RF-45
    assert repo_inventario.existencia(conexion, producto.id) == Decimal(8)

    guardada = repo_venta.obtener(conexion, registrada.id)
    assert guardada.total_usd == Decimal("2.32")
    assert guardada.base_imponible_usd == Decimal("2.00")
    assert guardada.iva_usd == Decimal("0.32")
    assert len(guardada.pagos) == 1
    assert guardada.pagos[0].monto_usd == Decimal("2.32")


def test_la_linea_guarda_copia_del_nombre_precio_y_alicuota(
    conexion, categoria, general, caja_abierta
):
    """RN-19. La venta no depende de la ficha del producto."""
    producto = _con_existencia(
        conexion, categoria, general, Decimal("1.1600"), Decimal("0.5000")
    )
    venta = servicio_venta.registrar_venta(
        conexion,
        _venta(
            [servicio_venta.nueva_linea(conexion, producto.id)],
            [servicio_venta.pago(EFECTIVO, USD, Decimal("1.16"), TASA_DEL_EJEMPLO)],
        ),
    )
    linea = repo_venta.obtener(conexion, venta.id).lineas[0]
    assert linea.descripcion == producto.nombre
    assert linea.precio_unit_usd == Decimal("1.1600")
    assert linea.alicuota_pct == Decimal(16)
    assert linea.costo_unitario_usd == Decimal("0.5000")


def test_cambiar_el_costo_no_altera_la_ganancia_de_una_venta_pasada(
    conexion, categoria, general, caja_abierta
):
    """RN-19, la regla mas importante del sistema desde lo contable."""
    producto = _con_existencia(
        conexion, categoria, general, Decimal("1.1600"), Decimal("0.5000")
    )
    venta = servicio_venta.registrar_venta(
        conexion,
        _venta(
            [servicio_venta.nueva_linea(conexion, producto.id, Decimal(2))],
            [servicio_venta.pago(EFECTIVO, USD, Decimal("2.32"), TASA_DEL_EJEMPLO)],
        ),
    )
    ganancia_original = repo_venta.obtener(conexion, venta.id).ganancia_usd
    assert ganancia_original == Decimal("1.00")  # 2,00 de base − 1,00 de costo

    # El proveedor sube el costo al doble despues de la venta.
    registrar_compra(
        conexion, producto.id, Decimal("1.0000"), fecha="2026-08-15",
        presentaciones=Decimal(10),
    )
    from minimarket.datos.repositorios import producto as repo_producto

    assert repo_producto.ultimo_costo(conexion, producto.id) == Decimal("1.0000")
    assert repo_venta.obtener(conexion, venta.id).ganancia_usd == ganancia_original


def test_numeros_correlativos_y_la_anulada_conserva_el_suyo(
    conexion, categoria, exento, caja_abierta
):
    """RN-24."""
    producto = _con_existencia(
        conexion, categoria, exento, Decimal("1.0000"), Decimal("0.5000")
    )

    def vender():
        return servicio_venta.registrar_venta(
            conexion,
            _venta(
                [servicio_venta.nueva_linea(conexion, producto.id)],
                [servicio_venta.pago(EFECTIVO, USD, Decimal("1.00"), TASA_DEL_EJEMPLO)],
            ),
        )

    primera, segunda = vender(), vender()
    assert (primera.numero, segunda.numero) == (1, 2)

    servicio_venta.anular_venta(conexion, segunda.id, "Error de carga")
    tercera = vender()
    assert tercera.numero == 3  # el 2 no se reutiliza
    assert repo_venta.obtener(conexion, segunda.id).numero == 2


# --- Cobro (RN-22, RN-23) ---------------------------------------------------


def test_no_se_confirma_la_venta_si_los_pagos_no_alcanzan(
    conexion, categoria, exento, caja_abierta
):
    """RN-22."""
    producto = _con_existencia(
        conexion, categoria, exento, Decimal("5.0000"), Decimal("1.0000")
    )
    venta = _venta(
        [servicio_venta.nueva_linea(conexion, producto.id)],
        [servicio_venta.pago(EFECTIVO, USD, Decimal("3.00"), TASA_DEL_EJEMPLO)],
    )
    with pytest.raises(servicio_venta.ErrorVenta, match="Faltan"):
        servicio_venta.registrar_venta(conexion, venta)
    assert repo_inventario.existencia(conexion, producto.id) == Decimal(10)


def test_el_excedente_por_punto_de_venta_se_rechaza(
    conexion, categoria, exento, caja_abierta
):
    """RN-23. Solo el efectivo genera vuelto."""
    producto = _con_existencia(
        conexion, categoria, exento, Decimal("5.0000"), Decimal("1.0000")
    )
    venta = _venta(
        [servicio_venta.nueva_linea(conexion, producto.id)],
        [servicio_venta.pago(PUNTO, BS, Decimal("2105.00"), TASA_DEL_EJEMPLO)],
    )
    with pytest.raises(servicio_venta.ErrorVenta, match="excedente"):
        servicio_venta.registrar_venta(conexion, venta)


def test_pago_mixto_efectivo_y_punto_con_vuelto_en_efectivo(
    conexion, categoria, exento, caja_abierta
):
    """RN-22 + RN-23: el vuelto sale del efectivo, no del punto."""
    producto = _con_existencia(
        conexion, categoria, exento, Decimal("10.0000"), Decimal("1.0000")
    )
    venta = _venta(
        [servicio_venta.nueva_linea(conexion, producto.id)],
        [
            servicio_venta.pago(PUNTO, BS, Decimal("1052.50"), TASA_DEL_EJEMPLO),
            servicio_venta.pago(EFECTIVO, USD, Decimal("6.00"), TASA_DEL_EJEMPLO),
        ],
    )
    registrada = servicio_venta.registrar_venta(conexion, venta)
    assert registrada.total_usd == Decimal("10.00")
    assert registrada.vuelto_usd == Decimal("1.00")


# --- Existencia (RF-27) -----------------------------------------------------


def test_no_se_vende_sin_existencia(conexion, categoria, exento, caja_abierta):
    """RF-27."""
    producto = _con_existencia(
        conexion, categoria, exento, Decimal("1.0000"), Decimal("0.5000")
    )
    venta = _venta(
        [servicio_venta.nueva_linea(conexion, producto.id, Decimal(15))],
        [servicio_venta.pago(EFECTIVO, USD, Decimal("15.00"), TASA_DEL_EJEMPLO)],
    )
    with pytest.raises(servicio_venta.ErrorVenta, match="existencia"):
        servicio_venta.registrar_venta(conexion, venta)


def test_el_administrador_puede_autorizar_la_venta_sin_existencia(
    conexion, categoria, exento, caja_abierta
):
    """RF-27. La existencia negativa se corrige despues con un ajuste."""
    producto = _con_existencia(
        conexion, categoria, exento, Decimal("1.0000"), Decimal("0.5000")
    )
    venta = _venta(
        [servicio_venta.nueva_linea(conexion, producto.id, Decimal(15))],
        [servicio_venta.pago(EFECTIVO, USD, Decimal("15.00"), TASA_DEL_EJEMPLO)],
    )
    servicio_venta.registrar_venta(conexion, venta, autorizado_por=USUARIO_SEMILLA)
    assert repo_inventario.existencia(conexion, producto.id) == Decimal(-5)


# --- Caja obligatoria (RF-44) -----------------------------------------------


def test_sin_caja_abierta_no_se_vende(conexion, categoria, exento):
    """RF-44."""
    cargar_tasa(conexion, _hoy())
    producto = _con_existencia(
        conexion, categoria, exento, Decimal("1.0000"), Decimal("0.5000")
    )
    venta = _venta(
        [servicio_venta.nueva_linea(conexion, producto.id)],
        [servicio_venta.pago(EFECTIVO, USD, Decimal("1.00"), TASA_DEL_EJEMPLO)],
    )
    with pytest.raises(servicio_caja.ErrorCaja, match="caja abierta"):
        servicio_venta.registrar_venta(conexion, venta)


# --- Anulacion (RF-41, RN-25) -----------------------------------------------


def test_anular_devuelve_la_mercancia_y_conserva_el_documento(
    conexion, categoria, exento, caja_abierta
):
    """RN-25."""
    producto = _con_existencia(
        conexion, categoria, exento, Decimal("1.0000"), Decimal("0.5000")
    )
    venta = servicio_venta.registrar_venta(
        conexion,
        _venta(
            [servicio_venta.nueva_linea(conexion, producto.id, Decimal(3))],
            [servicio_venta.pago(EFECTIVO, USD, Decimal("3.00"), TASA_DEL_EJEMPLO)],
        ),
    )
    assert repo_inventario.existencia(conexion, producto.id) == Decimal(7)

    servicio_venta.anular_venta(conexion, venta.id, "Producto devuelto")

    assert repo_inventario.existencia(conexion, producto.id) == Decimal(10)
    guardada = repo_venta.obtener(conexion, venta.id)
    assert guardada.estado == ANULADA
    assert guardada.motivo_anulacion == "Producto devuelto"
    assert len(guardada.lineas) == 1  # el detalle sigue ahi


def test_la_anulacion_conserva_el_costo_congelado(
    conexion, categoria, exento, caja_abierta
):
    """RN-25. El movimiento inverso usa el costo de la venta original."""
    producto = _con_existencia(
        conexion, categoria, exento, Decimal("1.0000"), Decimal("0.5000")
    )
    venta = servicio_venta.registrar_venta(
        conexion,
        _venta(
            [servicio_venta.nueva_linea(conexion, producto.id)],
            [servicio_venta.pago(EFECTIVO, USD, Decimal("1.00"), TASA_DEL_EJEMPLO)],
        ),
    )
    registrar_compra(
        conexion, producto.id, Decimal("9.9999"), fecha="2026-08-20",
        presentaciones=Decimal(1),
    )
    servicio_venta.anular_venta(conexion, venta.id, "Devolucion")

    inverso = [
        m
        for m in repo_inventario.movimientos_de(conexion, producto.id)
        if m.tipo == "ANULACION_VENTA"
    ][0]
    assert inverso.costo_unitario_usd == Decimal("0.5000")


def test_la_anulacion_exige_motivo(conexion, categoria, exento, caja_abierta):
    """RN-25."""
    producto = _con_existencia(
        conexion, categoria, exento, Decimal("1.0000"), Decimal("0.5000")
    )
    venta = servicio_venta.registrar_venta(
        conexion,
        _venta(
            [servicio_venta.nueva_linea(conexion, producto.id)],
            [servicio_venta.pago(EFECTIVO, USD, Decimal("1.00"), TASA_DEL_EJEMPLO)],
        ),
    )
    with pytest.raises(servicio_venta.ErrorVenta, match="motivo"):
        servicio_venta.anular_venta(conexion, venta.id, "   ")
    assert repo_venta.obtener(conexion, venta.id).estado == COMPLETADA


# --- Atomicidad (RNF-06) ----------------------------------------------------


def test_una_venta_interrumpida_no_deja_inventario_descontado(
    conexion, categoria, exento, caja_abierta, monkeypatch
):
    """RNF-06. El corte ocurre despues de descontar y antes de los pagos."""
    producto = _con_existencia(
        conexion, categoria, exento, Decimal("1.0000"), Decimal("0.5000")
    )

    def explotar(*_args, **_kwargs):
        raise RuntimeError("se corto la luz")

    monkeypatch.setattr(repo_venta, "registrar_pago", explotar)
    venta = _venta(
        [servicio_venta.nueva_linea(conexion, producto.id, Decimal(2))],
        [servicio_venta.pago(EFECTIVO, USD, Decimal("2.00"), TASA_DEL_EJEMPLO)],
    )
    with pytest.raises(RuntimeError):
        servicio_venta.registrar_venta(conexion, venta)

    assert repo_inventario.existencia(conexion, producto.id) == Decimal(10)
    assert repo_venta.listar(conexion) == []


# --- Cliente (RF-40) --------------------------------------------------------


def test_guardar_cliente_reutiliza_el_rif_existente(conexion):
    """RF-40."""
    primero = servicio_venta.guardar_cliente(
        conexion, Cliente(razon_social="Acme C.A.", rif="J-30012345-6", tipo="EMPRESA")
    )
    segundo = servicio_venta.guardar_cliente(
        conexion, Cliente(razon_social="Acme C.A.", rif="J-30012345-6", tipo="EMPRESA")
    )
    assert primero.id == segundo.id
    assert servicio_venta.cliente_por_rif(conexion, "J-30012345-6").id == primero.id
