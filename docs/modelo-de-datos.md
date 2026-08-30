


Modelo de Datos
Sistema de gestión para minimarket  ·  Opción C
Cliente | 
Proyecto | Sistema de gestión comercial
Versión | 1.0
Fecha | 19 de agosto de 2026
Autor | Gregor Barrios — Borealis Software Solutions
Documentos relacionados | Especificación de Requisitos, Reglas de Negocio


1. CRITERIOS DE DISEÑO
El modelo se construye sobre cuatro decisiones que condicionan todo lo demás. Están enunciadas aquí porque revertirlas una vez iniciado el desarrollo implica rehacer el sistema.
Inventario por movimientos
No existe un campo de existencia editable. La cantidad disponible de un producto es la suma de los registros de la tabla de movimientos. Esta decisión permite explicar el origen de cada unidad y es la única forma de que las pérdidas, las anulaciones y los ajustes queden auditados.
Costos y precios en dólares
La moneda base es el dólar. El bolívar se calcula siempre a partir de la tasa correspondiente. Las tablas de operaciones consumadas conservan el importe en bolívares efectivamente cobrado junto con la tasa aplicada, como registro histórico.
Copias de valores en el momento de la operación
Las líneas de venta guardan copia del precio, de la alícuota y del costo unitario vigentes al momento de registrarse. Cambiar el costo de un producto no debe alterar la ganancia de las ventas ya realizadas.
Conversión de presentación en la línea de compra
Las unidades por presentación se registran en cada línea de compra y no en la ficha del producto, porque el cliente adquiere el mismo artículo en presentaciones de distinto tamaño según el proveedor.
Motor de base de datosEl modelo está expresado de forma portable. Para una operación local sobre un único equipo, sin concurrencia y sin conexión, tanto SQLite como PostgreSQL son adecuados: el primero simplifica la instalación y el respaldo a un solo archivo; el segundo ofrece tipos decimales nativos y mejor comportamiento ante interrupciones.Cualquiera sea la elección, los importes monetarios deben usar tipos decimales de precisión fija. En SQLite esto exige almacenar enteros escalados o texto, ya que carece de tipo decimal nativo; conviene evaluarlo antes de decidir.

Convenciones de nomenclatura
Nombres de tabla en singular y minúsculas, con palabras separadas por guion bajo.
Clave primaria denominada id, entera y autoincremental.
Claves foráneas con el nombre de la tabla referida seguido del sufijo _id.
Importes monetarios con el sufijo _usd o _bs según su moneda.
Campos de auditoría creado_en y actualizado_en en las tablas maestras.
Estados y tipos expresados como valores enumerados en mayúsculas.

2. DIAGRAMAS ENTIDAD-RELACIÓN
El modelo se presenta en cinco vistas para facilitar su lectura. Las tablas que aparecen en más de una vista son la misma entidad; los campos omitidos en una vista se detallan en el diccionario.
2.1 Producto, categoría, alícuota y lote


2.2 Compras, proveedores y tasa de cambio


2.3 Inventario, pérdidas y ajustes


2.4 Ventas, líneas y medios de pago


2.5 Usuarios, caja, gastos y auditoría


3. DICCIONARIO DE TABLAS
producto
Catálogo de artículos comercializados. La baja es lógica mediante el campo activo, ya que los productos con movimientos no pueden eliminarse.
Campo | Observación
precio_venta_usd | Precio al público con IVA incluido, expresado en dólares.
margen_objetivo | Margen propio del producto. Si es nulo, se aplica el de su categoría.
maneja_vencimiento | Determina si las compras del producto exigen lote y fecha de vencimiento.
existencia_minima | Umbral que dispara la alerta de reposición.


categoria
Agrupación comercial de productos. Define el margen objetivo aplicable por defecto.
alicuota_iva
Catálogo de alícuotas vigentes. El porcentaje se copia a cada línea de venta al momento de registrarla.
tasa_cambio
Histórico de tasas, con una fila por fecha. El campo origen distingue la carga automática de la manual.
proveedor
Proveedores de mercancía.
compra
Encabezado de una entrada de mercancía. El saldo pendiente permite el control de deuda con el proveedor.
compra_detalle
Líneas de la compra. Contiene la conversión de presentación a unidad y el costo unitario resultante.
Campo | Observación
unid_x_presentacion | Unidades contenidas en la presentación adquirida, propia de esta línea.
cantidad_unidades | Producto de la cantidad de presentaciones por las unidades que contiene.
costo_unitario_usd | Costo de la presentación dividido entre las unidades que contiene.


pago_proveedor
Pagos parciales o totales aplicados a una compra.
lote
Agrupación de unidades con una misma fecha de vencimiento. Solo se crea para productos que lo manejan.
movimiento_inventario
Registro único de toda variación de existencias. Es la tabla central del sistema.
Campo | Observación
cantidad | Positiva en entradas, negativa en salidas.
costo_unitario_usd | Costo vigente al producirse el movimiento. No se recalcula.
referencia_tipo / referencia_id | Vínculo con la operación que originó el movimiento: compra, venta, pérdida o ajuste.


motivo_perdida
Catálogo de motivos: vencido, dañado, faltante, merma de charcutería y consumo propio.
perdida
Registro de mercancía perdida, valorizada al último costo vigente.
ajuste_inventario
Resultado de un conteo físico, con la cantidad del sistema, la contada y la diferencia.
usuario
Usuarios del sistema y su perfil. Las claves se almacenan cifradas.
caja_sesion
Apertura y cierre de caja, con montos iniciales y conteo final por moneda.
cliente
Datos fiscales de clientes que requieren comprobante con RIF y razón social.
venta
Encabezado de la venta, con separación de exento, base imponible e IVA, y el equivalente en bolívares a la tasa aplicada.
Campo | Observación
numero | Correlativo irrepetible que se conserva aun cuando la venta se anule.
tasa_id | Tasa utilizada. Permite reconstruir el importe en bolívares en cualquier momento.


