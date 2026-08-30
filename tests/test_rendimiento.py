"""Rendimiento sobre 3.000 productos.

RNF-03: la busqueda responde en menos de un segundo.
RNF-02: registrar una linea de venta tarda menos de 300 ms.
"""

import time

import pytest

from minimarket.servicios import catalogo
from minimarket.servicios import venta as servicio_venta
from tests.datos_prueba import cargar

LIMITE_SEGUNDOS = 1.0
LIMITE_LINEA_SEGUNDOS = 0.3  # RNF-02


@pytest.fixture(scope="module")
def catalogo_grande(tmp_path_factory):
    from minimarket.datos.conexion import abrir

    conexion = abrir(tmp_path_factory.mktemp("rendimiento") / "prueba.db")
    cargar(conexion, 3000)
    yield conexion
    conexion.close()


def _medir(conexion, texto: str) -> tuple[float, int]:
    inicio = time.perf_counter()
    resultado = catalogo.buscar(conexion, texto)
    return time.perf_counter() - inicio, len(resultado)


def test_busqueda_por_nombre_bajo_un_segundo(catalogo_grande):
    assert (
        catalogo_grande.execute("SELECT COUNT(*) FROM producto").fetchone()[0] == 3000
    )
    segundos, encontrados = _medir(catalogo_grande, "harina")
    assert encontrados > 0
    assert segundos < LIMITE_SEGUNDOS, f"la busqueda por nombre tardo {segundos:.3f} s"


def test_busqueda_por_codigo_de_barras_bajo_un_segundo(catalogo_grande):
    segundos, encontrados = _medir(catalogo_grande, "7700000002500")
    assert encontrados == 1
    assert segundos < LIMITE_SEGUNDOS, f"la busqueda por codigo tardo {segundos:.3f} s"


def test_busqueda_sin_coincidencias_tambien_responde(catalogo_grande):
    segundos, encontrados = _medir(catalogo_grande, "zzzzz")
    assert encontrados == 0
    assert segundos < LIMITE_SEGUNDOS


def test_registrar_una_linea_de_venta_bajo_300_ms(catalogo_grande):
    """RNF-02. El camino que recorre cada lectura del codigo de barras."""
    peor = 0.0
    for numero in range(20):
        codigo = f"77{numero:011d}"
        inicio = time.perf_counter()
        producto = catalogo.buscar(catalogo_grande, codigo)[0]
        servicio_venta.nueva_linea(catalogo_grande, producto.id)
        peor = max(peor, time.perf_counter() - inicio)
    assert peor < LIMITE_LINEA_SEGUNDOS, f"la peor linea tardo {peor:.3f} s"


# --- RNF-04: cualquier reporte de un mes de operacion, en menos de 5 s -------

LIMITE_REPORTE_SEGUNDOS = 5.0  # RNF-04

MES = "2026-07"
DESDE = f"{MES}-01"
HASTA = f"{MES}-31"


