"""Casos de uso del catalogo (RF-01 a RF-08).

La interfaz no habla con `datos/`: entra por aca. Los errores salen como
`ErrorCatalogo` con un mensaje ya redactado para el usuario final (RNF-09).
"""

import csv
import sqlite3
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation

from minimarket.datos.conexion import transaccion
from minimarket.datos.repositorios import alicuota as repo_alicuota
from minimarket.datos.repositorios import categoria as repo_categoria
from minimarket.datos.repositorios import producto as repo_producto
from minimarket.dominio.producto import (
    AlicuotaIva,
    Categoria,
    Producto,
    margen_resultante,
    precio_sugerido,
)
from minimarket.dominio.usuario import MODIFICAR_PRECIOS, VER_COSTOS
from minimarket.infra import auditoria
from minimarket.servicios import ErrorServicio, usuario_actual
from minimarket.servicios import usuarios as servicio_usuarios


class ErrorCatalogo(ErrorServicio):
    """Falla previsible, con mensaje listo para mostrar en pantalla."""


def crear_producto(conexion: sqlite3.Connection, producto: Producto) -> int:
    """RF-01. Alta de catalogo: fija un precio, asi que es de administrador."""
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    _validar(conexion, producto)
    with transaccion(conexion):
        try:
            return repo_producto.crear(conexion, producto)
        except sqlite3.IntegrityError as error:
            raise _error_codigo_repetido(producto, error) from error


def modificar_producto(conexion: sqlite3.Connection, producto: Producto) -> None:
    """RF-01 / RF-58. El cambio de precio queda en la bitacora (RF-59)."""
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    if producto.id is None:
        raise ErrorCatalogo("No se puede modificar un producto que no fue guardado.")
    _validar(conexion, producto)
    anterior = repo_producto.obtener(conexion, producto.id)
    autor = usuario_actual()
    with transaccion(conexion):
        try:
            repo_producto.actualizar(conexion, producto)
        except sqlite3.IntegrityError as error:
            raise _error_codigo_repetido(producto, error) from error
        cambio_de_precio = (
            anterior is not None
            and anterior.precio_venta_usd != producto.precio_venta_usd
        )
        if cambio_de_precio:
            auditoria.registrar(
                conexion,
                autor,
                auditoria.CAMBIO_PRECIO,
                "producto",
                producto.id,
                antes={"precio_venta_usd": anterior.precio_venta_usd},
                despues={"precio_venta_usd": producto.precio_venta_usd},
            )


def desactivar_producto(conexion: sqlite3.Connection, producto_id: int) -> None:
    """RF-02. Baja logica siempre: el producto con movimientos no se borra."""
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    with transaccion(conexion):
        repo_producto.cambiar_estado(conexion, producto_id, activo=False)


def reactivar_producto(conexion: sqlite3.Connection, producto_id: int) -> None:
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    with transaccion(conexion):
        repo_producto.cambiar_estado(conexion, producto_id, activo=True)


def buscar(
    conexion: sqlite3.Connection, texto: str, solo_activos: bool = True
) -> list[Producto]:
    """RF-04. Codigo de barras exacto primero; si no, nombre parcial.

    El lector de codigo de barras entrega el codigo completo, asi que la
    coincidencia exacta corta la busqueda antes de recorrer nombres.
    """
    texto = texto.strip()
    if not texto:
        return repo_producto.listar(conexion, solo_activos=solo_activos)
    exacto = repo_producto.por_codigo_barras(conexion, texto)
    if exacto is not None and (exacto.activo or not solo_activos):
        return [exacto]
    return repo_producto.buscar_por_nombre(conexion, texto, solo_activos=solo_activos)


def listado_completo(
    conexion: sqlite3.Connection, solo_activos: bool = True
) -> list[Producto]:
    """Todo el catalogo, para los selectores de producto de la interfaz.

    `buscar` esta limitada a 200 filas porque responde a cada tecla; un
    selector con autocompletado necesita el catalogo entero cargado.
    """
    return repo_producto.listar(
        conexion, solo_activos=solo_activos, limite=1_000_000
    )


def obtener_producto(
    conexion: sqlite3.Connection, producto_id: int
) -> Producto | None:
    return repo_producto.obtener(conexion, producto_id)


def tiene_movimientos(conexion: sqlite3.Connection, producto_id: int) -> bool:
    """RF-02. Si los tiene, la baja conserva el historico en vez de borrarlo."""
    return repo_producto.tiene_movimientos(conexion, producto_id)


