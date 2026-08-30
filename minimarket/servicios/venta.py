"""Casos de uso del punto de venta (RF-34 a RF-41, RF-44, RF-45).

Una venta se registra entera o no se registra: encabezado, lineas, pagos y
movimientos de salida viajan en UNA sola transaccion (RNF-06). Si algo falla no
puede quedar inventario descontado sin venta registrada.
"""

import sqlite3
from collections import defaultdict
from decimal import Decimal

from minimarket.datos.conexion import transaccion
from minimarket.datos.repositorios import alicuota as repo_alicuota
from minimarket.datos.repositorios import configuracion as repo_configuracion
from minimarket.datos.repositorios import inventario as repo_inventario
from minimarket.datos.repositorios import producto as repo_producto
from minimarket.datos.repositorios import tasa as repo_tasa
from minimarket.datos.repositorios import usuario as repo_usuario
from minimarket.datos.repositorios import venta as repo_venta
from minimarket.dominio.inventario import (
    ANULACION_VENTA,
    REF_VENTA,
    VENTA,
    Movimiento,
)
from minimarket.dominio.venta import (
    COMPLETADA,
    MEDIOS,
    MONEDAS,
    Cliente,
    LineaVenta,
    Pago,
    Venta,
    equivalente_usd,
)
from minimarket.servicios import USUARIO_ACTUAL, caja
from minimarket.servicios import inventario as servicio_inventario
from minimarket.servicios import tasa as servicio_tasa


class ErrorVenta(Exception):
    """Falla previsible, con mensaje listo para mostrar en pantalla."""


# --- Armado de la venta -----------------------------------------------------


def nueva_linea(
    conexion: sqlite3.Connection, producto_id: int, cantidad: Decimal = Decimal(1)
) -> LineaVenta:
    """RF-34 / RN-19. Arma la linea copiando precio, alicuota y costo actual.

    Es el camino que recorre cada lectura del codigo de barras, asi que hace
    tres consultas por indice y nada mas (RNF-02).
    """
    if cantidad <= 0:
        raise ErrorVenta("La cantidad debe ser mayor que cero.")
    producto = repo_producto.obtener(conexion, producto_id)
    if producto is None:
        raise ErrorVenta("El producto ya no existe.")
    if not producto.activo:
        raise ErrorVenta(f"«{producto.nombre}» esta dado de baja y no se puede vender.")
    alicuota = repo_alicuota.obtener(conexion, producto.alicuota_iva_id)
    if alicuota is None:
        raise ErrorVenta(f"«{producto.nombre}» no tiene una alicuota de IVA valida.")
    return LineaVenta(
        producto_id=producto.id,
        descripcion=producto.nombre,
        cantidad=cantidad,
        precio_unit_usd=producto.precio_venta_usd,
        alicuota_pct=alicuota.porcentaje,
        # RN-19: el costo se congela ahora. Si manana cambia, esta venta no.
        costo_unitario_usd=repo_producto.ultimo_costo(conexion, producto.id)
        or Decimal(0),
    )


def pago(
    medio: str, moneda: str, monto: Decimal, tasa: Decimal, referencia: str | None = None
) -> Pago:
    """RN-22. Pago en su moneda con el equivalente en dolares ya calculado."""
    if medio not in MEDIOS:
        raise ErrorVenta(f"Medio de pago desconocido: {medio}.")
    if moneda not in MONEDAS:
        raise ErrorVenta(f"Moneda desconocida: {moneda}.")
    if monto <= 0:
        raise ErrorVenta("El monto del pago debe ser mayor que cero.")
    return Pago(
        medio=medio,
        moneda=moneda,
        monto=monto,
        monto_usd=equivalente_usd(monto, moneda, tasa),
        referencia=referencia,
    )


def cliente_por_rif(conexion: sqlite3.Connection, rif: str) -> Cliente | None:
    """RF-40."""
    return repo_venta.cliente_por_rif(conexion, rif.strip())


def guardar_cliente(conexion: sqlite3.Connection, cliente: Cliente) -> Cliente:
    """RF-40. Alta de los datos fiscales; si el RIF ya existe, lo devuelve."""
    if not (cliente.razon_social or "").strip():
        raise ErrorVenta("El cliente necesita una razon social.")
    if not (cliente.rif or "").strip():
        raise ErrorVenta("El cliente necesita un RIF.")
    existente = repo_venta.cliente_por_rif(conexion, cliente.rif.strip())
    if existente is not None:
        return existente
    with transaccion(conexion):
        identificador = repo_venta.crear_cliente(conexion, cliente)
    return repo_venta.obtener_cliente(conexion, identificador)


# --- Registro (RF-34 a RF-38, RF-44, RF-45) ---------------------------------


