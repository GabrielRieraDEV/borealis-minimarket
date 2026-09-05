"""Base de demostracion para la capacitacion (punto 9 de la Fase 6).

    python -m herramientas.demostracion

Deja `~/Minimarket/demostracion.db` con un minimarket ya andando: catalogo,
proveedor, existencia con lotes por vencer, la caja del dia abierta, ventas
hechas, una perdida y un gasto. Sirve para que el cliente practique sin miedo:
si borra algo, se corre de nuevo y queda como estaba.

Para trabajar sobre ella, se arranca apuntando la variable de entorno a ese
archivo, que es lo que `infra/rutas.py` mira antes que nada:

    set MINIMARKET_DB=%USERPROFILE%\\Minimarket\\demostracion.db
    python -m minimarket

Sin la variable, la aplicacion abre la base real y esta ni se toca. Es aposta:
la unica forma de mezclar los datos de practica con los de verdad es escribir
la variable a mano.

No se reusa `tests/datos_prueba.py`: ese genera 3.000 productos con nombres
inventados para medir tiempos, y para capacitar hace falta lo contrario, un
punado de productos que el cajero reconozca.
"""

import sys
from decimal import Decimal
from pathlib import Path

from minimarket.datos.conexion import abrir
from minimarket.datos.repositorios import perdida as repo_perdida
from minimarket.dominio.compra import Compra, LineaCompra, Proveedor
from minimarket.dominio.producto import Categoria, Producto
from minimarket.dominio.reportes import ALQUILER, FIJO, OTROS, PORCENTAJE, SERVICIOS
from minimarket.dominio.usuario import CAJERO, Usuario
from minimarket.dominio.venta import EFECTIVO, PUNTO, Venta
from minimarket.infra import rutas
from minimarket.servicios import caja as servicio_caja
from minimarket.servicios import catalogo as servicio_catalogo
from minimarket.servicios import compras as servicio_compras
from minimarket.servicios import configuracion as servicio_configuracion
from minimarket.servicios import gastos as servicio_gastos
from minimarket.servicios import perdidas as servicio_perdidas
from minimarket.servicios import tasa as servicio_tasa
from minimarket.servicios import usuarios as servicio_usuarios
from minimarket.servicios import venta as servicio_venta

ARCHIVO = "demostracion.db"
CLAVE_ADMIN = "demo1234"
CLAVE_CAJERO = "caja1234"
TASA = Decimal("804.8109")  # la del BCV del 3 de septiembre de 2026

CATEGORIAS = [
    ("Viveres", Decimal(30)),
    ("Charcuteria", Decimal(35)),
    ("Bebidas", Decimal(35)),
    ("Limpieza", Decimal(45)),
    ("Hortalizas", Decimal(40)),
]