def ultimo_costo(
    conexion: sqlite3.Connection, producto_id: int
) -> Decimal | None:
    """RN-07. Costo de la ultima compra confirmada; None si nunca se compro."""
    servicio_usuarios.exigir(conexion, VER_COSTOS)  # RF-58
    return repo_producto.ultimo_costo(conexion, producto_id)


def listar_categorias(
    conexion: sqlite3.Connection, solo_activas: bool = True
) -> list[Categoria]:
    """RF-05."""
    return repo_categoria.listar(conexion, solo_activas=solo_activas)


def cantidad_productos(conexion: sqlite3.Connection, categoria_id: int) -> int:
    """RF-05. Cuantos productos cuelgan de una categoria."""
    return repo_categoria.cantidad_productos(conexion, categoria_id)


def listar_alicuotas(conexion: sqlite3.Connection) -> list[AlicuotaIva]:
    """RF-06. Las tres del esquema: exento, general y reducida."""
    return repo_alicuota.listar(conexion)


def calcular_precio(
    conexion: sqlite3.Connection, producto: Producto
) -> Decimal | None:
    """RF-07. Precio con IVA sugerido por el margen objetivo aplicable.

    Devuelve None si el producto no tiene costo de compra todavia: sin costo,
    RN-09 no tiene de donde partir.
    """
    servicio_usuarios.exigir(conexion, VER_COSTOS)  # RF-58
    costo = repo_producto.ultimo_costo(conexion, producto.id) if producto.id else None
    if costo is None:
        return None
    categoria = _categoria(conexion, producto.categoria_id)
    return precio_sugerido(
        costo, producto, categoria, _porcentaje(conexion, producto.alicuota_iva_id)
    )


def calcular_margen(
    conexion: sqlite3.Connection, producto: Producto
) -> Decimal | None:
    """RF-07, camino inverso: margen que deja el precio cargado a mano."""
    servicio_usuarios.exigir(conexion, VER_COSTOS)  # RF-58
    costo = repo_producto.ultimo_costo(conexion, producto.id) if producto.id else None
    if costo is None:
        return None
    return margen_resultante(
        producto.precio_venta_usd,
        _porcentaje(conexion, producto.alicuota_iva_id),
        costo,
    )


def previsualizar_recalculo(
    conexion: sqlite3.Connection, categoria_id: int
) -> list[tuple[Producto, Decimal]]:
    """RF-08. Que precio quedaria en cada producto, sin tocar nada todavia.

    Se muestra al administrador para que confirme; recien despues corre
    `aplicar_recalculo`. Los productos sin costo de compra quedan fuera: no hay
    con que recalcularlos.
    """
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    categoria = _categoria(conexion, categoria_id)
    costos = repo_producto.ultimos_costos(conexion, categoria_id)
    alicuotas = {a.id: a.porcentaje for a in repo_alicuota.listar(conexion)}
    cambios = []
    for producto in repo_producto.listar(
        conexion, categoria_id=categoria_id, limite=1_000_000
    ):
        costo = costos.get(producto.id)
        if costo is None:
            continue
        nuevo = precio_sugerido(
            costo, producto, categoria, alicuotas[producto.alicuota_iva_id]
        )
        if nuevo != producto.precio_venta_usd:
            cambios.append((producto, nuevo))
    return cambios


def aplicar_recalculo(
    conexion: sqlite3.Connection, cambios: list[tuple[Producto, Decimal]]
) -> int:
    """RF-08. Aplica lo previsualizado; todo o nada (RNF-06)."""
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    autor = usuario_actual()
    with transaccion(conexion):
        for producto, precio in cambios:
            repo_producto.actualizar_precio(conexion, producto.id, precio)
            auditoria.registrar(  # RF-59
                conexion,
                autor,
                auditoria.RECALCULO_PRECIOS,
                "producto",
                producto.id,
                antes={"precio_venta_usd": producto.precio_venta_usd},
                despues={"precio_venta_usd": precio},
            )
    return len(cambios)


def previsualizar_recalculo_total(
    conexion: sqlite3.Connection,
) -> list[tuple[Producto, Decimal]]:
    """RF-08 para todo el catalogo: el boton que pidio el cliente (1.2.0)."""
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    cambios = []
    for categoria in repo_categoria.listar(conexion, solo_activas=False):
        cambios.extend(previsualizar_recalculo(conexion, categoria.id))
    return cambios


@dataclass(frozen=True)
class PlanDeMargen:
    """Lo que pasaria al aplicar un margen como piso a todo el catalogo.

    `categorias` y `productos` son los que hoy tienen un margen objetivo por
    debajo y subirian a `margen_pct`; lo que esta por encima no se toca (es
    lo que el dueno decidio). `cambios` son los precios resultantes, listos
    para `aplicar_recalculo`. `sin_costo` cuenta los productos que no se
    pueden recalcular porque nunca se compraron.
    """

    margen_pct: Decimal
    categorias: list[tuple[Categoria, Decimal]]
    productos: list[tuple[Producto, Decimal]]
    cambios: list[tuple[Producto, Decimal]]
    sin_costo: int


