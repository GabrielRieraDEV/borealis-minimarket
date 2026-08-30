"""Respaldo, restauracion y exportacion a PDF (RF-61 a RF-64)."""

from decimal import Decimal

import pytest

from minimarket.datos.conexion import abrir
from minimarket.datos.repositorios import configuracion as repo_configuracion
from minimarket.datos.repositorios import producto as repo_producto
from minimarket.infra import auditoria, respaldo
from minimarket.servicios import cerrar_sesion
from minimarket.servicios import configuracion as servicio_configuracion
from tests.conftest import alta


@pytest.fixture(autouse=True)
def sin_sesion():
    cerrar_sesion()
    yield
    cerrar_sesion()


@pytest.fixture
def destino(conexion, tmp_path):
    """Deja configurada una carpeta de respaldo y la devuelve."""
    carpeta = tmp_path / "unidad-externa"
    servicio_configuracion.guardar(conexion, {"respaldo.ruta": str(carpeta)})
    return carpeta


# --- RF-61 / RF-62 ----------------------------------------------------------


def test_rf61_el_respaldo_genera_un_archivo_restaurable(
    conexion, destino, categoria, exento
):
    alta(conexion, categoria, exento, nombre="Harina")
    registro = servicio_configuracion.respaldar(conexion)

    assert registro.ok
    assert registro.tamano_bytes > 0

    copia = abrir(registro.ruta)
    try:
        nombres = [p.nombre for p in repo_producto.listar(copia)]
    finally:
        copia.close()
    assert nombres == ["Harina"]


def test_rf62_cada_intento_queda_registrado(conexion, destino):
    servicio_configuracion.respaldar(conexion)
    servicio_configuracion.respaldar(conexion)
    historial = servicio_configuracion.historial(conexion)
    assert len(historial) == 2
    assert all(r.estado == respaldo.OK for r in historial)


def test_rf62_sin_carpeta_configurada_el_intento_queda_en_error(conexion):
    registro = servicio_configuracion.respaldar(conexion)
    assert not registro.ok
    assert "carpeta" in registro.mensaje
    assert servicio_configuracion.historial(conexion)[0].estado == respaldo.ERROR


def test_rf62_la_unidad_que_no_esta_no_rompe_la_aplicacion(conexion, tmp_path):
    """La unidad externa desconectada es lo normal, no una excepcion."""
    archivo = tmp_path / "no-es-carpeta"
    archivo.write_text("ocupa el nombre", encoding="utf-8")
    servicio_configuracion.guardar(
        conexion, {"respaldo.ruta": str(archivo / "adentro")}
    )
    registro = servicio_configuracion.respaldar(conexion)
    assert not registro.ok
    assert "No se pudo respaldar" in registro.mensaje


def test_el_respaldo_automatico_corre_una_vez_por_dia(conexion, destino):
    servicio_configuracion.guardar(conexion, {"respaldo.hora": "22:00"})

    assert servicio_configuracion.respaldo_automatico(conexion, ahora="21:59") is None
    primero = servicio_configuracion.respaldo_automatico(conexion, ahora="22:00")
    assert primero is not None and primero.ok
    assert servicio_configuracion.respaldo_automatico(conexion, ahora="23:30") is None


def test_sin_carpeta_configurada_el_automatico_no_hace_nada(conexion):
    assert servicio_configuracion.respaldo_automatico(conexion, ahora="23:59") is None
    assert servicio_configuracion.historial(conexion) == []


# --- RF-63 ------------------------------------------------------------------


def test_rf63_la_restauracion_devuelve_los_datos_del_respaldo(
    conexion, destino, categoria, exento
):
    alta(conexion, categoria, exento, nombre="Harina")
    registro = servicio_configuracion.respaldar(conexion)
    alta(conexion, categoria, exento, nombre="Arroz posterior al respaldo")
    assert len(repo_producto.listar(conexion)) == 2

    servicio_configuracion.restaurar(conexion, registro.ruta)

    # La conexion sigue viva y ve el contenido del respaldo (RF-63).
    assert [p.nombre for p in repo_producto.listar(conexion)] == ["Harina"]
    assert auditoria.listar(conexion, accion=auditoria.RESTAURACION)


def test_la_restauracion_rechaza_un_archivo_que_no_es_de_este_sistema(
    conexion, tmp_path
):
    ajeno = tmp_path / "ajeno.db"
    import sqlite3

    otra = sqlite3.connect(str(ajeno))
    otra.execute("CREATE TABLE cosas (id INTEGER)")
    otra.commit()
    otra.close()

    with pytest.raises(servicio_configuracion.ErrorConfiguracion, match="no es un"):
        servicio_configuracion.restaurar(conexion, str(ajeno))
    # La base sigue funcionando.
    assert repo_producto.listar(conexion) == []


def test_la_restauracion_de_un_archivo_inexistente_avisa(conexion, tmp_path):
    with pytest.raises(servicio_configuracion.ErrorConfiguracion):
        servicio_configuracion.restaurar(conexion, str(tmp_path / "no-existe.db"))


# --- RF-64 ------------------------------------------------------------------


def test_rf64_la_configuracion_se_guarda_y_queda_en_la_bitacora(conexion):
    servicio_configuracion.guardar(
        conexion,
        {"negocio.nombre": "Minimarket Borealis", "negocio.rif": "J-123456789"},
    )
    assert repo_configuracion.leer(conexion, "negocio.nombre") == "Minimarket Borealis"
    assert servicio_configuracion.datos_del_negocio(conexion)["rif"] == "J-123456789"
    assert auditoria.listar(conexion, accion=auditoria.CAMBIO_CONFIGURACION)


def test_una_clave_desconocida_se_rechaza(conexion):
    with pytest.raises(servicio_configuracion.ErrorConfiguracion, match="configurable"):
        servicio_configuracion.guardar(conexion, {"lo.que.sea": "1"})


def test_el_redondeo_tiene_que_ser_un_numero_positivo(conexion):
    with pytest.raises(servicio_configuracion.ErrorConfiguracion, match="numero"):
        servicio_configuracion.guardar(conexion, {"precio.redondeo_bs": "mucho"})
    with pytest.raises(servicio_configuracion.ErrorConfiguracion, match="mayor"):
        servicio_configuracion.guardar(conexion, {"precio.redondeo_bs": "0"})


def test_guardar_lo_mismo_no_deja_asiento(conexion):
    servicio_configuracion.guardar(conexion, {"negocio.nombre": "Borealis"})
    servicio_configuracion.guardar(conexion, {"negocio.nombre": "Borealis"})
    assert len(auditoria.listar(conexion, accion=auditoria.CAMBIO_CONFIGURACION)) == 1


# --- Exportacion a PDF ------------------------------------------------------


def test_el_reporte_se_exporta_a_pdf(tmp_path):
    from minimarket.infra import pdf

    destino = pdf.exportar(
        tmp_path / "reporte.pdf",
        "Ventas del periodo",
        ["Medio", "Moneda", "Cobrado"],
        [["EFECTIVO", "USD", "6,00"]],
        negocio={"nombre": "Minimarket Borealis", "rif": "J-123456789"},
        subtitulo="Del 2026-08-01 al 2026-08-31",
        pie=[f"Total {Decimal('6.00')} USD"],
    )
    assert destino.exists()
    assert destino.read_bytes().startswith(b"%PDF")


def test_el_pdf_sin_filas_igual_se_arma(tmp_path):
    from minimarket.infra import pdf

    destino = pdf.exportar(tmp_path / "vacio.pdf", "Sin movimientos", ["A", "B"], [])
    assert destino.exists()