def registrar_venta(
    conexion: sqlite3.Connection, venta: Venta, autorizado_por: int | None = None
) -> Venta:
    """Registra la venta completa y descuenta el inventario.

    `autorizado_por` es el administrador que habilita vender por encima de la
    existencia registrada (RF-27); sin el, la venta se rechaza.
    """
    sesion = caja.exigir_sesion(conexion)  # RF-44
    venta.caja_sesion_id = sesion.id  # RF-45
    _fijar_tasa(conexion, venta)
    _validar_lineas(venta)
    _validar_existencias(conexion, venta, autorizado_por)
    _validar_pagos(venta)

    with transaccion(conexion):
        venta.numero = repo_venta.siguiente_numero(conexion)  # RN-24
        venta.estado = COMPLETADA
        venta.id = repo_venta.crear(conexion, venta)
        for linea in venta.lineas:
            _descontar(conexion, venta, linea)
            repo_venta.agregar_linea(conexion, venta.id, linea)
        for cobro in venta.pagos:
            repo_venta.registrar_pago(conexion, venta.id, cobro)
    return venta


def anular_venta(
    conexion: sqlite3.Connection,
    venta_id: int,
    motivo: str,
    usuario_id: int = USUARIO_ACTUAL,
) -> None:
    """RF-41 / RN-25. Clave de administrador y motivo obligatorio.

    Devuelve la mercancia al inventario con el costo congelado en la venta
    original. El documento no se borra: conserva su numero (RN-24) y sigue en
    el libro de ventas identificado como anulado.
    """
    if not repo_usuario.es_administrador(conexion, usuario_id):
        raise ErrorVenta("La anulacion de ventas esta reservada al administrador.")
    if not motivo.strip():
        raise ErrorVenta("Indica el motivo de la anulacion.")
    venta = repo_venta.obtener(conexion, venta_id)
    if venta is None:
        raise ErrorVenta("La venta ya no existe.")
    if venta.estado != COMPLETADA:
        raise ErrorVenta("Esta venta ya fue anulada.")

    salidas = [
        movimiento
        for movimiento in repo_inventario.movimientos_de_referencia(
            conexion, REF_VENTA, venta_id
        )
        if movimiento.tipo == VENTA
    ]
    with transaccion(conexion):
        for salida in salidas:
            repo_inventario.registrar_movimiento(
                conexion,
                Movimiento(
                    producto_id=salida.producto_id,
                    lote_id=salida.lote_id,
                    tipo=ANULACION_VENTA,
                    cantidad=-salida.cantidad,  # la salida es negativa: vuelve
                    costo_unitario_usd=salida.costo_unitario_usd,  # RN-25
                    referencia_tipo=REF_VENTA,
                    referencia_id=venta_id,
                    usuario_id=usuario_id,
                    observacion=motivo.strip(),
                ),
            )
        repo_venta.anular(conexion, venta_id, usuario_id, motivo.strip())


# --- Consultas --------------------------------------------------------------


def obtener(conexion: sqlite3.Connection, venta_id: int) -> Venta | None:
    return repo_venta.obtener(conexion, venta_id)


def por_numero(conexion: sqlite3.Connection, numero: int) -> Venta | None:
    """RN-24. El numero correlativo es lo que conoce el cajero."""
    return repo_venta.por_numero(conexion, numero)


def listar(
    conexion: sqlite3.Connection,
    desde: str | None = None,
    hasta: str | None = None,
    caja_sesion_id: int | None = None,
) -> list[Venta]:
    """RF-48 se apoya en esto; aca alcanza para buscar la venta a anular."""
    return repo_venta.listar(
        conexion, desde=desde, hasta=hasta, caja_sesion_id=caja_sesion_id
    )


# --- Nota de entrega (RF-39) ------------------------------------------------


def nota_de_entrega(conexion: sqlite3.Connection, venta_id: int) -> list[str]:
    """El comprobante ya maquetado, sin tocar la impresora."""
    from minimarket.infra import impresora  # import diferido: no siempre hay

    venta = repo_venta.obtener(conexion, venta_id)
    if venta is None:
        raise ErrorVenta("La venta ya no existe.")
    cliente = (
        repo_venta.obtener_cliente(conexion, venta.cliente_id)
        if venta.cliente_id
        else None
    )
    negocio = {
        clave: repo_configuracion.leer(conexion, f"negocio.{clave}")
        for clave in ("nombre", "rif", "direccion", "telefono")
    }
    return impresora.nota_de_entrega(
        venta, negocio, cliente, servicio_tasa.multiplo_redondeo(conexion)
    )


def hay_impresora(conexion: sqlite3.Connection) -> bool:
    """Sin impresora configurada la venta se registra igual, y sin avisos."""
    return bool(repo_configuracion.leer(conexion, "impresora.destino").strip())


def imprimir_nota(conexion: sqlite3.Connection, venta_id: int) -> None:
    """RF-39. Levanta `infra.impresora.ErrorImpresion` si no se pudo imprimir.

    La venta ya esta registrada cuando esto corre: un fallo de impresion se
    avisa y se ofrece reimprimir, nunca revierte la venta.
    """
    from minimarket.infra import impresora

    impresora.imprimir(
        nota_de_entrega(conexion, venta_id),
        repo_configuracion.leer(conexion, "impresora.destino"),
    )


