"""Tasa de cambio: registro, reemplazo, historico y consulta al BCV.

RF-09 a RF-13, RN-02 a RN-04.
"""

from decimal import Decimal

import pytest

from minimarket.infra import bcv
from minimarket.servicios import tasa as servicio_tasa


def test_registro_manual_conserva_los_seis_decimales(conexion):
    servicio_tasa.registrar_manual(
        conexion, Decimal("210.500000"), fecha="2026-08-29"
    )
    assert servicio_tasa.tasa_del_dia(conexion, "2026-08-29") == Decimal("210.500000")


def test_una_sola_tasa_por_fecha(conexion):
    """RN-02. La segunda carga reemplaza a la primera, no se acumulan."""
    servicio_tasa.registrar_manual(conexion, Decimal("210.5"), fecha="2026-08-29")
    servicio_tasa.registrar_manual(conexion, Decimal("212.75"), fecha="2026-08-29")

    assert servicio_tasa.tasa_del_dia(conexion, "2026-08-29") == Decimal("212.750000")
    assert len(servicio_tasa.historico(conexion)) == 1


def test_el_reemplazo_conserva_el_id_al_que_apuntan_las_operaciones(conexion):
    """RN-02. Las operaciones ya registradas referencian tasa_cambio.id."""
    servicio_tasa.registrar_manual(conexion, Decimal("210.5"), fecha="2026-08-29")
    primero = servicio_tasa.historico(conexion)[0].id
    servicio_tasa.registrar_manual(conexion, Decimal("212.75"), fecha="2026-08-29")
    assert servicio_tasa.historico(conexion)[0].id == primero


def test_tasa_no_positiva_se_rechaza(conexion):
    with pytest.raises(servicio_tasa.ErrorTasa):
        servicio_tasa.registrar_manual(conexion, Decimal(0))


def test_sin_tasa_del_dia_no_se_opera(conexion):
    """RF-12. Sin tasa no se abre caja ni se registran ventas."""
    assert servicio_tasa.tasa_del_dia(conexion) is None
    with pytest.raises(servicio_tasa.ErrorTasa, match="No hay tasa de cambio"):
        servicio_tasa.exigir_tasa(conexion)


def test_no_se_hereda_la_tasa_del_dia_anterior(conexion):
    """RN-04. Nunca se asume la tasa de ayer."""
    servicio_tasa.registrar_manual(conexion, Decimal("210.5"), fecha="2026-08-28")
    assert servicio_tasa.tasa_del_dia(conexion, "2026-08-29") is None


def test_historico_ordenado_y_filtrado(conexion):
    """RF-13. Las operaciones pasadas conservan su valor original."""
    for fecha, valor in [
        ("2026-08-27", "208"),
        ("2026-08-28", "209.25"),
        ("2026-08-29", "210.5"),
    ]:
        servicio_tasa.registrar_manual(conexion, Decimal(valor), fecha=fecha)

    todas = servicio_tasa.historico(conexion)
    assert [t.fecha for t in todas] == ["2026-08-29", "2026-08-28", "2026-08-27"]

    tramo = servicio_tasa.historico(conexion, desde="2026-08-28", hasta="2026-08-28")
    assert [t.valor for t in tramo] == [Decimal("209.250000")]


def test_consulta_al_bcv_registra_la_tasa(conexion, monkeypatch):
    """RF-10. Origen automatico cuando la consulta responde."""
    monkeypatch.setattr(bcv, "consultar", lambda *_a, **_k: Decimal("212.345678"))

    valor = servicio_tasa.actualizar_desde_bcv(conexion, fecha="2026-08-29")
    assert valor == Decimal("212.345678")
    assert servicio_tasa.historico(conexion)[0].origen == "BCV_AUTO"


def test_si_el_bcv_falla_no_bloquea_ni_registra_nada(conexion, monkeypatch):
    """RF-10 / RN-04. Devuelve None y queda la carga manual."""
    monkeypatch.setattr(bcv, "consultar", lambda *_a, **_k: None)

    assert servicio_tasa.actualizar_desde_bcv(conexion, fecha="2026-08-29") is None
    assert servicio_tasa.historico(conexion) == []


def test_la_red_caida_no_propaga_la_excepcion(monkeypatch):
    """La consulta al BCV nunca tumba la aplicacion (RNF-01)."""

    def explotar(*_a, **_k):
        raise OSError("sin conexion")

    monkeypatch.setattr("requests.get", explotar)
    assert bcv.consultar("https://ejemplo.invalido/") is None


def test_lectura_del_valor_publicado_por_el_bcv():
    html = """<div id="dolar"><div class="col-sm-6 col-xs-6 centrado">
              <strong> 212,34567800 </strong></div></div>"""
    assert bcv._extraer(html) == Decimal("212.345678")


def test_html_inesperado_no_inventa_una_tasa():
    assert bcv._extraer("<html>mantenimiento</html>") is None


def test_multiplo_de_redondeo_por_defecto(conexion):
    """RN-10. El esquema siembra precio.redondeo_bs en 1."""
    assert servicio_tasa.multiplo_redondeo(conexion) == Decimal(1)
