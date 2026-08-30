"""Pruebas de minimarket.dominio.impuestos.

Los ejemplos trabajados A, B y C de docs/reglas-de-negocio.md son la
especificacion: si el codigo da otro resultado, el codigo esta mal.
"""

from decimal import Decimal

import pytest

from minimarket.dominio.dinero import (
    DECIMALES_PRECIO,
    DECIMALES_TOTAL,
    convertir_a_bs,
    redondear,
    redondear_comercial,
)
from minimarket.dominio.impuestos import (
    desglosar_precio,
    margen_sobre_costo,
    precio_desde_margen,
)

TASA = Decimal("210.500000")
EXENTO = Decimal("0.00")
GENERAL = Decimal("16.00")


class TestEjemploA:
    """Harina de maiz precocida, exenta.

    Bulto de 20 unidades a 12,00 USD, margen objetivo 30 %, tasa 210,500000.
    """

    COSTO_UNITARIO = redondear(Decimal("12.00") / 20, DECIMALES_PRECIO)

    def test_costo_unitario(self):
        assert self.COSTO_UNITARIO == Decimal("0.6000")

    def test_precio_con_iva(self):
        precio = precio_desde_margen(self.COSTO_UNITARIO, Decimal("30"), EXENTO)
        assert precio == Decimal("0.7800")

    def test_en_el_exento_la_base_es_el_precio_y_el_iva_cero(self):
        base, iva = desglosar_precio(Decimal("0.7800"), EXENTO)
        assert base == Decimal("0.7800")
        assert iva == Decimal("0")

    def test_precio_en_bolivares(self):
        assert convertir_a_bs(Decimal("0.7800"), TASA) == Decimal("164.19")

    def test_precio_redondeado_al_publico(self):
        assert redondear_comercial(Decimal("164.19")) == Decimal("165.00")

    def test_margen_real_sobre_el_costo(self):
        assert margen_sobre_costo(Decimal("0.7800"), self.COSTO_UNITARIO) == Decimal(
            "30.00"
        )


class TestEjemploB:
    """Refresco en lata, gravado al 16 %.

    Caja de 24 unidades a 12,60 USD, margen objetivo 35 %, tasa 210,500000.
    """

    COSTO_UNITARIO = redondear(Decimal("12.60") / 24, DECIMALES_PRECIO)

    def test_costo_unitario(self):
        assert self.COSTO_UNITARIO == Decimal("0.5250")

    def test_precio_con_iva(self):
        precio = precio_desde_margen(self.COSTO_UNITARIO, Decimal("35"), GENERAL)
        assert precio == Decimal("0.8222")

    def test_base_e_iva_del_precio_objetivo(self):
        base = redondear(self.COSTO_UNITARIO * Decimal("1.35"), DECIMALES_PRECIO)
        iva = redondear(base * Decimal("0.16"), DECIMALES_PRECIO)
        assert base == Decimal("0.7088")
        assert iva == Decimal("0.1134")
        assert base + iva == Decimal("0.8222")

    def test_desglose_inverso_devuelve_la_base_original(self):
        """Verificacion obligatoria de docs/reglas-de-negocio.md.

        Si dividir el precio con IVA entre 1,16 no recupera la base de partida,
        hay un error de redondeo en el orden de las operaciones.
        """
        base, iva = desglosar_precio(Decimal("0.8222"), GENERAL)
        assert base == Decimal("0.7088")
        assert iva == Decimal("0.1134")
        assert base + iva == Decimal("0.8222")

    def test_el_desglose_inverso_necesita_cuatro_decimales(self):
        # A dos decimales el desglose no recupera la base: por eso los precios
        # de catalogo se manejan con cuatro (seccion 5.2 de docs/requisitos.md).
        base, _ = desglosar_precio(Decimal("0.8222"), GENERAL, DECIMALES_TOTAL)
        assert base != Decimal("0.7088")

    def test_precio_en_bolivares(self):
        # docs/reglas-de-negocio.md dice 173,08. Es una errata:
        # 0,8222 x 210,500000 = 173,0731 -> 173,07. Ver CLAUDE.md.
        assert convertir_a_bs(Decimal("0.8222"), TASA) == Decimal("173.07")

    def test_precio_redondeado_al_publico(self):
        assert redondear_comercial(Decimal("173.07")) == Decimal("174.00")

    def test_margen_real_sobre_el_costo(self):
        assert margen_sobre_costo(Decimal("0.7088"), self.COSTO_UNITARIO) == Decimal(
            "35.01"
        )