# (nombre, categoria, alicuota, precio con IVA en USD, codigo de barras,
#  existencia minima, costo unitario en USD, unidades compradas)
PRODUCTOS = [
    ("Harina de maiz precocida 1 kg", "Viveres", "EXENTO", "1.20", "7591001000018", 12, "0.90", 60),
    ("Arroz blanco 1 kg", "Viveres", "EXENTO", "1.45", "7591001000025", 12, "1.10", 60),
    ("Pasta larga 1 kg", "Viveres", "EXENTO", "1.30", "7591001000032", 10, "1.00", 48),
    ("Aceite de maiz 1 L", "Viveres", "GENERAL", "2.60", "7591001000049", 8, "1.95", 36),
    ("Azucar refinada 1 kg", "Viveres", "EXENTO", "1.15", "7591001000056", 10, "0.88", 48),
    # Comprado por debajo de su existencia minima aposta: asi el panel de
    # inicio tiene algo que avisar en «Productos por reponer» (RF-46).
    ("Cafe molido 250 g", "Viveres", "GENERAL", "2.10", "7591001000063", 6, "1.55", 4),
    ("Sal refinada 1 kg", "Viveres", "EXENTO", "0.55", "7591001000070", 6, "0.40", 24),
    ("Atun en aceite 140 g", "Viveres", "GENERAL", "1.80", "7591001000087", 8, "1.35", 36),
    ("Mayonesa 445 g", "Viveres", "GENERAL", "2.35", "7591001000094", 5, "1.75", 3),
    ("Queso blanco duro (kg)", "Charcuteria", "EXENTO", "5.40", "7591002000017", 3, "4.10", 20),
    ("Jamon de pierna (kg)", "Charcuteria", "GENERAL", "7.20", "7591002000024", 2, "5.40", 12),
    ("Mortadela (kg)", "Charcuteria", "GENERAL", "3.60", "7591002000031", 3, "2.70", 15),
    ("Leche en polvo 900 g", "Charcuteria", "EXENTO", "6.10", "7591002000048", 6, "4.70", 24),
    ("Refresco 2 L", "Bebidas", "GENERAL", "1.90", "7591003000016", 12, "1.40", 72),
    ("Agua mineral 1,5 L", "Bebidas", "GENERAL", "0.85", "7591003000023", 24, "0.60", 96),
    ("Malta 355 ml", "Bebidas", "GENERAL", "0.95", "7591003000030", 24, "0.70", 96),
    ("Jugo de naranja 1 L", "Bebidas", "GENERAL", "1.60", "7591003000047", 10, "1.20", 36),
    ("Detergente en polvo 1 kg", "Limpieza", "GENERAL", "2.40", "7591004000015", 8, "1.80", 30),
    ("Jabon de bano 110 g", "Limpieza", "GENERAL", "0.75", "7591004000022", 12, "0.55", 60),
    ("Cloro 1 L", "Limpieza", "GENERAL", "1.10", "7591004000039", 10, "0.80", 40),
    ("Papel higienico x4", "Limpieza", "GENERAL", "2.20", "7591004000046", 10, "1.65", 40),
    ("Tomate (kg)", "Hortalizas", "EXENTO", "1.70", "7591005000014", 5, "1.20", 25),
    ("Cebolla (kg)", "Hortalizas", "EXENTO", "1.40", "7591005000021", 5, "1.00", 25),
    ("Papa (kg)", "Hortalizas", "EXENTO", "1.25", "7591005000038", 8, "0.90", 40),
    ("Platano (kg)", "Hortalizas", "EXENTO", "0.95", "7591005000045", 8, "0.65", 30),
]

# Lo perecedero lleva lote y fecha de vencimiento, para que el panel de
# vencimientos (RF-31) y el reporte de proximos a vencer (RF-54) muestren algo.
PERECEDERAS = {"Charcuteria", "Hortalizas"}
# Dias desde hoy hasta el vencimiento de cada lote perecedero, en orden. Con
# los 7 dias de aviso configurados, los cuatro primeros avisan y el resto no.
DIAS_VENCIMIENTO = [2, 4, 5, 7, 12, 18, 25, 40]

# (indice del producto, unidades) de cada venta de practica.
VENTAS = [
    [(0, 2), (13, 1), (18, 1)],
    [(1, 1), (9, "0.750"), (21, "1.500")],
    [(3, 1), (5, 1), (14, 2)],
    [(10, "0.500"), (12, 1), (16, 1)],
    [(2, 3), (4, 2), (19, 1)],
    [(23, "2.000"), (24, "1.500"), (15, 4)],
    [(7, 2), (8, 1), (20, 1)],
    [(11, "0.400"), (22, "1.000"), (17, 1)],
]


def construir(destino: Path) -> Path:
    if destino.exists():
        destino.unlink()  # se rehace entera: es una base de practica
    conexion = abrir(destino)
    try:
        _usuarios(conexion)
        productos = _catalogo(conexion)
        servicio_tasa.registrar_manual(conexion, TASA)  # RF-11
        _compra(conexion, productos)
        _ventas(conexion, productos)
        _perdida_y_gasto(conexion, productos)
    finally:
        conexion.close()
    return destino


def _usuarios(conexion) -> None:
    """Lo que dejaria el asistente de primer arranque: clave y datos del negocio."""
    servicio_usuarios.establecer_clave_inicial(conexion, CLAVE_ADMIN)
    servicio_usuarios.crear(
        conexion,
        Usuario(usuario="maria", nombre="Maria Rodriguez", rol=CAJERO),
        CLAVE_CAJERO,
    )
    servicio_configuracion.guardar(
        conexion,
        {
            "negocio.nombre": "Provisiones Jireh C.A.",
            "negocio.rif": "J-508499557",
            "negocio.logo": str(Path("recursos/logo.png").resolve()),
        },
    )


