"""Nota de entrega (RF-39). El texto se arma sin tocar la impresora."""

from decimal import Decimal

import pytest

from minimarket.dominio.venta import EFECTIVO, USD, Cliente, LineaVenta, Pago, Venta
from minimarket.infra import impresora
from tests.conftest import TASA_DEL_EJEMPLO

NEGOCIO = {
    "nombre": "Minimarket La Esquina",
    "rif": "J-12345678-9",
    "direccion": "Av. Principal, local 3",
    "telefono": "0293-1234567",
}


@pytest.fixture
def venta() -> Venta:
    """El ejemplo C, ya registrado."""
    return Venta(
        usuario_id=1,
        tasa=TASA_DEL_EJEMPLO,
        numero=123,
        fecha_hora="2026-08-29 14:32:00",
        lineas=[
            LineaVenta(1, "Harina de maiz", Decimal(4), Decimal("0.7800"), Decimal(0), Decimal("0.6000")),
            LineaVenta(2, "Refresco 2 L", Decimal(2), Decimal("0.8222"), Decimal(16), Decimal("0.5000")),
        ],
        pagos=[Pago(EFECTIVO, USD, Decimal("5.00"), Decimal("5.00"))],
    )


def test_la_nota_lleva_los_datos_fiscales_y_el_desglose(venta):
    """RF-39 / RN-21."""
    texto = "\n".join(impresora.nota_de_entrega(venta, NEGOCIO))
    assert "MINIMARKET LA ESQUINA" in texto
    assert "J-12345678-9" in texto
    assert "NOTA DE ENTREGA N° 000123" in texto
    assert "Exento" in texto and "3.12" in texto
    assert "Base imponible" in texto and "1.41" in texto
    assert "IVA" in texto and "0.23" in texto
    assert "TOTAL USD" in texto and "4.76" in texto
    assert "TOTAL Bs" in texto and "1,001.98" in texto


def test_la_nota_muestra_el_vuelto_en_bolivares(venta):
    """RN-23."""
    texto = "\n".join(impresora.nota_de_entrega(venta, NEGOCIO))
    assert "51.00 Bs" in texto  # 0,24 USD redondeados hacia arriba


def test_la_nota_identifica_al_cliente_cuando_lo_hay(venta):
    """RF-40."""
    cliente = Cliente(razon_social="Acme C.A.", rif="J-30012345-6", tipo="EMPRESA")
    texto = "\n".join(impresora.nota_de_entrega(venta, NEGOCIO, cliente))
    assert "Cliente: Acme C.A." in texto
    assert "RIF: J-30012345-6" in texto


def test_ninguna_linea_excede_el_ancho_del_papel(venta):
    largas = Venta(
        usuario_id=1,
        tasa=TASA_DEL_EJEMPLO,
        numero=9,
        lineas=[
            LineaVenta(
                1,
                "Detergente en polvo multiusos presentacion familiar de 5 kg",
                Decimal("12.500"),
                Decimal("123.4567"),
                Decimal(16),
                Decimal(1),
            )
        ],
        pagos=[Pago(EFECTIVO, USD, Decimal("2000.00"), Decimal("2000.00"))],
    )
    for linea in impresora.nota_de_entrega(largas, NEGOCIO):
        assert len(linea) <= impresora.ANCHO, linea


def test_sin_impresora_configurada_avisa_en_vez_de_romper(venta):
    """La venta ya esta registrada: imprimir es lo unico que puede fallar."""
    with pytest.raises(impresora.ErrorImpresion, match="No hay impresora"):
        impresora.imprimir(impresora.nota_de_entrega(venta, NEGOCIO), "  ")