# --- Validacion -------------------------------------------------------------


def _fijar_tasa(conexion: sqlite3.Connection, venta: Venta) -> None:
    """RN-03 / RN-04. La tasa de la venta la fija el servicio, no la pantalla.

    Los pagos en bolivares se reconvierten con ella: si la pantalla quedo
    abierta desde ayer, el equivalente en dolares no puede salir de la tasa
    vieja.
    """
    registro = repo_tasa.obtener(conexion, servicio_tasa.hoy())
    if registro is None:
        raise ErrorVenta(
            "No hay tasa de cambio cargada para hoy. Cargala antes de vender."
        )
    venta.tasa_id = registro.id
    venta.tasa = registro.valor
    for cobro in venta.pagos:
        cobro.monto_usd = equivalente_usd(cobro.monto, cobro.moneda, registro.valor)


def _validar_lineas(venta: Venta) -> None:
    if not venta.lineas:
        raise ErrorVenta("La venta no tiene ninguna linea cargada.")
    for numero, linea in enumerate(venta.lineas, start=1):
        if linea.cantidad <= 0:
            raise ErrorVenta(
                f"Linea {numero} ({linea.descripcion}): la cantidad debe ser "
                "mayor que cero."
            )
        if linea.precio_unit_usd < 0:
            raise ErrorVenta(
                f"Linea {numero} ({linea.descripcion}): el precio no puede ser "
                "negativo."
            )


def _validar_existencias(
    conexion: sqlite3.Connection, venta: Venta, autorizado_por: int | None
) -> None:
    """RF-27. Sin existencia no se vende, salvo autorizacion del administrador."""
    pedido: dict[int, Decimal] = defaultdict(Decimal)
    for linea in venta.lineas:
        pedido[linea.producto_id] += linea.cantidad
    autorizado = autorizado_por is not None and repo_usuario.es_administrador(
        conexion, autorizado_por
    )
    for producto_id, cantidad in pedido.items():
        disponible = repo_inventario.existencia(conexion, producto_id)
        if disponible >= cantidad:
            continue
        if autorizado:
            continue
        nombre = next(
            linea.descripcion
            for linea in venta.lineas
            if linea.producto_id == producto_id
        )
        raise ErrorVenta(
            f"No hay existencia suficiente de «{nombre}»: quedan {disponible} "
            f"y se piden {cantidad}. Un administrador puede autorizar la venta."
        )


def _validar_pagos(venta: Venta) -> None:
    """RN-22 y RN-23."""
    if not venta.pagos:
        raise ErrorVenta("La venta no tiene pagos registrados.")
    for cobro in venta.pagos:
        if cobro.medio not in MEDIOS:
            raise ErrorVenta(f"Medio de pago desconocido: {cobro.medio}.")
        if cobro.moneda not in MONEDAS:
            raise ErrorVenta(f"Moneda desconocida: {cobro.moneda}.")
        if cobro.monto <= 0:
            raise ErrorVenta("El monto de cada pago debe ser mayor que cero.")
    if venta.falta_usd > 0:
        raise ErrorVenta(
            f"Faltan {venta.falta_usd} USD por cobrar. La venta no se confirma "
            "hasta que los pagos alcancen el total."
        )
    if not venta.vuelto_admisible:
        raise ErrorVenta(
            "El excedente no se puede devolver: solo los pagos en efectivo "
            "generan vuelto. Cobra el monto exacto por punto, pago movil o "
            "transferencia."
        )


def _descontar(conexion: sqlite3.Connection, venta: Venta, linea: LineaVenta) -> None:
    """RN-15. Reparte la salida entre lotes y registra los movimientos.

    ponytail: la linea de detalle es una sola aunque la salida toque dos lotes;
    `venta_detalle.lote_id` queda en NULL en ese caso y el reparto real vive en
    los movimientos, que es donde se consulta. Partir la linea en dos cambiaria
    lo que ve el cliente en la nota por un detalle de almacen.
    """
    reparto = servicio_inventario.salida_por_lotes(
        conexion, linea.producto_id, linea.cantidad
    )
    linea.lote_id = reparto[0][0] if len(reparto) == 1 else None
    for lote_id, cantidad in reparto:
        repo_inventario.registrar_movimiento(
            conexion,
            Movimiento(
                producto_id=linea.producto_id,
                lote_id=lote_id,
                tipo=VENTA,
                cantidad=-cantidad,  # RN-12: salida, negativa
                costo_unitario_usd=linea.costo_unitario_usd,  # RN-19
                referencia_tipo=REF_VENTA,
                referencia_id=venta.id,
                usuario_id=venta.usuario_id,
            ),
        )
