"""RNF-03: la busqueda responde en menos de un segundo sobre 3.000 productos."""

import time

import pytest

from minimarket.servicios import catalogo
from tests.datos_prueba import cargar

LIMITE_SEGUNDOS = 1.0


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