def _catalogo(conexion) -> dict[str, int]:
    categorias = {
        nombre: servicio_catalogo.guardar_categoria(
            conexion, Categoria(None, nombre, margen)
        )
        for nombre, margen in CATEGORIAS
    }
    alicuotas = {a.codigo: a.id for a in servicio_catalogo.listar_alicuotas(conexion)}
    productos = {}
    for nombre, categoria, alicuota, precio, codigo, minima, _, _ in PRODUCTOS:
        productos[nombre] = servicio_catalogo.crear_producto(
            conexion,
            Producto(
                nombre=nombre,
                categoria_id=categorias[categoria],
                alicuota_iva_id=alicuotas[alicuota],
                precio_venta_usd=Decimal(precio),
                codigo_barras=codigo,
                existencia_minima=Decimal(minima),
                maneja_vencimiento=categoria in PERECEDERAS,
                dias_alerta_venc=7 if categoria in PERECEDERAS else 15,
            ),
        )
    return productos


def _compra(conexion, productos: dict[str, int]) -> None:
    """Una compra que deja existencia, costo (RN-07) y lotes por vencer."""
    proveedor = servicio_compras.guardar_proveedor(
        conexion,
        Proveedor(nombre="Distribuidora El Encanto", rif="J-402318765"),
    )
    hoy = servicio_tasa.hoy()
    lineas = []
    perecedero = 0
    for nombre, categoria, _, _, _, _, costo, unidades in PRODUCTOS:
        vencimiento = None
        if categoria in PERECEDERAS:
            # Escalonadas contra los 7 dias de aviso: las primeras entran en
            # alerta y las ultimas no, para que el panel muestre las dos cosas.
            vencimiento = _en_dias(hoy, DIAS_VENCIMIENTO[perecedero])
            perecedero += 1
        lineas.append(
            LineaCompra(
                producto_id=productos[nombre],
                cant_presentacion=Decimal(1),
                unid_x_presentacion=Decimal(unidades),
                costo_present_usd=Decimal(costo) * unidades,
                fecha_vencimiento=vencimiento,
            )
        )
    servicio_compras.registrar_compra(
        conexion,
        Compra(proveedor_id=proveedor, fecha=hoy, usuario_id=1, lineas=lineas),
    )


def _ventas(conexion, productos: dict[str, int]) -> None:
    """La caja del dia queda ABIERTA: el ejercicio es cerrarla (RF-43)."""
    servicio_caja.abrir(conexion, inicial_bs=Decimal(2000), inicial_usd=Decimal(20))
    nombres = [fila[0] for fila in PRODUCTOS]
    for numero, canasta in enumerate(VENTAS):
        venta = Venta(usuario_id=1, tasa=TASA)
        venta.lineas = [
            servicio_venta.nueva_linea(
                conexion, productos[nombres[indice]], Decimal(str(cantidad))
            )
            for indice, cantidad in canasta
        ]
        medio = PUNTO if numero % 2 else EFECTIVO  # la mitad por punto
        venta.pagos = [servicio_venta.pago(medio, "USD", venta.total_usd, TASA)]
        servicio_venta.registrar_venta(conexion, venta)


def _perdida_y_gasto(conexion, productos: dict[str, int]) -> None:
    motivo = repo_perdida.motivo_por_codigo(conexion, "MERMA_CHARCUTERIA")
    servicio_perdidas.registrar(
        conexion,
        productos["Mortadela (kg)"],
        Decimal("0.300"),
        motivo.id,
        observacion="Recorte del extremo",
    )
    # Gastos de todos los meses (1.2.0): un fijo y una comision por punto.
    servicio_gastos.registrar_recurrente(
        conexion, ALQUILER, "Alquiler del local", FIJO, monto_usd=Decimal(350)
    )
    servicio_gastos.registrar_recurrente(
        conexion, SERVICIOS, "Comision del punto de venta", PORCENTAJE,
        porcentaje=Decimal(3), medio=PUNTO,
    )
    # Y uno suelto, de este mes nada mas.
    servicio_gastos.registrar(conexion, OTROS, "Reparacion de la nevera", Decimal(60))


def _en_dias(fecha: str, dias: int) -> str:
    from datetime import date, timedelta

    return (date.fromisoformat(fecha) + timedelta(days=dias)).isoformat()


if __name__ == "__main__":
    destino = (
        Path(sys.argv[1]) if len(sys.argv) > 1
        else rutas.base_de_datos().with_name(ARCHIVO)
    )
    construir(destino)
    print(
        f"Base de demostracion lista en {destino}\n"
        f"  administrador: admin / {CLAVE_ADMIN}\n"
        f"  cajera:        maria / {CLAVE_CAJERO}\n"
        f"Para abrirla:\n"
        f'  set MINIMARKET_DB={destino}\n'
        f"  python -m minimarket"
    )
