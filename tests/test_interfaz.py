"""Prueba de humo de la interfaz: toda pantalla se construye y se refresca.

No prueba comportamiento —eso lo hacen los tests de servicios— sino que las
pantallas arman, con la hoja de estilo puesta, sobre una base con datos, y que
cada pestana refresca sin excepcion. Es lo que rompe cuando se renombra un
servicio o se cambia una firma y ninguna prueba de dominio se entera.

Corre con `QT_QPA_PLATFORM=offscreen`: sin ventanas, sin pantalla, en CI.
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from herramientas import demostracion  # noqa: E402
from minimarket.datos.conexion import abrir  # noqa: E402
from minimarket.servicios import cerrar_sesion, iniciar_sesion  # noqa: E402
from minimarket.servicios import usuarios as servicio_usuarios  # noqa: E402
from minimarket.ui import estilo  # noqa: E402


@pytest.fixture(scope="module")
def aplicacion():
    instancia = QApplication.instance() or QApplication(sys.argv)
    estilo.aplicar(instancia)
    return instancia


@pytest.fixture(scope="module")
def base_demo(tmp_path_factory):
    """La misma base de capacitacion: la interfaz se prueba con datos reales."""
    ruta = demostracion.construir(tmp_path_factory.mktemp("demo") / "demo.db")
    conexion = abrir(ruta)
    iniciar_sesion(servicio_usuarios.obtener(conexion, 1))
    yield conexion
    cerrar_sesion()
    conexion.close()


def test_la_ventana_principal_arma_todas_las_pestanas(aplicacion, base_demo):
    from minimarket.ui.principal import VentanaPrincipal

    ventana = VentanaPrincipal(base_demo, servicio_usuarios.obtener(base_demo, 1))
    titulos = [
        ventana.pestanas.tabText(i).split(" (")[0].replace("&", "")
        for i in range(ventana.pestanas.count())
    ]
    assert titulos == [
        "Inicio", "Venta", "Productos", "Categorias", "Compras", "Proveedores",
        "Existencias", "Perdidas", "Gastos", "Reportes", "Usuarios",
    ]
    for indice in range(ventana.pestanas.count()):
        ventana.pestanas.setCurrentIndex(indice)  # dispara `refrescar`
    assert "Tasa de hoy" in ventana.statusBar().currentMessage()


def test_el_cajero_no_ve_las_pestanas_del_administrador(aplicacion, base_demo):
    """RF-58 en la interfaz: al cajero no le aparecen compras ni catalogo.

    Reportes si: el cierre de su propia caja es suyo (REPORTE_CIERRE), y
    adentro la pantalla esconde los que piden VER_REPORTES.
    """
    from minimarket.ui.principal import VentanaPrincipal

    cajera = servicio_usuarios.obtener(base_demo, 2)
    ventana = VentanaPrincipal(base_demo, cajera)
    titulos = {
        ventana.pestanas.tabText(i).split(" (")[0].replace("&", "")
        for i in range(ventana.pestanas.count())
    }
    assert titulos == {"Venta", "Existencias", "Reportes"}


def test_el_punto_de_venta_arma_una_venta_desde_el_lector(aplicacion, base_demo):
    from minimarket.ui.venta import DialogoCobro, PantallaVenta

    pantalla = PantallaVenta(base_demo)
    for entrada in ("7591001000018", "2*7591003000016", "0.750*7591002000017"):
        pantalla.codigo.setText(entrada)
        pantalla.agregar()
    assert pantalla.tabla.rowCount() == 3
    assert pantalla.total_bs.text().startswith("Bs ")
    assert pantalla.codigo.text() == ""  # el foco vuelve limpio para el lector

    cobro = DialogoCobro(pantalla._venta_en_curso())
    assert "FALTA" in cobro.saldo.text()


def test_los_dialogos_se_construyen(aplicacion, base_demo):
    """Los que no cuelgan de una pestana: ingreso, tasa, configuracion, caja."""
    from minimarket.ui.asistente import AsistentePrimerArranque
    from minimarket.ui.configuracion import DialogoConfiguracion
    from minimarket.ui.tasa import DialogoTasa
    from minimarket.ui.usuarios import DialogoIngreso
    from minimarket.ui.venta import DialogoApertura

    admin = servicio_usuarios.obtener(base_demo, 1)
    for dialogo in (
        DialogoIngreso(base_demo),
        DialogoTasa(base_demo),
        DialogoConfiguracion(base_demo),
        DialogoApertura(base_demo),
        AsistentePrimerArranque(base_demo, admin),
    ):
        assert isinstance(dialogo, QDialog)
        assert dialogo.windowTitle()


def test_el_ingreso_rechaza_la_clave_mala_y_acepta_la_buena(
    aplicacion, base_demo, monkeypatch
):
    from minimarket.ui import usuarios as ui_usuarios

    avisos = []
    monkeypatch.setattr(ui_usuarios, "avisar", lambda *a: avisos.append(a[1]))
    dialogo = ui_usuarios.DialogoIngreso(base_demo)
    dialogo.nombre.setText("admin")
    dialogo.clave.setText("no-es")
    dialogo.entrar()
    assert dialogo.usuario is None and avisos == ["Usuario o clave incorrectos."]

    dialogo.clave.setText(demostracion.CLAVE_ADMIN)
    dialogo.entrar()
    assert dialogo.usuario is not None and dialogo.usuario.usuario == "admin"


def test_los_dialogos_de_carga_registran_de_verdad(aplicacion, base_demo, monkeypatch):
    """Los caminos que el cliente recorre y que armar la pantalla no ejercita.

    El primer dia en produccion revento `agregar_linea` de compras con un
    `NameError`: la pantalla armaba bien y el import faltante solo se usaba
    al agregar. Aca cada dialogo de carga se llena y se confirma.
    """
    from minimarket.datos.repositorios import producto as repo_producto
    from minimarket.servicios import inventario as servicio_inventario
    from minimarket.ui import compras as ui_compras
    from minimarket.ui import inventario as ui_inventario
    from minimarket.ui import perdidas as ui_perdidas

    avisos = []
    for modulo in (ui_compras, ui_inventario, ui_perdidas):
        monkeypatch.setattr(modulo, "avisar", lambda *a: avisos.append(a[1]))
    harina = repo_producto.por_codigo_barras(base_demo, "7591001000018")
    antes = servicio_inventario.existencia(base_demo, harina.id)

    # Compra: una linea agregada desde los campos, como con el teclado.
    compra = ui_compras.DialogoCompra(base_demo, None)
    compra.producto.setCurrentIndex(compra.producto.findData(harina.id))
    compra.presentaciones.setText("2")
    compra.unidades.setText("12")
    compra.costo.setText("10,80")
    compra.agregar_linea()
    assert compra.tabla.rowCount() == 1
    assert compra.tabla.item(0, 0).text() == harina.nombre
    compra.confirmar()
    assert servicio_inventario.existencia(base_demo, harina.id) == antes + 24

    # Perdida.
    perdida = ui_perdidas.DialogoPerdida(base_demo)
    perdida.producto.setCurrentIndex(perdida.producto.findData(harina.id))
    perdida.cantidad.setText("1")
    perdida.guardar()
    assert servicio_inventario.existencia(base_demo, harina.id) == antes + 23

    # Ajuste por conteo fisico.
    fila = next(
        f for f in servicio_inventario.consultar(base_demo) if f.producto_id == harina.id
    )
    ajuste = ui_inventario.DialogoAjuste(base_demo, fila)
    ajuste.contada.setText(str(fila.existencia - 3))
    ajuste.motivo.setText("Conteo de prueba")
    ajuste.guardar()
    assert servicio_inventario.existencia(base_demo, harina.id) == antes + 20

    assert avisos == [], avisos


def test_el_inicio_dice_si_los_margenes_cubren_los_gastos(aplicacion, base_demo):
    """El panel nuevo: con la demo hay ventas y un alquiler de 350 USD."""
    from minimarket.ui.inicio import PantallaInicio

    pantalla = PantallaInicio(base_demo)
    assert "cubren los gastos" in pantalla.equilibrio_titulo.title()
    assert "margen bruto" in pantalla.equilibrio_margen.text()
    veredicto = pantalla.equilibrio_veredicto.text()
    assert "Al mismo ritmo" in veredicto and "USD" in veredicto


def test_las_pantallas_nuevas_de_la_1_2_0(aplicacion, base_demo):
    """Gastos con recurrentes, el dialogo del margen, ventas del dia y el cierre."""
    from minimarket.servicios import caja as servicio_caja
    from minimarket.ui.gastos import DialogoGastoRecurrente, PantallaGastos
    from minimarket.ui.productos import DialogoMargenSugerido, PantallaProductos
    from minimarket.ui.reportes import PantallaReportes
    from minimarket.ui.venta import DialogoCierre

    gastos = PantallaGastos(base_demo)
    assert gastos.tabla_recurrentes.rowCount() == 2  # alquiler + punto (demo)
    origenes = {gastos.tabla_mes.item(i, 3).text() for i in range(gastos.tabla_mes.rowCount())}
    assert "fijo mensual" in origenes and "cargado" in origenes
    assert DialogoGastoRecurrente(base_demo).windowTitle()

    productos = PantallaProductos(base_demo)
    encabezados = [productos.tabla.horizontalHeaderItem(i).text() for i in range(productos.tabla.columnCount())]
    assert "Margen %" in encabezados
    dialogo = DialogoMargenSugerido(base_demo)
    assert "Margen minimo para no perder" in dialogo.explicacion.text()
    assert dialogo.plan is not None and dialogo.margen.text()

    reportes = PantallaReportes(base_demo)
    reportes.tipo.setCurrentIndex(0)  # «Ventas del dia»
    reportes.generar()
    assert reportes.tabla.columnCount() == 3 and reportes.tabla.rowCount() > 0
    assert "Cobrado" in reportes.resumen.text()

    sesion = servicio_caja.sesion_abierta(base_demo)
    cierre = DialogoCierre(base_demo, sesion.id)
    assert cierre.vendido.rowCount() > 0
    assert "Punto" in cierre.cobrado.text()
