"""Autenticacion, permisos y bitacora (RF-56 a RF-60)."""

import json
from decimal import Decimal

import pytest

from minimarket.datos.repositorios import usuario as repo_usuario
from minimarket.dominio.usuario import (
    ADMIN,
    CAJERO,
    REGISTRAR_COMPRAS,
    REPORTES_GANANCIA,
    VENDER,
    VER_COSTOS,
    Usuario,
    hashear_clave,
    puede,
    verificar_clave,
)
from minimarket.dominio.venta import Venta
from minimarket.infra import auditoria
from minimarket.servicios import (
    cerrar_sesion,
    iniciar_sesion,
    usuario_actual,
    usuarios as servicio_usuarios,
)
from minimarket.servicios import caja as servicio_caja
from minimarket.servicios import catalogo
from minimarket.servicios import compras as servicio_compras
from minimarket.servicios import inventario as servicio_inventario
from minimarket.servicios import reportes as servicio_reportes
from minimarket.servicios import tasa as servicio_tasa
from minimarket.servicios import venta as servicio_venta
from tests.conftest import USUARIO_SEMILLA, alta, cargar_tasa, registrar_compra


@pytest.fixture(autouse=True)
def sin_sesion():
    """Cada prueba arranca sin sesion: el default es el `admin` semilla."""
    cerrar_sesion()
    yield
    cerrar_sesion()


@pytest.fixture
def cajero(conexion) -> Usuario:
    identificador = servicio_usuarios.crear(
        conexion, Usuario(usuario="cajera", nombre="Cajera", rol=CAJERO), "clave1234"
    )
    return repo_usuario.obtener(conexion, identificador)


# --- Clave (RF-60) ----------------------------------------------------------


def test_rf60_la_clave_se_guarda_derivada_con_sal():
    primero = hashear_clave("clave1234")
    segundo = hashear_clave("clave1234")
    assert primero != segundo  # sal distinta en cada derivacion
    assert "clave1234" not in primero
    assert primero.startswith("scrypt$")
    assert verificar_clave("clave1234", primero)
    assert verificar_clave("clave1234", segundo)
    assert not verificar_clave("clave1233", primero)


def test_un_hash_vacio_o_corrupto_nunca_autentica():
    assert not verificar_clave("clave1234", "")
    assert not verificar_clave("clave1234", "md5$loquesea")
    assert not verificar_clave("clave1234", "scrypt$1$2$3$zz$zz")


# --- Autenticacion (RF-56) --------------------------------------------------


def test_rf56_el_admin_semilla_no_entra_hasta_tener_clave(conexion):
    semilla = servicio_usuarios.necesita_clave_inicial(conexion)
    assert semilla is not None and semilla.usuario == "admin"
    with pytest.raises(servicio_usuarios.ErrorUsuario):
        servicio_usuarios.autenticar(conexion, "admin", "")

    servicio_usuarios.establecer_clave_inicial(conexion, "clave1234")
    assert servicio_usuarios.necesita_clave_inicial(conexion) is None
    usuario = servicio_usuarios.autenticar(conexion, "admin", "clave1234")
    assert usuario.rol == ADMIN
    assert usuario_actual() == usuario.id


def test_el_mensaje_de_error_no_distingue_usuario_de_clave(conexion, cajero):
    with pytest.raises(servicio_usuarios.ErrorUsuario) as inexistente:
        servicio_usuarios.autenticar(conexion, "nadie", "clave1234")
    with pytest.raises(servicio_usuarios.ErrorUsuario) as equivocada:
        servicio_usuarios.autenticar(conexion, "cajera", "otraclave")
    assert str(inexistente.value) == str(equivocada.value)


def test_un_usuario_de_baja_no_autentica(conexion, cajero):
    servicio_usuarios.cambiar_estado(conexion, cajero.id, activo=False)
    with pytest.raises(servicio_usuarios.ErrorUsuario):
        servicio_usuarios.autenticar(conexion, "cajera", "clave1234")


def test_verificar_no_cambia_la_sesion_en_curso(conexion, cajero):
    """RN-25. El administrador autoriza y el cajero sigue operando."""
    iniciar_sesion(cajero)
    servicio_usuarios.establecer_clave_inicial(conexion, "clave1234")
    autorizante = servicio_usuarios.verificar(conexion, "admin", "clave1234")
    assert autorizante.rol == ADMIN
    assert usuario_actual() == cajero.id


# --- Permisos (RF-57, RF-58) ------------------------------------------------


