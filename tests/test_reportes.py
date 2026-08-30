"""Reportes del negocio (RF-47 a RF-55 y RN-27 a RN-31)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from minimarket.datos.repositorios import perdida as repo_perdida
from minimarket.dominio.dinero import convertir_a_bs
from minimarket.dominio.reportes import ALQUILER
from minimarket.dominio.usuario import CAJERO, Usuario
from minimarket.dominio.venta import EFECTIVO, PUNTO, Venta
from minimarket.servicios import caja as servicio_caja
from minimarket.servicios import cerrar_sesion, iniciar_sesion
from minimarket.servicios import gastos as servicio_gastos
from minimarket.servicios import perdidas as servicio_perdidas
from minimarket.servicios import usuarios as servicio_usuarios
from minimarket.servicios import inventario as servicio_inventario
from minimarket.servicios import reportes as servicio_reportes
from minimarket.servicios import tasa as servicio_tasa
from minimarket.servicios import venta as servicio_venta
from tests.conftest import (
    TASA_DEL_EJEMPLO,
    USUARIO_SEMILLA,
    alta,
    cargar_tasa,
    registrar_compra,
)

@pytest.fixture(autouse=True)
def sin_sesion():
    cerrar_sesion()
    yield
    cerrar_sesion()


def vender(conexion, producto_id, cantidad, pagos):
    """Registra una venta con los pagos indicados como (medio, moneda, monto)."""
    venta = Venta(usuario_id=USUARIO_SEMILLA, tasa=Decimal(0))
    venta.lineas = [servicio_venta.nueva_linea(conexion, producto_id, cantidad)]
    venta.pagos = [
        servicio_venta.pago(medio, moneda, monto, TASA_DEL_EJEMPLO)
        for medio, moneda, monto in pagos
    ]
    return servicio_venta.registrar_venta(conexion, venta)


@pytest.fixture
def dia_de_ventas(conexion, categoria, exento, general):
    """Dos productos con costo, la caja abierta y tres ventas del dia."""
    cargar_tasa(conexion, servicio_tasa.hoy())
    arroz = alta(
        conexion,
        categoria,
        exento,
        nombre="Arroz",
        precio_venta_usd=Decimal("2.0000"),
    )
    jabon = alta(
        conexion,
        categoria,
        general,
        nombre="Jabon",
        precio_venta_usd=Decimal("1.1600"),
    )
    registrar_compra(conexion, arroz.id, Decimal("1.2000"), unidades=Decimal(50))
    registrar_compra(conexion, jabon.id, Decimal("0.5000"), unidades=Decimal(50))
    servicio_caja.abrir(conexion)
    vender(conexion, arroz.id, Decimal(3), [(EFECTIVO, "USD", Decimal(6))])
    vender(conexion, jabon.id, Decimal(2), [(PUNTO, "BS", Decimal("488.36"))])
    anulada = vender(conexion, arroz.id, Decimal(1), [(EFECTIVO, "USD", Decimal(2))])
    servicio_venta.anular_venta(conexion, anulada.id, "prueba")
    return {"arroz": arroz, "jabon": jabon, "anulada": anulada}


def rango():
    hoy = servicio_tasa.hoy()
    return hoy, hoy


# --- RF-48 ------------------------------------------------------------------


def test_rf48_ventas_del_periodo_con_totales_por_medio(conexion, dia_de_ventas):
    desde, hasta = rango()
    resumen = servicio_reportes.ventas_por_periodo(conexion, desde, hasta)

    assert resumen.cantidad == 2  # la anulada no cuenta (RN-25)
    assert resumen.exento_usd == Decimal("6.00")  # 3 arroz x 2,00
    assert resumen.base_imponible_usd == Decimal("2.00")  # 2,32 / 1,16
    assert resumen.iva_usd == Decimal("0.32")
    assert resumen.total_usd == Decimal("8.32")

    por_medio = {(t.medio, t.moneda): t for t in resumen.por_medio}
    assert por_medio[(EFECTIVO, "USD")].monto == Decimal("6.00")
    assert por_medio[(PUNTO, "BS")].monto == Decimal("488.36")


# --- RF-49 / RN-30 ----------------------------------------------------------


def test_rf49_inventario_valorizado_al_ultimo_costo(conexion, dia_de_ventas):
    valorizado = servicio_reportes.inventario_valorizado(conexion)
    por_nombre = {f.nombre: f for f in valorizado.filas}

    # 50 compradas − 3 vendidas − 1 devuelta por la anulacion = 47 de arroz.
    assert por_nombre["Arroz"].existencia == Decimal("47.000")
    assert por_nombre["Arroz"].valorizacion == Decimal("56.40")  # 47 x 1,20
    assert por_nombre["Jabon"].valorizacion == Decimal("24.00")  # 48 x 0,50
    assert valorizado.total_usd == Decimal("80.40")


# --- RF-50 / RN-27 / RN-28 --------------------------------------------------


def test_rf50_ganancia_por_producto_usa_el_costo_congelado(conexion, dia_de_ventas):
    desde, hasta = rango()
    filas = {
        f.nombre: f
        for f in servicio_reportes.ganancia_por_producto(conexion, desde, hasta)
    }

    arroz = filas["Arroz"]
    assert arroz.cantidad == Decimal("3.000")
    assert arroz.ingreso_usd == Decimal("6.00")  # exento: base = total
    assert arroz.costo_usd == Decimal("3.60")  # RN-27: 3 x 1,20
    assert arroz.ganancia_usd == Decimal("2.40")  # RN-28
    assert arroz.margen_pct == Decimal("40.00")

    jabon = filas["Jabon"]
    assert jabon.ingreso_usd == Decimal("2.00")  # sin IVA: no es ingreso
    assert jabon.costo_usd == Decimal("1.00")
    assert jabon.ganancia_usd == Decimal("1.00")


def test_rn19_cambiar_el_costo_hoy_no_mueve_la_ganancia_de_ayer(
    conexion, dia_de_ventas
):
    desde, hasta = rango()
    antes = servicio_reportes.ganancia_por_producto(conexion, desde, hasta)
    ganancia_antes = {f.nombre: f.ganancia_usd for f in antes}

    # Una compra nueva mucho mas cara cambia el ultimo costo, no las ventas ya
    # registradas.
    registrar_compra(
        conexion,
        dia_de_ventas["arroz"].id,
        Decimal("9.0000"),
        fecha=servicio_tasa.hoy(),
    )
    despues = servicio_reportes.ganancia_por_producto(conexion, desde, hasta)
    assert {f.nombre: f.ganancia_usd for f in despues} == ganancia_antes


def test_el_producto_sin_costo_informa_margen_no_determinable(
    conexion, categoria, exento
):
    """Caso limite de las reglas: vendido antes de su primera compra."""
    cargar_tasa(conexion, servicio_tasa.hoy())
    producto = alta(conexion, categoria, exento, precio_venta_usd=Decimal("2.0000"))
    # Existencia sin compra detras: la carga un ajuste, que no deja costo.
    servicio_inventario.ajustar_por_conteo(
        conexion, producto.id, Decimal(5), "carga inicial"
    )
    servicio_caja.abrir(conexion)
    vender(
        conexion,
        producto.id,
        Decimal(1),
        [(EFECTIVO, "USD", Decimal(2))],
    )
    desde, hasta = rango()
    fila = servicio_reportes.ganancia_por_producto(conexion, desde, hasta)[0]
    assert fila.costo_usd == Decimal("0.00")
    assert not fila.determinable
    assert fila.margen_pct is None


def test_la_ganancia_por_categoria_suma_lo_mismo_que_por_producto(
    conexion, dia_de_ventas
):
    desde, hasta = rango()
    por_producto = servicio_reportes.ganancia_por_producto(conexion, desde, hasta)
    por_categoria = servicio_reportes.ganancia_por_categoria(conexion, desde, hasta)
    assert sum(f.ganancia_usd for f in por_categoria) == sum(
        f.ganancia_usd for f in por_producto
    )
    assert len(por_categoria) == 1  # las dos son de «Viveres»


# --- RF-51 ------------------------------------------------------------------


def test_rf51_el_cierre_de_caja_reporta_lo_esperado_por_medio(conexion, dia_de_ventas):
    sesion = servicio_caja.sesion_abierta(conexion)
    resumen = servicio_reportes.cierre_de_caja(conexion, sesion.id)
    assert resumen.linea(EFECTIVO, "USD").esperado == Decimal("6.00")
    assert resumen.linea(PUNTO, "BS").esperado == Decimal("488.36")
    assert resumen.ventas == 2


# --- RF-52 / RN-31 ----------------------------------------------------------


def test_rf52_el_libro_cuadra_con_las_ventas_del_periodo(conexion, dia_de_ventas):
    desde, hasta = rango()
    libro = servicio_reportes.libro_de_ventas(conexion, desde, hasta)
    resumen = servicio_reportes.ventas_por_periodo(conexion, desde, hasta)

    assert len(libro.filas) == 3  # incluye la anulada
    totales = libro.totales
    # RN-31: cada venta a SU tasa. Como todas son de hoy, el total en bolivares
    # tiene que coincidir con convertir el total en dolares del periodo.
    assert totales.exento_bs == convertir_a_bs(
        resumen.exento_usd, TASA_DEL_EJEMPLO
    )
    assert totales.base_imponible_bs == convertir_a_bs(
        resumen.base_imponible_usd, TASA_DEL_EJEMPLO
    )
    assert totales.iva_bs == convertir_a_bs(resumen.iva_usd, TASA_DEL_EJEMPLO)
    assert totales.total_bs == convertir_a_bs(resumen.total_usd, TASA_DEL_EJEMPLO)


def test_rn31_la_venta_anulada_figura_en_cero_y_marcada(conexion, dia_de_ventas):
    desde, hasta = rango()
    libro = servicio_reportes.libro_de_ventas(conexion, desde, hasta)
    anulada = next(
        f for f in libro.filas if f.numero == dia_de_ventas["anulada"].numero
    )
    assert anulada.condicion == "ANULADA"
    assert anulada.total_bs == Decimal(0)
    assert anulada.exento_bs == Decimal(0)


def test_rn31_el_libro_usa_la_tasa_de_cada_operacion(conexion, categoria, exento):
    """Cargar otra tasa hoy no puede mover los bolivares de una venta de ayer."""
    ayer = "2026-08-01"
    producto = alta(conexion, categoria, exento, precio_venta_usd=Decimal("2.0000"))
    registrar_compra(conexion, producto.id, Decimal("1.0000"), fecha=ayer)
    cargar_tasa(conexion, servicio_tasa.hoy(), Decimal("300.000000"))
    servicio_caja.abrir(conexion)
    venta = vender(conexion, producto.id, Decimal(1), [(EFECTIVO, "USD", Decimal(2))])

    desde, hasta = rango()
    fila = servicio_reportes.libro_de_ventas(conexion, desde, hasta).filas[0]
    assert fila.numero == venta.numero
    assert fila.tasa == Decimal("300.000000")
    assert fila.total_bs == Decimal("600.00")


def test_el_libro_agrupa_por_fecha(conexion, dia_de_ventas):
    desde, hasta = rango()
    libro = servicio_reportes.libro_de_ventas(conexion, desde, hasta)
    grupos = libro.por_fecha()
    assert [g.etiqueta for g in grupos] == [servicio_tasa.hoy()]
    assert grupos[0].total_bs == libro.totales.total_bs


def test_el_rango_invertido_se_rechaza(conexion):
    with pytest.raises(servicio_reportes.ErrorReporte, match="posterior"):
        servicio_reportes.ventas_por_periodo(conexion, "2026-12-31", "2026-01-01")


def test_el_cmv_redondea_medio_hacia_arriba_por_linea(conexion, categoria, exento):
    """RN-27 + regla 2: el CMV se resuelve en SQL y tiene que dar HALF_UP.

    Medio centimo justo: 1 x 0,0050 = 0,005, que a dos decimales es 0,01 y no
    0,00 (el default de Python seria ROUND_HALF_EVEN).
    """
    cargar_tasa(conexion, servicio_tasa.hoy())
    producto = alta(conexion, categoria, exento, precio_venta_usd=Decimal("1.0000"))
    registrar_compra(conexion, producto.id, Decimal("0.0050"), unidades=Decimal(10))
    servicio_caja.abrir(conexion)
    vender(conexion, producto.id, Decimal(1), [(EFECTIVO, "USD", Decimal(1))])

    desde, hasta = rango()
    fila = servicio_reportes.ganancia_por_producto(conexion, desde, hasta)[0]
    assert fila.costo_usd == Decimal("0.01")


# --- RF-47 / RF-53 / RF-54 / RN-29 ------------------------------------------


def test_rf53_las_perdidas_se_agrupan_por_motivo(conexion, dia_de_ventas):
    danado = repo_perdida.motivo_por_codigo(conexion, "DANADO").id
    faltante = repo_perdida.motivo_por_codigo(conexion, "FALTANTE").id
    servicio_perdidas.registrar(conexion, dia_de_ventas["arroz"].id, Decimal(1), danado)
    servicio_perdidas.registrar(conexion, dia_de_ventas["arroz"].id, Decimal(2), danado)
    servicio_perdidas.registrar(
        conexion, dia_de_ventas["jabon"].id, Decimal(4), faltante
    )

    desde, hasta = rango()
    filas = {
        f.motivo: f
        for f in servicio_reportes.perdidas_por_motivo(conexion, desde, hasta)
    }
    assert filas["Producto danado o roto"].cantidad == Decimal("3.000")
    assert filas["Producto danado o roto"].costo_usd == Decimal("3.60")  # 3 x 1,20
    assert filas["Faltante o sustraccion"].costo_usd == Decimal("2.00")  # 4 x 0,50


def test_rf54_el_reporte_de_vencimientos_lo_ve_tambien_el_cajero(
    conexion, categoria, exento
):
    """Quien atiende el mostrador tiene que ver que se le esta por vencer."""
    producto = alta(conexion, categoria, exento, maneja_vencimiento=True)
    vence = (date.today() + timedelta(days=3)).isoformat()
    registrar_compra(
        conexion, producto.id, Decimal("1.0000"), fecha_vencimiento=vence
    )
    cajero_id = servicio_usuarios.crear(
        conexion, Usuario(usuario="cajera", nombre="Cajera", rol=CAJERO), "clave1234"
    )
    iniciar_sesion(servicio_usuarios.obtener(conexion, cajero_id))

    lotes = servicio_reportes.proximos_a_vencer(conexion)
    assert [lote.fecha_vencimiento for lote in lotes] == [vence]


def test_rf47_la_ganancia_real_coincide_con_la_cuenta_a_mano(
    conexion, dia_de_ventas
):
    """RN-29 sobre datos conocidos, verificados renglon por renglon.

    Ventas validas del dia:
      arroz exento  3 x 2,00      -> ingreso 6,00 · costo 3 x 1,20 = 3,60
      jabon 16%     2 x 1,16=2,32 -> ingreso 2,00 (sin IVA) · costo 2 x 0,50 = 1,00
    La tercera venta esta anulada y no cuenta (RN-25).
    """
    perdida_arroz = repo_perdida.motivo_por_codigo(conexion, "DANADO").id
    servicio_perdidas.registrar(
        conexion, dia_de_ventas["arroz"].id, Decimal(1), perdida_arroz
    )
    servicio_gastos.registrar(
        conexion, ALQUILER, "Alquiler del mes", Decimal("0.80")
    )

    desde, hasta = rango()
    resultado = servicio_reportes.ganancia_real(conexion, desde, hasta)

    assert resultado.ingreso_usd == Decimal("8.00")  # 6,00 + 2,00
    assert resultado.costo_usd == Decimal("4.60")  # 3,60 + 1,00 (RN-27)
    assert resultado.ganancia_bruta_usd == Decimal("3.40")  # RN-28
    assert resultado.perdidas_usd == Decimal("1.20")  # 1 x 1,20 (RN-18)
    assert resultado.gastos_usd == Decimal("0.80")
    assert resultado.ganancia_real_usd == Decimal("1.40")  # RN-29
    assert resultado.margen_real_pct == Decimal("17.50")  # 1,40 / 8,00


def test_rn29_una_perdida_baja_la_ganancia_real_del_periodo(conexion, dia_de_ventas):
    desde, hasta = rango()
    antes = servicio_reportes.ganancia_real(conexion, desde, hasta)
    assert antes.perdidas_usd == Decimal(0)
    assert antes.ganancia_real_usd == antes.ganancia_bruta_usd

    servicio_perdidas.registrar(
        conexion,
        dia_de_ventas["arroz"].id,
        Decimal(2),
        repo_perdida.motivo_por_codigo(conexion, "DANADO").id,
    )

    despues = servicio_reportes.ganancia_real(conexion, desde, hasta)
    # La ganancia BRUTA no se mueve: la perdida no es una venta.
    assert despues.ganancia_bruta_usd == antes.ganancia_bruta_usd
    assert despues.perdidas_usd == Decimal("2.40")
    assert despues.ganancia_real_usd == antes.ganancia_real_usd - Decimal("2.40")


def test_los_gastos_de_otro_mes_no_entran_en_el_periodo(conexion, dia_de_ventas):
    servicio_gastos.registrar(
        conexion, ALQUILER, "Mes que no toca", Decimal(999), periodo="2020-01"
    )
    desde, hasta = rango()
    assert servicio_reportes.ganancia_real(conexion, desde, hasta).gastos_usd == (
        Decimal(0)
    )


def test_rf58_el_cajero_no_ve_la_ganancia_real_ni_las_perdidas(conexion):
    cajero_id = servicio_usuarios.crear(
        conexion, Usuario(usuario="cajera", nombre="Cajera", rol=CAJERO), "clave1234"
    )
    iniciar_sesion(servicio_usuarios.obtener(conexion, cajero_id))
    desde, hasta = rango()
    for operacion in (
        servicio_reportes.ganancia_real,
        servicio_reportes.perdidas_por_motivo,
    ):
        with pytest.raises(servicio_usuarios.ErrorPermiso):
            operacion(conexion, desde, hasta)
