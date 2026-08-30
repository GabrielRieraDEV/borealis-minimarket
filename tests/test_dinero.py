"""Pruebas de minimarket.dominio.dinero."""

from decimal import Decimal

import pytest

from minimarket.dominio.dinero import (
    ESCALA_CANTIDAD,
    ESCALA_PORCENTAJE,
    ESCALA_PRECIO,
    ESCALA_TASA,
    ESCALA_TOTAL,
    a_entero,
    convertir_a_bs,
    desde_entero,
    redondear,
    redondear_comercial,
)

TASA = Decimal("210.500000")


class TestRedondear:
    @pytest.mark.parametrize(
        ("valor", "decimales", "esperado"),
        [
            # El default de Python (ROUND_HALF_EVEN) daria 0 y 2.
            ("0.5", 0, "1"),
            ("2.5", 0, "3"),
            ("1.5", 0, "2"),
            ("0.82215", 4, "0.8222"),
            ("0.70875", 4, "0.7088"),
            ("1.005", 2, "1.01"),
            ("164.185", 2, "164.19"),
        ],
    )
    def test_redondea_medio_hacia_arriba(self, valor, decimales, esperado):
        assert redondear(Decimal(valor), decimales) == Decimal(esperado)

    def test_los_negativos_tambien_van_hacia_arriba(self):
        # ROUND_HALF_UP en decimal es "medio lejos del cero".
        assert redondear(Decimal("-2.5"), 0) == Decimal("-3")


class TestEnteroEscalado:
    @pytest.mark.parametrize(
        ("valor", "escala", "esperado"),
        [
            # Los cuatro ejemplos de la tabla 5.2 de docs/requisitos.md.
            ("0.7800", ESCALA_PRECIO, 7800),
            ("4.76", ESCALA_TOTAL, 476),
            ("2.500", ESCALA_CANTIDAD, 2500),
            ("210.500000", ESCALA_TASA, 210_500_000),
            ("16.00", ESCALA_PORCENTAJE, 1600),
        ],
    )
    def test_a_entero(self, valor, escala, esperado):
        assert a_entero(Decimal(valor), escala) == esperado

    @pytest.mark.parametrize(
        ("entero", "escala", "esperado"),
        [
            (7800, ESCALA_PRECIO, "0.7800"),
            (476, ESCALA_TOTAL, "4.76"),
            (2500, ESCALA_CANTIDAD, "2.500"),
            (210_500_000, ESCALA_TASA, "210.500000"),
            (1600, ESCALA_PORCENTAJE, "16.00"),
        ],
    )
    def test_desde_entero(self, entero, escala, esperado):
        assert desde_entero(entero, escala) == Decimal(esperado)

    @pytest.mark.parametrize(
        "escala",
        [ESCALA_PRECIO, ESCALA_TOTAL, ESCALA_CANTIDAD, ESCALA_TASA, ESCALA_PORCENTAJE],
    )
    def test_ida_y_vuelta(self, escala):
        for entero in (0, 1, 476, 7800, 210_500_000):
            assert a_entero(desde_entero(entero, escala), escala) == entero

    def test_recorta_al_guardar_con_medio_hacia_arriba(self):
        # Un total con mas decimales de los que admite su escala se redondea,
        # no se trunca.
        assert a_entero(Decimal("4.765"), ESCALA_TOTAL) == 477
        assert a_entero(Decimal("0.82215"), ESCALA_PRECIO) == 8222

    def test_los_negativos_se_guardan_como_negativos(self):
        # Las salidas de inventario son cantidades negativas (RN-12).
        assert a_entero(Decimal("-2.500"), ESCALA_CANTIDAD) == -2500
        assert desde_entero(-2500, ESCALA_CANTIDAD) == Decimal("-2.500")


class TestConvertirABs:
    def test_ejemplo_a_precio_de_la_harina(self):
        assert convertir_a_bs(Decimal("0.7800"), TASA) == Decimal("164.19")

    def test_ejemplo_b_precio_del_refresco(self):
        # docs/reglas-de-negocio.md dice 173,08. Es una errata:
        # 0,8222 x 210,500000 = 173,0731 -> 173,07. Ver CLAUDE.md.
        assert convertir_a_bs(Decimal("0.8222"), TASA) == Decimal("173.07")

    def test_ejemplo_c_total_de_la_venta(self):
        assert convertir_a_bs(Decimal("4.76"), TASA) == Decimal("1001.98")

    def test_ejemplo_c_vuelto(self):
        assert convertir_a_bs(Decimal("0.24"), TASA) == Decimal("50.52")


class TestRedondeoComercial:
    @pytest.mark.parametrize(
        ("monto", "esperado"),
        [
            ("164.19", "165.00"),  # ejemplo A
            ("173.07", "174.00"),  # ejemplo B
            ("50.52", "51.00"),  # ejemplo C, vuelto en bolivares
            ("165.00", "165.00"),  # ya es multiplo exacto: no sube
            ("0.01", "1.00"),
            ("0.00", "0.00"),
        ],
    )
    def test_multiplo_de_uno_hacia_arriba(self, monto, esperado):
        assert redondear_comercial(Decimal(monto)) == Decimal(esperado)

    def test_otros_multiplos(self):
        assert redondear_comercial(Decimal("164.19"), Decimal("5")) == Decimal("165.00")
        assert redondear_comercial(Decimal("50.52"), Decimal("0.50")) == Decimal("51.00")
        assert redondear_comercial(Decimal("50.02"), Decimal("0.50")) == Decimal("50.50")

    def test_multiplo_invalido(self):
        with pytest.raises(ValueError):
            redondear_comercial(Decimal("100"), Decimal(0))