def test_rf57_la_tabla_de_permisos_es_la_seccion_6():
    assert puede(ADMIN, VER_COSTOS) and not puede(CAJERO, VER_COSTOS)
    assert puede(ADMIN, REGISTRAR_COMPRAS) and not puede(CAJERO, REGISTRAR_COMPRAS)
    assert puede(ADMIN, REPORTES_GANANCIA) and not puede(CAJERO, REPORTES_GANANCIA)
    assert puede(ADMIN, VENDER) and puede(CAJERO, VENDER)
    assert not puede(CAJERO, "OPERACION_INVENTADA")


def test_rf58_el_cajero_no_puede_invocar_los_servicios_restringidos(
    conexion, cajero, categoria, exento
):
    producto = alta(conexion, categoria, exento)
    registrar_compra(conexion, producto.id, Decimal("0.6000"))
    iniciar_sesion(cajero)

    restringidas = [
        lambda: catalogo.crear_producto(conexion, producto),
        lambda: catalogo.modificar_producto(conexion, producto),
        lambda: catalogo.calcular_precio(conexion, producto),
        lambda: catalogo.calcular_margen(conexion, producto),
        lambda: catalogo.previsualizar_recalculo(conexion, categoria.id),
        lambda: catalogo.aplicar_recalculo(conexion, []),
        lambda: catalogo.guardar_categoria(conexion, categoria),
        lambda: servicio_compras.registrar_compra(conexion, None),
        lambda: servicio_inventario.ajustar_por_conteo(
            conexion, producto.id, Decimal(1), "conteo"
        ),
        lambda: servicio_tasa.registrar_manual(conexion, Decimal(200)),
        lambda: servicio_reportes.ganancia_por_producto(
            conexion, "2026-01-01", "2026-12-31"
        ),
        lambda: servicio_reportes.libro_de_ventas(conexion, "2026-01-01", "2026-12-31"),
        lambda: servicio_usuarios.listar(conexion),
    ]
    for operacion in restringidas:
        with pytest.raises(servicio_usuarios.ErrorPermiso):
            operacion()


def test_rf58_el_cajero_ve_existencias_pero_no_costos(
    conexion, cajero, categoria, exento
):
    producto = alta(conexion, categoria, exento)
    registrar_compra(conexion, producto.id, Decimal("0.6000"), unidades=Decimal(10))

    como_admin = servicio_inventario.consultar(conexion)
    assert como_admin[0].ultimo_costo == Decimal("0.6000")

    iniciar_sesion(cajero)
    como_cajero = servicio_inventario.consultar(conexion)
    assert como_cajero[0].existencia == como_admin[0].existencia
    assert como_cajero[0].ultimo_costo is None


def test_el_cajero_si_puede_vender_y_operar_la_caja(
    conexion, cajero, categoria, exento
):
    producto = alta(conexion, categoria, exento, precio_venta_usd=Decimal("2.0000"))
    registrar_compra(conexion, producto.id, Decimal("1.0000"), unidades=Decimal(10))
    cargar_tasa(conexion, servicio_tasa.hoy())

    iniciar_sesion(cajero)
    servicio_caja.abrir(conexion)
    venta = Venta(usuario_id=cajero.id, tasa=Decimal(0))
    venta.lineas = [servicio_venta.nueva_linea(conexion, producto.id, Decimal(2))]
    venta.pagos = [servicio_venta.pago("EFECTIVO", "USD", Decimal(4), Decimal(1))]
    registrada = servicio_venta.registrar_venta(conexion, venta)
    assert registrada.id is not None
    assert registrada.usuario_id == cajero.id


def test_rn25_el_cajero_anula_solo_con_autorizacion(
    conexion, cajero, categoria, exento
):
    producto = alta(conexion, categoria, exento, precio_venta_usd=Decimal("2.0000"))
    registrar_compra(conexion, producto.id, Decimal("1.0000"), unidades=Decimal(10))
    cargar_tasa(conexion, servicio_tasa.hoy())
    servicio_caja.abrir(conexion)
    venta = Venta(usuario_id=USUARIO_SEMILLA, tasa=Decimal(0))
    venta.lineas = [servicio_venta.nueva_linea(conexion, producto.id, Decimal(2))]
    venta.pagos = [servicio_venta.pago("EFECTIVO", "USD", Decimal(4), Decimal(1))]
    servicio_venta.registrar_venta(conexion, venta)

    iniciar_sesion(cajero)
    with pytest.raises(servicio_venta.ErrorVenta, match="autorizacion"):
        servicio_venta.anular_venta(conexion, venta.id, "error de carga")

    servicio_venta.anular_venta(
        conexion, venta.id, "error de carga", autorizado_por=USUARIO_SEMILLA
    )
    assert servicio_venta.obtener(conexion, venta.id).estado == "ANULADA"


# --- Gestion (RF-57) --------------------------------------------------------