venta_detalle
Líneas de la venta con copia del precio, la alícuota y el costo unitario del momento.
Campo | Observación
costo_unitario_usd | Copia del costo vigente. Base del cálculo de ganancia por producto.
descripcion | Copia del nombre del producto, para que la reimpresión del comprobante sea fiel al original.


venta_pago
Medios de pago aplicados a una venta, con su moneda original y su equivalente en dólares.
gasto_operativo
Gastos fijos del negocio, asociados a un período mensual.
configuracion
Parámetros del sistema: datos fiscales, redondeo, ruta de respaldo y días de alerta por defecto.
auditoria
Bitácora de operaciones sensibles: anulaciones, ajustes, cambios de precio y de usuarios.
respaldo
Historial de respaldos ejecutados, con su resultado.

4. ÍNDICES Y RESTRICCIONES
Tabla | Índice o restricción | Motivo
producto | Índice único sobre codigo_barras, admitiendo nulos | Lectura inmediata en caja; los productos sin código no lo tienen.
producto | Índice sobre nombre | Búsqueda parcial por nombre en el punto de venta.
tasa_cambio | Índice único sobre fecha | Garantiza una sola tasa por día.
movimiento_inventario | Índice compuesto sobre producto_id y fecha_hora | Cálculo de existencias y kardex por período.
movimiento_inventario | Índice sobre referencia_tipo y referencia_id | Localización de los movimientos de una operación al anularla.
venta | Índice único sobre numero | Correlativo irrepetible.
venta | Índice sobre fecha_hora | Reportes por período y libro de ventas.
venta_detalle | Índice sobre producto_id | Reporte de ganancia y rotación por producto.
lote | Índice sobre producto_id y fecha_vencimiento | Selección del lote más próximo a vencer y alertas.
compra_detalle | Índice sobre producto_id | Determinación del último costo.

Reglas de integridad
Ninguna tabla de operaciones admite borrado físico. Las correcciones se registran como operaciones inversas.
Las claves foráneas se declaran con restricción de borrado, de modo que la base rechace la eliminación de registros referenciados.
La cantidad de un movimiento nunca puede ser cero.
El total de una venta debe coincidir con la suma de sus líneas; se verifica antes de confirmar.
La suma de los pagos convertidos a dólares debe ser mayor o igual al total de la venta.
Una sesión de caja no puede tener dos aperturas simultáneas.
Un producto marcado con control de vencimiento no admite movimientos de entrada sin lote asociado.
5. ESTIMACIÓN DE VOLUMEN
Los valores siguientes orientan las decisiones de indexación y de estrategia de respaldo. Corresponden a la operación prevista de un minimarket con una caja.
Tabla | Volumen inicial | Crecimiento anual estimado
producto | 1.500 a 2.500 registros | Bajo
venta | — | 60.000 a 110.000 registros
venta_detalle | — | 300.000 a 600.000 registros
movimiento_inventario | 2.500 (carga inicial) | 350.000 a 700.000 registros
compra_detalle | — | 15.000 a 25.000 registros
tasa_cambio | — | 365 registros

Consecuencia prácticaLa tabla de movimientos supera el medio millón de filas en el primer año. Calcular la existencia sumando movimientos en cada lectura resulta viable con los índices indicados, pero conviene mantener una existencia calculada en caché por producto, recalculable a partir de los movimientos y nunca editable de forma directa.Es igualmente recomendable prever desde el inicio un procedimiento de cierre anual que consolide los movimientos antiguos en un saldo de apertura, aun cuando no se implemente en esta versión.


ANEXO — ESQUEMA DE CREACIÓN
El archivo esquema.sql acompaña a este documento y contiene la definición completa en sintaxis compatible con PostgreSQL, incluidos los índices, las restricciones y los datos iniciales de alícuotas, motivos de pérdida y configuración.
Fragmento representativo de las dos tablas centrales del modelo:
CREATE TABLE movimiento_inventario (
    id                  SERIAL PRIMARY KEY,
    producto_id         INTEGER NOT NULL REFERENCES producto(id),
    lote_id             INTEGER NULL REFERENCES lote(id),
    tipo                VARCHAR(20) NOT NULL,
    cantidad            NUMERIC(14,3) NOT NULL,
    costo_unitario_usd  NUMERIC(12,4) NOT NULL DEFAULT 0,
    referencia_tipo     VARCHAR(30) NOT NULL,
    referencia_id       INTEGER NOT NULL,
    fecha_hora          TIMESTAMP NOT NULL DEFAULT NOW(),
    usuario_id          INTEGER NOT NULL REFERENCES usuario(id),
    observacion         VARCHAR(250),
    CONSTRAINT ck_cantidad_no_cero CHECK (cantidad <> 0)
);
 
CREATE TABLE venta_detalle (
    id                  SERIAL PRIMARY KEY,
    venta_id            INTEGER NOT NULL REFERENCES venta(id),
    producto_id         INTEGER NOT NULL REFERENCES producto(id),
    lote_id             INTEGER NULL REFERENCES lote(id),
    descripcion         VARCHAR(150) NOT NULL,
    cantidad            NUMERIC(14,3) NOT NULL,
    precio_unit_usd     NUMERIC(12,4) NOT NULL,
    alicuota_pct        NUMERIC(5,2)  NOT NULL,
    base_imponible_usd  NUMERIC(14,2) NOT NULL,
    iva_usd             NUMERIC(14,2) NOT NULL,
    total_linea_usd     NUMERIC(14,2) NOT NULL,
    costo_unitario_usd  NUMERIC(12,4) NOT NULL
);