def previsualizar_margen(
    conexion: sqlite3.Connection, margen_pct: Decimal
) -> PlanDeMargen:
    """Que cambiaria si `margen_pct` fuera el piso de todo el catalogo (1.2.0).

    No toca nada. Calcula los precios como si los margenes ya estuvieran
    subidos, con el ultimo costo de cada producto (RN-07, RN-09).
    """
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    if margen_pct < 0:
        raise ErrorCatalogo("El margen no puede ser negativo.")
    alicuotas = {a.id: a.porcentaje for a in repo_alicuota.listar(conexion)}
    categorias_subir, productos_subir, cambios, sin_costo = [], [], [], 0
    for categoria in repo_categoria.listar(conexion, solo_activas=False):
        nueva = categoria
        if categoria.margen_objetivo < margen_pct:
            categorias_subir.append((categoria, categoria.margen_objetivo))
            nueva = Categoria(categoria.id, categoria.nombre, margen_pct, categoria.activo)
        costos = repo_producto.ultimos_costos(conexion, categoria.id)
        for producto in repo_producto.listar(
            conexion, categoria_id=categoria.id, limite=1_000_000
        ):
            if producto.margen_objetivo is not None and producto.margen_objetivo < margen_pct:
                productos_subir.append((producto, producto.margen_objetivo))
                producto = replace(producto, margen_objetivo=margen_pct)
            costo = costos.get(producto.id)
            if costo is None:
                sin_costo += 1
                continue
            precio = precio_sugerido(costo, producto, nueva, alicuotas[producto.alicuota_iva_id])
            if precio != producto.precio_venta_usd:
                cambios.append((producto, precio))
    return PlanDeMargen(margen_pct, categorias_subir, productos_subir, cambios, sin_costo)


def aplicar_margen(conexion: sqlite3.Connection, plan: PlanDeMargen) -> int:
    """Sube los margenes por debajo del piso y recalcula los precios; todo o nada.

    Cada precio queda en la bitacora por `aplicar_recalculo` (RF-59); los
    margenes, en un asiento propio.
    """
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    autor = usuario_actual()
    with transaccion(conexion):
        for categoria, _ in plan.categorias:
            repo_categoria.actualizar(
                conexion,
                Categoria(categoria.id, categoria.nombre, plan.margen_pct, categoria.activo),
            )
        for producto, _ in plan.productos:
            repo_producto.actualizar(conexion, replace(producto, margen_objetivo=plan.margen_pct))
        if plan.categorias or plan.productos:
            auditoria.registrar(
                conexion,
                autor,
                auditoria.RECALCULO_PRECIOS,
                "categoria",
                antes={
                    "categorias": {c.nombre: str(m) for c, m in plan.categorias},
                    "productos": {p.nombre: str(m) for p, m in plan.productos},
                },
                despues={"margen_objetivo": str(plan.margen_pct)},
            )
        for producto, precio in plan.cambios:
            repo_producto.actualizar_precio(conexion, producto.id, precio)
            auditoria.registrar(
                conexion,
                autor,
                auditoria.RECALCULO_PRECIOS,
                "producto",
                producto.id,
                antes={"precio_venta_usd": producto.precio_venta_usd},
                despues={"precio_venta_usd": precio},
            )
    return len(plan.cambios)


def margenes_actuales(conexion: sqlite3.Connection) -> dict[int, Decimal | None]:
    """RN-08 para todo el catalogo: el margen que deja el precio de hoy.

    Para la columna «Margen %» de la pantalla de productos. None: sin costo
    de compra, no determinable. Solo quien puede ver costos.
    """
    servicio_usuarios.exigir(conexion, VER_COSTOS)
    alicuotas = {a.id: a.porcentaje for a in repo_alicuota.listar(conexion)}
    margenes: dict[int, Decimal | None] = {}
    for categoria in repo_categoria.listar(conexion, solo_activas=False):
        costos = repo_producto.ultimos_costos(conexion, categoria.id)
        for producto in repo_producto.listar(
            conexion, categoria_id=categoria.id, solo_activos=False, limite=1_000_000
        ):
            costo = costos.get(producto.id)
            margenes[producto.id] = (
                None
                if costo is None
                else margen_resultante(
                    producto.precio_venta_usd, alicuotas[producto.alicuota_iva_id], costo
                )
            )
    return margenes


