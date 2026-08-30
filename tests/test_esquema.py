"""Pruebas de minimarket.datos.conexion y del esquema SQLite."""

import sqlite3

import pytest

from minimarket.datos.conexion import abrir, transaccion

TABLAS = {
    "usuario", "configuracion", "auditoria", "respaldo",
    "categoria", "alicuota_iva", "producto", "lote",
    "tasa_cambio",
    "proveedor", "compra", "compra_detalle", "pago_proveedor",
    "movimiento_inventario", "motivo_perdida", "perdida", "ajuste_inventario",
    "caja_sesion", "cliente", "venta", "venta_detalle", "venta_pago",
    "gasto_operativo",
}


@pytest.fixture
def conexion(tmp_path):
    con = abrir(tmp_path / "prueba.db")
    yield con
    con.close()


def nombres(conexion, tipo):
    filas = conexion.execute(
        "SELECT name FROM sqlite_master WHERE type = ? AND name NOT LIKE 'sqlite_%'",
        (tipo,),
    ).fetchall()
    return {fila["name"] for fila in filas}


class TestApertura:
    def test_crea_las_23_tablas(self, conexion):
        assert nombres(conexion, "table") - {"sqlite_sequence"} == TABLAS
        assert len(TABLAS) == 23

    def test_crea_las_vistas(self, conexion):
        assert nombres(conexion, "view") == {"v_existencia", "v_ultimo_costo"}

    def test_modo_wal(self, conexion):
        assert conexion.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

    def test_claves_foraneas_activas(self, conexion):
        assert conexion.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def test_reabrir_no_duplica_datos_iniciales(self, tmp_path):
        ruta = tmp_path / "prueba.db"
        abrir(ruta).close()
        con = abrir(ruta)
        esperado = {
            "alicuota_iva": 3,
            "motivo_perdida": 5,
            "configuracion": 10,
            "usuario": 1,
        }
        for tabla, cuantos in esperado.items():
            assert con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0] == cuantos
        con.close()


class TestDatosIniciales:
    def test_alicuotas_escaladas_por_cien(self, conexion):
        filas = dict(
            conexion.execute("SELECT codigo, porcentaje FROM alicuota_iva").fetchall()
        )
        assert filas == {"EXENTO": 0, "GENERAL": 1600, "REDUCIDA": 800}

    def test_usuario_de_arranque_sin_clave(self, conexion):
        fila = conexion.execute(
            "SELECT rol, hash_clave FROM usuario WHERE usuario = 'admin'"
        ).fetchone()
        assert fila["rol"] == "ADMIN"
        assert fila["hash_clave"] == ""


class TestRestricciones:
    def test_rechaza_clave_foranea_inexistente(self, conexion):
        conexion.execute("INSERT INTO categoria (nombre) VALUES ('Viveres')")
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            conexion.execute(
                "INSERT INTO producto (nombre, categoria_id, alicuota_iva_id)"
                " VALUES ('Fantasma', 999, 1)"
            )

    def test_rechaza_movimiento_con_cantidad_cero(self, conexion):
        with pytest.raises(sqlite3.IntegrityError):
            conexion.execute(
                "INSERT INTO movimiento_inventario"
                " (producto_id, tipo, cantidad, referencia_tipo, referencia_id, usuario_id)"
                " VALUES (1, 'AJUSTE', 0, 'AJUSTE', 1, 1)"
            )

    def test_una_sola_tasa_por_fecha(self, conexion):
        conexion.execute(
            "INSERT INTO tasa_cambio (fecha, valor, origen)"
            " VALUES ('2026-08-29', 210500000, 'MANUAL')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conexion.execute(
                "INSERT INTO tasa_cambio (fecha, valor, origen)"
                " VALUES ('2026-08-29', 211000000, 'BCV_AUTO')"
            )

    def test_una_sola_caja_abierta(self, conexion):
        abrir_caja = "INSERT INTO caja_sesion (usuario_apertura_id) VALUES (1)"
        conexion.execute(abrir_caja)
        with pytest.raises(sqlite3.IntegrityError):
            conexion.execute(abrir_caja)

    def test_se_puede_abrir_caja_de_nuevo_tras_cerrar(self, conexion):
        abrir_caja = "INSERT INTO caja_sesion (usuario_apertura_id) VALUES (1)"
        conexion.execute(abrir_caja)
        conexion.execute("UPDATE caja_sesion SET estado = 'CERRADA' WHERE id = 1")
        conexion.execute(abrir_caja)
        assert conexion.execute("SELECT COUNT(*) FROM caja_sesion").fetchone()[0] == 2

    def test_varios_productos_sin_codigo_de_barras(self, conexion):
        conexion.execute("INSERT INTO categoria (nombre) VALUES ('Viveres')")
        for nombre in ("Suelto A", "Suelto B"):
            conexion.execute(
                "INSERT INTO producto (nombre, categoria_id, alicuota_iva_id)"
                " VALUES (?, 1, 1)",
                (nombre,),
            )
        assert conexion.execute("SELECT COUNT(*) FROM producto").fetchone()[0] == 2