class TestEjemploC:
    """Venta mixta con exento y gravado, pago de 5,00 USD y vuelto en bolivares.

    Cuatro paquetes de harina exenta a 0,7800 y dos refrescos gravados a 0,8222.

    Solo se verifica la aritmetica de linea de RN-20; el armado del documento de
    venta es de la Fase 3.
    """

    def test_linea_1_exenta(self):
        total = redondear(4 * Decimal("0.7800"), DECIMALES_TOTAL)
        base, iva = desglosar_precio(total, EXENTO, DECIMALES_TOTAL)
        assert total == Decimal("3.12")
        assert base == Decimal("3.12")
        assert iva == Decimal("0")

    def test_linea_2_gravada(self):
        total = redondear(2 * Decimal("0.8222"), DECIMALES_TOTAL)
        base, iva = desglosar_precio(total, GENERAL, DECIMALES_TOTAL)
        assert total == Decimal("1.64")
        assert base == Decimal("1.41")
        assert iva == Decimal("0.23")

    def test_totales_del_documento(self):
        exento = redondear(4 * Decimal("0.7800"), DECIMALES_TOTAL)
        total_gravado = redondear(2 * Decimal("0.8222"), DECIMALES_TOTAL)
        base, iva = desglosar_precio(total_gravado, GENERAL, DECIMALES_TOTAL)

        assert exento == Decimal("3.12")
        assert base == Decimal("1.41")
        assert iva == Decimal("0.23")

        total = exento + base + iva
        assert total == Decimal("4.76")
        # RN-20: el total del documento es la suma de los totales de linea ya
        # redondeados, no un IVA recalculado sobre el total.
        assert total == exento + total_gravado

    def test_equivalente_en_bolivares(self):
        assert convertir_a_bs(Decimal("4.76"), TASA) == Decimal("1001.98")

    def test_vuelto(self):
        vuelto = Decimal("5.00") - Decimal("4.76")
        assert vuelto == Decimal("0.24")
        assert convertir_a_bs(vuelto, TASA) == Decimal("50.52")
        assert redondear_comercial(Decimal("50.52")) == Decimal("51.00")


class TestMargen:
    def test_sin_costo_registrado_no_es_determinable(self):
        # Seccion 7 de docs/reglas-de-negocio.md: se permite vender, pero el
        # margen se informa como no determinable.
        assert margen_sobre_costo(Decimal("0.7800"), Decimal("0")) is None

    def test_margen_negativo_cuando_el_costo_supera_la_base(self):
        # Caso limite: el costo nuevo quedo por encima del precio de venta.
        assert margen_sobre_costo(Decimal("0.5000"), Decimal("0.6000")) == Decimal(
            "-16.67"
        )


class TestDesglosarPrecio:
    @pytest.mark.parametrize("alicuota", ["0.00", "8.00", "16.00"])
    def test_base_mas_iva_siempre_devuelve_el_precio(self, alicuota):
        precio = Decimal("0.8222")
        base, iva = desglosar_precio(precio, Decimal(alicuota))
        assert base + iva == precio

    def test_alicuota_reducida(self):
        base, iva = desglosar_precio(Decimal("1.0800"), Decimal("8.00"))
        assert base == Decimal("1.0000")
        assert iva == Decimal("0.0800")