@pytest.fixture(scope="module")
def mes_de_operacion(tmp_path_factory):
    """Un mes realista: 3.000 productos, 1.000 con stock y 500 ventas.

    Se arma una sola vez para todo el modulo; construirlo es lento a proposito,
    porque pasa por los servicios reales y no por INSERT directos.
    """
    from decimal import Decimal

    from minimarket.datos.conexion import abrir
    from minimarket.dominio.compra import Compra, LineaCompra, Proveedor
    from minimarket.dominio.venta import Venta
    from minimarket.servicios import caja as servicio_caja
    from minimarket.servicios import compras as servicio_compras
    from minimarket.servicios import gastos as servicio_gastos
    from minimarket.servicios import perdidas as servicio_perdidas
    from minimarket.servicios import tasa as servicio_tasa
    from minimarket.dominio.reportes import ALQUILER
    from minimarket.datos.repositorios import perdida as repo_perdida

    conexion = abrir(tmp_path_factory.mktemp("mes") / "prueba.db")
    productos = cargar(conexion, 3000)
    servicio_tasa.registrar_manual(conexion, Decimal("210.500000"), DESDE)
    proveedor = servicio_compras.guardar_proveedor(
        conexion, Proveedor(nombre="Distribuidora")
    )

    # 1.000 productos con existencia, en 10 compras de 100 lineas.
    con_stock = productos[:1000]
    for bloque in range(10):
        servicio_compras.registrar_compra(
            conexion,
            Compra(
                proveedor_id=proveedor,
                fecha=DESDE,
                usuario_id=1,
                lineas=[
                    LineaCompra(
                        producto_id=identificador,
                        cant_presentacion=Decimal(1),
                        unid_x_presentacion=Decimal(100),
                        costo_present_usd=Decimal(100),
                        # Charcuteria, carniceria y hortalizas llevan lote; con
                        # eso RF-31 y RF-54 se miden sobre datos reales.
                        fecha_vencimiento=f"2026-08-{1 + identificador % 28:02d}",
                    )
                    for identificador in con_stock[bloque * 100 : (bloque + 1) * 100]
                ],
            ),
        )

    servicio_tasa.registrar_manual(conexion, Decimal("215.000000"))
    servicio_caja.abrir(conexion)
    for numero in range(500):
        venta = Venta(usuario_id=1, tasa=Decimal(0))
        venta.lineas = [
            servicio_venta.nueva_linea(
                conexion, con_stock[(numero * 3 + salto) % 1000], Decimal(1)
            )
            for salto in range(3)
        ]
        venta.pagos = [
            servicio_venta.pago("EFECTIVO", "USD", venta.total_usd, Decimal(1))
        ]
        servicio_venta.registrar_venta(conexion, venta)

    motivo = repo_perdida.motivo_por_codigo(conexion, "DANADO").id
    for identificador in con_stock[:50]:
        servicio_perdidas.registrar(conexion, identificador, Decimal(1), motivo)
    servicio_gastos.registrar(conexion, ALQUILER, "Alquiler", Decimal(350))

    yield conexion
    conexion.close()


def _reportes(conexion):
    """Los nueve reportes de la aplicacion, tal como los pide la pantalla."""
    from minimarket.servicios import reportes

    sesion = conexion.execute("SELECT MAX(id) FROM caja_sesion").fetchone()[0]
    return [
        ("ventas del periodo (RF-48)", lambda: reportes.ventas_por_periodo(
            conexion, DESDE, HASTA)),
        ("inventario valorizado (RF-49)", lambda: reportes.inventario_valorizado(
            conexion)),
        ("ganancia por producto (RF-50)", lambda: reportes.ganancia_por_producto(
            conexion, DESDE, HASTA)),
        ("ganancia por categoria (RF-50)", lambda: reportes.ganancia_por_categoria(
            conexion, DESDE, HASTA)),
        ("cierre de caja (RF-51)", lambda: reportes.cierre_de_caja(conexion, sesion)),
        ("libro de ventas (RF-52)", lambda: reportes.libro_de_ventas(
            conexion, DESDE, HASTA)),
        ("perdidas por motivo (RF-53)", lambda: reportes.perdidas_por_motivo(
            conexion, DESDE, HASTA)),
        ("proximos a vencer (RF-54)", lambda: reportes.proximos_a_vencer(conexion)),
        ("ganancia real (RF-55)", lambda: reportes.ganancia_real(
            conexion, DESDE, HASTA)),
    ]


def test_rnf04_todos_los_reportes_del_mes_bajo_cinco_segundos(mes_de_operacion):
    """RNF-04, medido sobre los nueve reportes con un mes cargado."""
    assert mes_de_operacion.execute(
        "SELECT COUNT(*) FROM venta"
    ).fetchone()[0] == 500

    lentos = []
    for nombre, generar in _reportes(mes_de_operacion):
        inicio = time.perf_counter()
        generar()
        segundos = time.perf_counter() - inicio
        if segundos >= LIMITE_REPORTE_SEGUNDOS:
            lentos.append(f"{nombre}: {segundos:.3f} s")
    assert not lentos, "reportes por encima de RNF-04: " + ", ".join(lentos)


def test_la_existencia_calculada_no_necesita_cache(mes_de_operacion):
    """RN-11. La vista `v_existencia` suma los movimientos en cada consulta.

    El modelo de datos sugeria materializarla por volumen. Esta medicion es la
    que decide: mientras la consulta completa sobre 3.000 productos entre
    comoda en el limite de RNF-04, no hay caché que justificar.
    """
    from minimarket.servicios import inventario

    inicio = time.perf_counter()
    filas = inventario.consultar(mes_de_operacion)
    segundos = time.perf_counter() - inicio
    assert len(filas) == 2000  # el limite por defecto de la consulta
    assert segundos < LIMITE_SEGUNDOS, f"la existencia tardo {segundos:.3f} s"
