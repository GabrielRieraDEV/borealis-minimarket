"""Fase 6: bitacora de errores (RNF-13) y carga inicial del catalogo.

Lo que se verifica es lo que puede romperse en silencio: que un error no
controlado quede escrito en vez de tumbar la aplicacion, y que la importacion
no cargue medio archivo cuando una fila esta mal.
"""

import logging
import sys
from decimal import Decimal

import pytest

from minimarket.datos.repositorios import producto as repo_producto
from minimarket.infra import bitacora, rutas
from minimarket.servicios import catalogo


# --- RNF-13: bitacora en archivo --------------------------------------------


@pytest.fixture
def bitacora_temporal(tmp_path):
    """Deja `logging` y el excepthook como estaban: son estado global."""
    anterior = sys.excepthook
    handlers = logging.root.handlers[:]
    nivel = logging.root.level
    archivo = tmp_path / "registro" / "minimarket.log"
    yield bitacora.configurar(archivo), archivo
    for handler in logging.root.handlers:
        handler.close()
    logging.root.handlers[:] = handlers
    logging.root.setLevel(nivel)
    sys.excepthook = anterior


def test_la_bitacora_crea_su_carpeta_y_escribe(bitacora_temporal):
    _, archivo = bitacora_temporal
    logging.getLogger("minimarket.prueba").error("algo salio mal")
    assert archivo.is_file()
    assert "algo salio mal" in archivo.read_text(encoding="utf-8")


def test_una_excepcion_no_controlada_se_anota_y_no_propaga(bitacora_temporal):
    """RNF-13. El manejador registra y devuelve: la aplicacion sigue viva."""
    _, archivo = bitacora_temporal
    try:
        raise ValueError("reventon inesperado")
    except ValueError:
        sys.excepthook(*sys.exc_info())  # lo que haria Qt con un slot que falla
    escrito = archivo.read_text(encoding="utf-8")
    assert "Error no controlado" in escrito
    assert "reventon inesperado" in escrito  # con la traza, para el diagnostico
    assert "Traceback" in escrito


def test_anotar_guarda_el_detalle_tecnico_que_no_se_muestra(bitacora_temporal):
    """RNF-09. Al usuario se le dice que hacer; aca queda el porque."""
    _, archivo = bitacora_temporal
    bitacora.anotar("Fallo el respaldo", OSError("disco lleno"))
    assert "disco lleno" in archivo.read_text(encoding="utf-8")


def test_la_bitacora_vive_al_lado_de_la_base(monkeypatch, tmp_path):
    monkeypatch.setenv("MINIMARKET_DB", str(tmp_path / "otra.db"))
    assert rutas.bitacora() == tmp_path / "minimarket.log"


# --- Carga inicial del catalogo desde CSV -----------------------------------

ENCABEZADO = ",".join(catalogo.COLUMNAS_CSV)


def escribir(tmp_path, *filas: str):
    archivo = tmp_path / "catalogo.csv"
    archivo.write_text("\n".join([ENCABEZADO, *filas]) + "\n", encoding="utf-8")
    return str(archivo)


def test_importa_las_filas_validas_con_sus_decimales(conexion, categoria, tmp_path):
    ruta = escribir(
        tmp_path,
        "Harina de maiz,Viveres,GENERAL,1.2000,7591234567890,,10,0,15",
        "Queso blanco,Viveres,EXENTO,3,5,,0,si,7",
    )
    resultado = catalogo.importar_csv(conexion, ruta)
    assert (resultado.creados, resultado.errores) == (2, [])

    harina, queso = sorted(
        repo_producto.listar(conexion), key=lambda p: p.nombre
    )
    assert harina.precio_venta_usd == Decimal("1.2000")
    assert harina.codigo_barras == "7591234567890"
    assert harina.existencia_minima == Decimal(10)
    assert not harina.maneja_vencimiento
    assert queso.maneja_vencimiento and queso.dias_alerta_venc == 7


def test_acepta_la_coma_decimal_como_el_resto_de_la_interfaz(
    conexion, categoria, tmp_path
):
    """El Excel en español escribe «1,20»; rechazarlo seria pelearse con todos."""
    ruta = escribir(tmp_path, '"Harina","Viveres","GENERAL","1,20",,,,,')
    assert catalogo.importar_csv(conexion, ruta).creados == 1
    assert repo_producto.listar(conexion)[0].precio_venta_usd == Decimal("1.20")


def test_una_fila_mala_no_carga_ninguna(conexion, categoria, tmp_path):
    """Todo o nada: si entrara la mitad, la segunda pasada duplicaria."""
    ruta = escribir(
        tmp_path,
        "Harina,Viveres,GENERAL,1.20,,,,,",
        "Arroz,Panaderia,GENERAL,1.00,,,,,",
        ",Viveres,GENERAL,1.00,,,,,",
        "Azucar,Viveres,GENERAL,ochenta,,,,,",
    )
    resultado = catalogo.importar_csv(conexion, ruta)
    assert resultado.creados == 0
    assert repo_producto.listar(conexion) == []
    assert len(resultado.errores) == 3
    assert "Fila 3" in resultado.errores[0] and "Panaderia" in resultado.errores[0]
    assert "Fila 4" in resultado.errores[1] and "nombre" in resultado.errores[1]
    assert "Fila 5" in resultado.errores[2]


def test_el_codigo_repetido_dentro_del_archivo_se_detecta(
    conexion, categoria, tmp_path
):
    ruta = escribir(
        tmp_path,
        "Harina,Viveres,GENERAL,1.20,7591234567890,,,,",
        "Harina otra marca,Viveres,GENERAL,1.30,7591234567890,,,,",
    )
    resultado = catalogo.importar_csv(conexion, ruta)
    assert resultado.creados == 0
    assert "Fila 3" in resultado.errores[0] and "fila 2" in resultado.errores[0]


def test_el_codigo_ya_usado_en_la_base_corta_la_importacion(
    conexion, categoria, general, tmp_path
):
    from tests.conftest import alta

    alta(conexion, categoria, general, codigo_barras="7591234567890")
    ruta = escribir(tmp_path, "Harina,Viveres,GENERAL,1.20,7591234567890,,,,")
    with pytest.raises(catalogo.ErrorCatalogo, match="ya esta en uso"):
        catalogo.importar_csv(conexion, ruta)
    assert len(repo_producto.listar(conexion)) == 1


def test_un_archivo_sin_las_columnas_esperadas_lo_dice(conexion, tmp_path):
    archivo = tmp_path / "otro.csv"
    archivo.write_text("producto;precio\nHarina;1.20\n", encoding="utf-8")
    with pytest.raises(catalogo.ErrorCatalogo, match="faltan columnas"):
        catalogo.importar_csv(conexion, str(archivo))


def test_la_plantilla_se_puede_importar_tal_como_sale(conexion, categoria, tmp_path):
    """La fila de ejemplo tiene que ser valida, o la plantilla no sirve."""
    archivo = tmp_path / "plantilla.csv"
    archivo.write_text(catalogo.plantilla_csv(), encoding="utf-8-sig")
    assert catalogo.importar_csv(conexion, str(archivo)).creados == 1