def guardar_categoria(conexion: sqlite3.Connection, categoria: Categoria) -> int:
    """RF-05. Alta si no tiene id, modificacion si lo tiene.

    Es de administrador: el margen objetivo de la categoria decide el precio
    sugerido de todos sus productos (RN-09).
    """
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    if not categoria.nombre.strip():
        raise ErrorCatalogo("La categoria necesita un nombre.")
    if categoria.margen_objetivo < 0:
        raise ErrorCatalogo("El margen objetivo no puede ser negativo.")
    with transaccion(conexion):
        try:
            if categoria.id is None:
                return repo_categoria.crear(conexion, categoria)
            repo_categoria.actualizar(conexion, categoria)
            return categoria.id
        except sqlite3.IntegrityError as error:
            raise ErrorCatalogo(
                f"Ya existe una categoria llamada «{categoria.nombre}»."
            ) from error


# --- Carga inicial desde CSV (punto 7 de la Fase 6) -------------------------

COLUMNAS_CSV = [
    "nombre",
    "categoria",
    "alicuota",
    "precio_venta_usd",
    "codigo_barras",
    "margen_objetivo",
    "existencia_minima",
    "maneja_vencimiento",
    "dias_alerta_venc",
]
OBLIGATORIAS = COLUMNAS_CSV[:4]

# ponytail: CSV y nada mas. Excel entra guardando como «CSV UTF-8» desde el
# mismo Excel; leer .xlsx nativo pide openpyxl, una dependencia entera para un
# archivo que el cliente carga una vez en la vida.


@dataclass(frozen=True)
class ResultadoImportacion:
    """Lo que dejo la carga: cuantos entraron y que fila fallo."""

    creados: int
    errores: list[str]


def plantilla_csv() -> str:
    """El encabezado que el archivo tiene que traer, con una fila de ejemplo."""
    return (
        ",".join(COLUMNAS_CSV)
        + "\nHarina de maiz 1 kg,Viveres,GENERAL,1.20,7591234567890,,10,0,15\n"
    )


def importar_csv(conexion: sqlite3.Connection, ruta: str) -> ResultadoImportacion:
    """RF-01 en lote. Todo o nada: con un solo error no se carga ninguno.

    Es la carga inicial de mas de mil productos. Importar «los que se pueda»
    dejaria el archivo a medio entrar y la segunda pasada duplicaria los
    productos sin codigo de barras. Se corrigen las filas que el reporte
    nombra y se vuelve a importar.
    """
    servicio_usuarios.exigir(conexion, MODIFICAR_PRECIOS)
    categorias = {
        c.nombre.strip().lower(): c.id
        for c in repo_categoria.listar(conexion, solo_activas=False)
    }
    alicuotas = {a.codigo.upper(): a.id for a in repo_alicuota.listar(conexion)}

    productos: list[tuple[int, Producto]] = []  # (fila del archivo, producto)
    errores: list[str] = []
    try:
        with open(ruta, encoding="utf-8-sig", newline="") as archivo:
            lector = csv.DictReader(archivo)
            faltantes = [c for c in OBLIGATORIAS if c not in (lector.fieldnames or [])]
            if faltantes:
                raise ErrorCatalogo(
                    "Al archivo le faltan columnas: "
                    + ", ".join(faltantes)
                    + ". La primera fila tiene que ser: "
                    + ", ".join(COLUMNAS_CSV)
                )
            for numero, fila in enumerate(lector, start=2):  # 1 es el encabezado
                try:
                    productos.append(
                        (numero, _desde_fila(fila, categorias, alicuotas))
                    )
                except ErrorCatalogo as error:
                    errores.append(f"Fila {numero}: {error}")
    except OSError as error:
        raise ErrorCatalogo(
            "No se pudo leer el archivo. Revisa que exista y que no este "
            "abierto en otro programa."
        ) from error
    except UnicodeDecodeError as error:
        raise ErrorCatalogo(
            "El archivo no esta en formato UTF-8. Volve a guardarlo desde "
            "Excel como «CSV UTF-8 (delimitado por comas)»."
        ) from error

    errores.extend(_codigos_repetidos(productos))
    if errores or not productos:
        return ResultadoImportacion(0, errores or ["El archivo no tiene filas."])
    with transaccion(conexion):
        for _, producto in productos:
            try:
                repo_producto.crear(conexion, producto)
            except sqlite3.IntegrityError as error:
                raise _error_codigo_repetido(producto, error) from error
    return ResultadoImportacion(len(productos), [])


