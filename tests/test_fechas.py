"""La fecha escrita a mano se normaliza a ISO antes de tocar la base."""

import pytest

from minimarket.datos.conexion import abrir, transaccion
from minimarket.dominio.fechas import a_iso
from minimarket.servicios.compras import ErrorCompra
from minimarket.servicios.perdidas import proximos_a_vencer
from minimarket.ui.comunes import ErrorDeCampo, a_fecha
from tests.conftest import alta, registrar_compra


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("2027-02-01", "2027-02-01"),
        ("01-02-2027", "2027-02-01"),  # el caso que tumbaba el arranque
        ("01/02/2027", "2027-02-01"),
        ("1/2/2027", "2027-02-01"),
        ("2027/02/01", "2027-02-01"),
        (" 01.02.2027 ", "2027-02-01"),
    ],
)
def test_la_fecha_tecleada_se_normaliza(texto, esperado):
    assert a_iso(texto) == esperado


@pytest.mark.parametrize(
    "texto", ["", "manana", "01-02-27", "2027-02-31", "2027-13-01", "01-02", "x-y-z"]
)
def test_lo_que_no_es_fecha_no_se_inventa(texto):
    assert a_iso(texto) is None


def test_el_campo_avisa_en_castellano():
    with pytest.raises(ErrorDeCampo, match="no es una fecha valida"):
        a_fecha("31-02-2027", "la fecha de vencimiento")


def test_el_campo_opcional_admite_vacio():
    assert a_fecha("  ", "la fecha de vencimiento", opcional=True) is None
    with pytest.raises(ErrorDeCampo, match="Falta completar"):
        a_fecha("  ", "la fecha de vencimiento")


def test_la_compra_rechaza_un_vencimiento_que_no_es_fecha(conexion, categoria, exento):
    from decimal import Decimal

    producto = alta(conexion, categoria, exento, maneja_vencimiento=True)
    with pytest.raises(ErrorCompra, match="no es una fecha valida"):
        registrar_compra(
            conexion, producto.id, Decimal("1.0000"), fecha_vencimiento="mañana"
        )


def _lote_con_fecha(conexion, categoria, exento, fecha: str) -> int:
    producto = alta(conexion, categoria, exento, maneja_vencimiento=True)
    with transaccion(conexion):
        cursor = conexion.execute(
            "INSERT INTO lote (producto_id, fecha_vencimiento) VALUES (?, ?)",
            (producto.id, fecha),
        )
    return cursor.lastrowid


def _vencimiento(conexion, lote_id: int) -> str:
    return conexion.execute(
        "SELECT fecha_vencimiento FROM lote WHERE id = ?", (lote_id,)
    ).fetchone()[0]


def test_abrir_corrige_los_vencimientos_viejos(tmp_path, conexion, categoria, exento):
    """La base del cliente se cura sola: no puede correr ningun script."""
    lote_id = _lote_con_fecha(conexion, categoria, exento, "01-02-2027")
    conexion.close()

    reabierta = abrir(tmp_path / "prueba.db")
    assert _vencimiento(reabierta, lote_id) == "2027-02-01"
    reabierta.close()


def test_un_vencimiento_ilegible_no_tumba_el_arranque(conexion, categoria, exento):
    """Se anota al abrir y se deja fuera del aviso: Inicio tiene que abrir."""
    _lote_con_fecha(conexion, categoria, exento, "el martes")
    assert proximos_a_vencer(conexion) == []
    assert proximos_a_vencer(conexion, solo_alerta=False) == []