class TestTransaccion:
    def test_confirma_al_salir_sin_error(self, conexion):
        with transaccion(conexion):
            conexion.execute("INSERT INTO categoria (nombre) VALUES ('Bebidas')")
        assert conexion.execute("SELECT COUNT(*) FROM categoria").fetchone()[0] == 1

    def test_deshace_todo_si_algo_falla(self, conexion):
        with pytest.raises(RuntimeError):
            with transaccion(conexion):
                conexion.execute("INSERT INTO categoria (nombre) VALUES ('Bebidas')")
                conexion.execute("INSERT INTO categoria (nombre) VALUES ('Limpieza')")
                raise RuntimeError("corte de energia")
        assert conexion.execute("SELECT COUNT(*) FROM categoria").fetchone()[0] == 0


class TestVistas:
    def test_existencia_es_la_suma_de_los_movimientos(self, conexion):
        with transaccion(conexion):
            conexion.execute("INSERT INTO categoria (nombre) VALUES ('Viveres')")
            conexion.execute(
                "INSERT INTO producto (nombre, categoria_id, alicuota_iva_id)"
                " VALUES ('Harina', 1, 1)"
            )
            for cantidad in (20_000, -4_000, -1_000):
                conexion.execute(
                    "INSERT INTO movimiento_inventario"
                    " (producto_id, tipo, cantidad, referencia_tipo, referencia_id,"
                    "  usuario_id) VALUES (1, 'AJUSTE', ?, 'AJUSTE', 1, 1)",
                    (cantidad,),
                )
        fila = conexion.execute("SELECT * FROM v_existencia").fetchone()
        assert fila["existencia"] == 15_000  # x1000 -> 15,000 unidades

    def test_producto_sin_movimientos_tiene_existencia_cero(self, conexion):
        with transaccion(conexion):
            conexion.execute("INSERT INTO categoria (nombre) VALUES ('Viveres')")
            conexion.execute(
                "INSERT INTO producto (nombre, categoria_id, alicuota_iva_id)"
                " VALUES ('Harina', 1, 1)"
            )
        assert conexion.execute("SELECT * FROM v_existencia").fetchone()["existencia"] == 0

    def test_ultimo_costo_toma_la_compra_confirmada_mas_reciente(self, conexion):
        with transaccion(conexion):
            conexion.execute("INSERT INTO categoria (nombre) VALUES ('Viveres')")
            conexion.execute(
                "INSERT INTO producto (nombre, categoria_id, alicuota_iva_id)"
                " VALUES ('Harina', 1, 1)"
            )
            conexion.execute("INSERT INTO proveedor (nombre) VALUES ('Distribuidora')")
            conexion.execute(
                "INSERT INTO tasa_cambio (fecha, valor, origen)"
                " VALUES ('2026-08-29', 210500000, 'MANUAL')"
            )
            compras = [
                ("2026-08-01", "CONFIRMADA", 6000),
                ("2026-08-20", "CONFIRMADA", 6500),  # la mas reciente confirmada
                ("2026-08-25", "ANULADA", 9900),  # se excluye (RN-07)
            ]
            for fecha, estado, costo in compras:
                cur = conexion.execute(
                    "INSERT INTO compra (proveedor_id, fecha, tasa_id, estado, usuario_id)"
                    " VALUES (1, ?, 1, ?, 1)",
                    (fecha, estado),
                )
                conexion.execute(
                    "INSERT INTO compra_detalle (compra_id, producto_id,"
                    " cant_presentacion, unid_x_presentacion, cantidad_unidades,"
                    " costo_present_usd, costo_unitario_usd)"
                    " VALUES (?, 1, 1000, 20000, 20000, 120000, ?)",
                    (cur.lastrowid, costo),
                )
        fila = conexion.execute("SELECT * FROM v_ultimo_costo").fetchone()
        assert fila["costo_unitario_usd"] == 6500  # x10000 -> 0,6500 USD