def _desde_fila(
    fila: dict[str, str], categorias: dict[str, int], alicuotas: dict[str, int]
) -> Producto:
    """Una fila del CSV convertida a Producto, o `ErrorCatalogo` con el motivo."""
    nombre = (fila.get("nombre") or "").strip()
    if not nombre:
        raise ErrorCatalogo("falta el nombre del producto.")
    categoria = (fila.get("categoria") or "").strip().lower()
    if categoria not in categorias:
        raise ErrorCatalogo(
            f"la categoria «{fila.get('categoria', '').strip()}» no existe. "
            "Creala primero en la pantalla de categorias."
        )
    codigo_alicuota = (fila.get("alicuota") or "").strip().upper()
    if codigo_alicuota not in alicuotas:
        raise ErrorCatalogo(
            f"la alicuota «{codigo_alicuota}» no existe. Usa una de: "
            + ", ".join(sorted(alicuotas))
        )
    precio = _numero(fila, "precio_venta_usd", Decimal(0))
    if precio < 0:
        raise ErrorCatalogo("el precio de venta no puede ser negativo.")
    minima = _numero(fila, "existencia_minima", Decimal(0))
    if minima < 0:
        raise ErrorCatalogo("la existencia minima no puede ser negativa.")
    codigo = (fila.get("codigo_barras") or "").strip()
    return Producto(
        nombre=nombre,
        categoria_id=categorias[categoria],
        alicuota_iva_id=alicuotas[codigo_alicuota],
        precio_venta_usd=precio,
        codigo_barras=codigo or None,
        margen_objetivo=_numero(fila, "margen_objetivo", None),
        existencia_minima=minima,
        maneja_vencimiento=_bandera(fila.get("maneja_vencimiento")),
        dias_alerta_venc=int(_numero(fila, "dias_alerta_venc", Decimal(15))),
    )


def _numero(fila: dict[str, str], columna: str, defecto):
    """Los importes aceptan coma o punto decimal, como el resto de la interfaz."""
    texto = (fila.get(columna) or "").strip().replace(",", ".")
    if not texto:
        return defecto
    try:
        return Decimal(texto)
    except InvalidOperation as error:
        raise ErrorCatalogo(f"«{columna}» tiene que ser un numero.") from error


def _bandera(texto: str | None) -> bool:
    return (texto or "").strip().lower() in ("1", "si", "sí", "s", "true", "x")


def _codigos_repetidos(productos: list[tuple[int, Producto]]) -> list[str]:
    """El archivo puede traer el mismo codigo dos veces; SQLite lo diria una."""
    vistos: dict[str, int] = {}
    errores = []
    for numero, producto in productos:
        if producto.codigo_barras is None:
            continue
        if producto.codigo_barras in vistos:
            errores.append(
                f"Fila {numero}: el codigo de barras "
                f"«{producto.codigo_barras}» ya aparece en la fila "
                f"{vistos[producto.codigo_barras]}."
            )
        vistos[producto.codigo_barras] = numero
    return errores


def _validar(conexion: sqlite3.Connection, producto: Producto) -> None:
    if not producto.nombre.strip():
        raise ErrorCatalogo("El producto necesita un nombre.")
    if producto.precio_venta_usd < 0:
        raise ErrorCatalogo("El precio de venta no puede ser negativo.")
    if producto.existencia_minima < 0:
        raise ErrorCatalogo("La existencia minima no puede ser negativa.")
    if repo_categoria.obtener(conexion, producto.categoria_id) is None:
        raise ErrorCatalogo("Elegi una categoria valida.")
    if repo_alicuota.obtener(conexion, producto.alicuota_iva_id) is None:
        raise ErrorCatalogo("Elegi una alicuota de IVA valida.")


def _categoria(conexion: sqlite3.Connection, categoria_id: int) -> Categoria:
    categoria = repo_categoria.obtener(conexion, categoria_id)
    if categoria is None:
        raise ErrorCatalogo("La categoria del producto ya no existe.")
    return categoria


def _porcentaje(conexion: sqlite3.Connection, alicuota_id: int) -> Decimal:
    alicuota = repo_alicuota.obtener(conexion, alicuota_id)
    if alicuota is None:
        raise ErrorCatalogo("La alicuota de IVA del producto ya no existe.")
    return alicuota.porcentaje


def _error_codigo_repetido(
    producto: Producto, error: sqlite3.IntegrityError
) -> ErrorCatalogo:
    if "codigo_barras" in str(error):
        return ErrorCatalogo(
            f"El codigo de barras «{producto.codigo_barras}» ya esta en uso "
            "por otro producto."
        )
    return ErrorCatalogo("No se pudo guardar el producto: revisa los datos cargados.")