def test_no_se_puede_dejar_al_sistema_sin_administrador(conexion):
    admin = repo_usuario.obtener(conexion, USUARIO_SEMILLA)
    admin.rol = CAJERO
    with pytest.raises(servicio_usuarios.ErrorUsuario, match="unico administrador"):
        servicio_usuarios.modificar(conexion, admin)

    otro = servicio_usuarios.crear(
        conexion, Usuario(usuario="jefa", nombre="Jefa", rol=ADMIN), "clave1234"
    )
    servicio_usuarios.modificar(conexion, admin)  # ya hay otro admin activo
    assert repo_usuario.obtener(conexion, otro).rol == ADMIN
    assert repo_usuario.obtener(conexion, USUARIO_SEMILLA).rol == CAJERO


def test_el_usuario_repetido_no_se_crea_dos_veces(conexion, cajero):
    with pytest.raises(servicio_usuarios.ErrorUsuario, match="Ya existe"):
        servicio_usuarios.crear(
            conexion, Usuario(usuario="cajera", nombre="Otra", rol=CAJERO), "clave1234"
        )


def test_la_clave_corta_se_rechaza(conexion):
    with pytest.raises(servicio_usuarios.ErrorUsuario, match="caracteres"):
        servicio_usuarios.crear(
            conexion, Usuario(usuario="corta", nombre="Corta"), "123"
        )


def test_cada_uno_cambia_su_propia_clave_sin_ser_administrador(conexion, cajero):
    iniciar_sesion(cajero)
    servicio_usuarios.cambiar_clave(conexion, cajero.id, "nuevaclave")
    nueva = servicio_usuarios.autenticar(conexion, "cajera", "nuevaclave")
    assert nueva.id == cajero.id


def test_el_cajero_no_le_cambia_la_clave_a_otro(conexion, cajero):
    iniciar_sesion(cajero)
    with pytest.raises(servicio_usuarios.ErrorPermiso):
        servicio_usuarios.cambiar_clave(conexion, USUARIO_SEMILLA, "nuevaclave")


# --- Bitacora (RF-59) -------------------------------------------------------


def test_rf59_las_operaciones_sensibles_quedan_en_la_bitacora(
    conexion, categoria, exento, cajero
):
    producto = alta(conexion, categoria, exento, precio_venta_usd=Decimal("2.0000"))
    registrar_compra(conexion, producto.id, Decimal("1.0000"), unidades=Decimal(10))

    producto.precio_venta_usd = Decimal("3.0000")  # cambio de precio
    catalogo.modificar_producto(conexion, producto)
    servicio_inventario.ajustar_por_conteo(
        conexion, producto.id, Decimal(9), "faltante"
    )

    cargar_tasa(conexion, servicio_tasa.hoy())
    servicio_caja.abrir(conexion)
    venta = Venta(usuario_id=USUARIO_SEMILLA, tasa=Decimal(0))
    venta.lineas = [servicio_venta.nueva_linea(conexion, producto.id, Decimal(1))]
    venta.pagos = [servicio_venta.pago("EFECTIVO", "USD", Decimal(3), Decimal(1))]
    servicio_venta.registrar_venta(conexion, venta)
    servicio_venta.anular_venta(conexion, venta.id, "cliente se arrepintio")

    acciones = {a.accion for a in auditoria.listar(conexion)}
    assert {
        auditoria.ALTA_USUARIO,  # el cajero de la fixture
        auditoria.CAMBIO_PRECIO,
        auditoria.AJUSTE_INVENTARIO,
        auditoria.ANULACION_VENTA,
    } <= acciones


def test_la_bitacora_guarda_quien_y_que_cambio(conexion, categoria, exento):
    producto = alta(conexion, categoria, exento, precio_venta_usd=Decimal("2.0000"))
    producto.precio_venta_usd = Decimal("2.5000")
    catalogo.modificar_producto(conexion, producto)

    asiento = auditoria.listar(conexion, accion=auditoria.CAMBIO_PRECIO)[0]
    assert asiento.usuario == "admin"
    assert asiento.entidad_id == producto.id
    # Los importes se serializan como texto, nunca como float (regla 1).
    assert Decimal(json.loads(asiento.datos_antes)["precio_venta_usd"]) == Decimal(2)
    assert Decimal(json.loads(asiento.datos_despues)["precio_venta_usd"]) == Decimal(
        "2.5"
    )


def test_la_bitacora_se_revierte_con_la_operacion(conexion, categoria, exento):
    """El asiento viaja en la misma transaccion: si falla, no queda."""
    producto = alta(conexion, categoria, exento)
    with pytest.raises(servicio_inventario.ErrorInventario):
        servicio_inventario.ajustar_por_conteo(
            conexion, producto.id, Decimal(-1), "negativo"
        )
    assert auditoria.listar(conexion, accion=auditoria.AJUSTE_INVENTARIO) == []
