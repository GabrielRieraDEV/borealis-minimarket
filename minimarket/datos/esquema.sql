-- =====================================================================
--  Sistema de gestion para minimarket — Opcion C
--  Borealis Software Solutions
--  Esquema SQLite · adaptado de docs/esquema-postgres.sql
--
--  SQLite carece de tipo decimal. Todo importe se guarda como ENTERO
--  ESCALADO y se convierte a Decimal en la capa datos/. Escalas:
--
--    precios y costos unitarios  x10.000     (4 decimales)
--    totales monetarios          x100        (2 decimales)
--    cantidades                  x1.000      (3 decimales)
--    tasa de cambio              x1.000.000  (6 decimales)
--    porcentajes                 x100        (2 decimales)
--
--  Booleanos como INTEGER 0/1. Fechas como TEXT ISO 8601 en hora local
--  (RNF-14): 'AAAA-MM-DD' o 'AAAA-MM-DD HH:MM:SS'.
--
--  Idempotente: se ejecuta en cada apertura de la base.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. SEGURIDAD Y CONFIGURACION
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS usuario (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario    TEXT    NOT NULL UNIQUE,
    nombre     TEXT    NOT NULL,
    hash_clave TEXT    NOT NULL,
    rol        TEXT    NOT NULL,
    activo     INTEGER NOT NULL DEFAULT 1,
    creado_en  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    CONSTRAINT ck_usuario_rol CHECK (rol IN ('ADMIN','CAJERO')),
    CONSTRAINT ck_usuario_activo CHECK (activo IN (0,1))
);

CREATE TABLE IF NOT EXISTS configuracion (
    clave          TEXT PRIMARY KEY,
    valor          TEXT NOT NULL,
    descripcion    TEXT,
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS auditoria (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id    INTEGER NOT NULL REFERENCES usuario(id),
    accion        TEXT    NOT NULL,
    entidad       TEXT    NOT NULL,
    entidad_id    INTEGER,
    datos_antes   TEXT,
    datos_despues TEXT,
    fecha_hora    TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS respaldo (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    ruta         TEXT    NOT NULL,
    tamano_bytes INTEGER,
    estado       TEXT    NOT NULL,
    mensaje      TEXT,
    CONSTRAINT ck_respaldo_estado CHECK (estado IN ('OK','ERROR'))
);

-- ---------------------------------------------------------------------
-- 2. CATALOGO
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS categoria (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT    NOT NULL UNIQUE,
    margen_objetivo INTEGER NOT NULL DEFAULT 3000,   -- x100 -> 30,00 %
    activo          INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT ck_categoria_margen CHECK (margen_objetivo >= 0),
    CONSTRAINT ck_categoria_activo CHECK (activo IN (0,1))
);

CREATE TABLE IF NOT EXISTS alicuota_iva (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo     TEXT    NOT NULL UNIQUE,             -- EXENTO | GENERAL | REDUCIDA
    nombre     TEXT    NOT NULL,
    porcentaje INTEGER NOT NULL,                    -- x100 -> 1600 = 16,00 %
    activo     INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT ck_alicuota_rango CHECK (porcentaje >= 0 AND porcentaje <= 10000),
    CONSTRAINT ck_alicuota_activo CHECK (activo IN (0,1))
);

CREATE TABLE IF NOT EXISTS producto (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_barras      TEXT    NULL,
    nombre             TEXT    NOT NULL,
    categoria_id       INTEGER NOT NULL REFERENCES categoria(id),
    alicuota_iva_id    INTEGER NOT NULL REFERENCES alicuota_iva(id),
    precio_venta_usd   INTEGER NOT NULL DEFAULT 0,  -- x10000, IVA INCLUIDO
    margen_objetivo    INTEGER NULL,                -- x100; NULL usa el de la categoria
    existencia_minima  INTEGER NOT NULL DEFAULT 0,  -- x1000
    maneja_vencimiento INTEGER NOT NULL DEFAULT 0,
    dias_alerta_venc   INTEGER NOT NULL DEFAULT 15,
    activo             INTEGER NOT NULL DEFAULT 1,
    creado_en          TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    actualizado_en     TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    CONSTRAINT ck_producto_precio CHECK (precio_venta_usd >= 0),
    CONSTRAINT ck_producto_minima CHECK (existencia_minima >= 0),
    CONSTRAINT ck_producto_venc CHECK (maneja_vencimiento IN (0,1)),
    CONSTRAINT ck_producto_activo CHECK (activo IN (0,1))
);

-- Indice unico parcial: varios productos pueden no tener codigo de barras.
CREATE UNIQUE INDEX IF NOT EXISTS ux_producto_codigo_barras
    ON producto (codigo_barras) WHERE codigo_barras IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_producto_nombre ON producto (LOWER(nombre));
CREATE INDEX IF NOT EXISTS ix_producto_categoria ON producto (categoria_id);

CREATE TABLE IF NOT EXISTS lote (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id       INTEGER NOT NULL REFERENCES producto(id),
    codigo            TEXT,
    fecha_vencimiento TEXT    NOT NULL,             -- AAAA-MM-DD
    creado_en         TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS ix_lote_producto_venc ON lote (producto_id, fecha_vencimiento);

-- ---------------------------------------------------------------------
-- 3. TASA DE CAMBIO
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tasa_cambio (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha         TEXT    NOT NULL UNIQUE,          -- RN-02: una tasa por fecha
    valor         INTEGER NOT NULL,                 -- x1000000
    origen        TEXT    NOT NULL,
    usuario_id    INTEGER NULL REFERENCES usuario(id),
    registrado_en TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    CONSTRAINT ck_tasa_positiva CHECK (valor > 0),
    CONSTRAINT ck_tasa_origen CHECK (origen IN ('BCV_AUTO','MANUAL'))
);

-- ---------------------------------------------------------------------
-- 4. COMPRAS
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS proveedor (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre   TEXT    NOT NULL,
    rif      TEXT,
    telefono TEXT,
    contacto TEXT,
    activo   INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT ck_proveedor_activo CHECK (activo IN (0,1))
);

CREATE TABLE IF NOT EXISTS compra (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    proveedor_id        INTEGER NOT NULL REFERENCES proveedor(id),
    numero_documento    TEXT,
    fecha               TEXT    NOT NULL,           -- AAAA-MM-DD
    tasa_id             INTEGER NOT NULL REFERENCES tasa_cambio(id),
    total_usd           INTEGER NOT NULL DEFAULT 0, -- x100
    saldo_pendiente_usd INTEGER NOT NULL DEFAULT 0, -- x100
    estado              TEXT    NOT NULL DEFAULT 'CONFIRMADA',
    usuario_id          INTEGER NOT NULL REFERENCES usuario(id),
    observacion         TEXT,
    creado_en           TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    CONSTRAINT ck_compra_estado CHECK (estado IN ('CONFIRMADA','ANULADA'))
);
CREATE INDEX IF NOT EXISTS ix_compra_fecha ON compra (fecha);

CREATE TABLE IF NOT EXISTS compra_detalle (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    compra_id           INTEGER NOT NULL REFERENCES compra(id),
    producto_id         INTEGER NOT NULL REFERENCES producto(id),
    cant_presentacion   INTEGER NOT NULL,           -- x1000
    unid_x_presentacion INTEGER NOT NULL DEFAULT 1000,  -- x1000; RN-06, por linea
    cantidad_unidades   INTEGER NOT NULL,           -- x1000
    costo_present_usd   INTEGER NOT NULL,           -- x10000
    costo_unitario_usd  INTEGER NOT NULL,           -- x10000
    lote_id             INTEGER NULL REFERENCES lote(id),
    CONSTRAINT ck_cd_cantidades CHECK (cant_presentacion > 0 AND unid_x_presentacion > 0)
);
CREATE INDEX IF NOT EXISTS ix_compra_detalle_producto ON compra_detalle (producto_id);

CREATE TABLE IF NOT EXISTS pago_proveedor (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    compra_id  INTEGER NOT NULL REFERENCES compra(id),
    fecha      TEXT    NOT NULL,
    monto_usd  INTEGER NOT NULL,                    -- x100
    tasa_id    INTEGER NOT NULL REFERENCES tasa_cambio(id),
    medio      TEXT    NOT NULL,
    referencia TEXT,
    CONSTRAINT ck_pago_prov_positivo CHECK (monto_usd > 0)
);
CREATE INDEX IF NOT EXISTS ix_pago_proveedor_compra ON pago_proveedor (compra_id);

-- ---------------------------------------------------------------------
-- 5. INVENTARIO
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS movimiento_inventario (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id        INTEGER NOT NULL REFERENCES producto(id),
    lote_id            INTEGER NULL REFERENCES lote(id),
    tipo               TEXT    NOT NULL,
    cantidad           INTEGER NOT NULL,            -- x1000; + entradas, - salidas
    costo_unitario_usd INTEGER NOT NULL DEFAULT 0,  -- x10000; RN-14, congelado
    referencia_tipo    TEXT    NOT NULL,
    referencia_id      INTEGER NOT NULL,
    fecha_hora         TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    usuario_id         INTEGER NOT NULL REFERENCES usuario(id),
    observacion        TEXT,
    CONSTRAINT ck_mov_cantidad CHECK (cantidad <> 0),
    CONSTRAINT ck_mov_tipo CHECK (tipo IN
        ('INICIAL','COMPRA','VENTA','ANULACION_VENTA','ANULACION_COMPRA','PERDIDA','AJUSTE')),
    CONSTRAINT ck_mov_referencia CHECK (referencia_tipo IN
        ('INICIAL','COMPRA','VENTA','PERDIDA','AJUSTE'))
);
CREATE INDEX IF NOT EXISTS ix_mov_producto_fecha ON movimiento_inventario (producto_id, fecha_hora);
CREATE INDEX IF NOT EXISTS ix_mov_referencia ON movimiento_inventario (referencia_tipo, referencia_id);
CREATE INDEX IF NOT EXISTS ix_mov_lote ON movimiento_inventario (lote_id);

CREATE TABLE IF NOT EXISTS motivo_perdida (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT    NOT NULL UNIQUE,
    nombre TEXT    NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT ck_motivo_activo CHECK (activo IN (0,1))
);

CREATE TABLE IF NOT EXISTS perdida (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id        INTEGER NOT NULL REFERENCES producto(id),
    lote_id            INTEGER NULL REFERENCES lote(id),
    motivo_id          INTEGER NOT NULL REFERENCES motivo_perdida(id),
    cantidad           INTEGER NOT NULL,            -- x1000
    costo_unitario_usd INTEGER NOT NULL,            -- x10000; RN-18
    fecha              TEXT    NOT NULL,
    usuario_id         INTEGER NOT NULL REFERENCES usuario(id),
    observacion        TEXT,
    CONSTRAINT ck_perdida_cantidad CHECK (cantidad > 0)
);
CREATE INDEX IF NOT EXISTS ix_perdida_fecha ON perdida (fecha);

CREATE TABLE IF NOT EXISTS ajuste_inventario (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id      INTEGER NOT NULL REFERENCES producto(id),
    cantidad_sistema INTEGER NOT NULL,              -- x1000
    cantidad_fisica  INTEGER NOT NULL,              -- x1000
    diferencia       INTEGER NOT NULL,              -- x1000
    motivo           TEXT    NOT NULL,
    usuario_id       INTEGER NOT NULL REFERENCES usuario(id),
    fecha            TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ---------------------------------------------------------------------
-- 6. VENTAS Y CAJA
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS caja_sesion (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_apertura_id INTEGER NOT NULL REFERENCES usuario(id),
    fecha_apertura      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    inicial_bs          INTEGER NOT NULL DEFAULT 0, -- x100
    inicial_usd         INTEGER NOT NULL DEFAULT 0, -- x100
    fecha_cierre        TEXT    NULL,
    usuario_cierre_id   INTEGER NULL REFERENCES usuario(id),
    conteo_bs           INTEGER NULL,
    conteo_usd          INTEGER NULL,
    diferencia_bs       INTEGER NULL,
    diferencia_usd      INTEGER NULL,
    estado              TEXT    NOT NULL DEFAULT 'ABIERTA',
    CONSTRAINT ck_caja_estado CHECK (estado IN ('ABIERTA','CERRADA'))
);

-- RF-44 / RN-26: una sola sesion abierta a la vez.
CREATE UNIQUE INDEX IF NOT EXISTS ux_caja_una_abierta
    ON caja_sesion (estado) WHERE estado = 'ABIERTA';

CREATE TABLE IF NOT EXISTS cliente (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo             TEXT NOT NULL DEFAULT 'CONSUMIDOR_FINAL',
    razon_social     TEXT,
    rif              TEXT UNIQUE,
    direccion_fiscal TEXT,
    telefono         TEXT,
    CONSTRAINT ck_cliente_tipo CHECK (tipo IN ('CONSUMIDOR_FINAL','EMPRESA'))
);

CREATE TABLE IF NOT EXISTS venta (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    numero             INTEGER NOT NULL UNIQUE,     -- RN-24, nunca se reutiliza
    caja_sesion_id     INTEGER NOT NULL REFERENCES caja_sesion(id),
    usuario_id         INTEGER NOT NULL REFERENCES usuario(id),
    cliente_id         INTEGER NULL REFERENCES cliente(id),
    tasa_id            INTEGER NOT NULL REFERENCES tasa_cambio(id),
    fecha_hora         TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    exento_usd         INTEGER NOT NULL DEFAULT 0,  -- x100
    base_imponible_usd INTEGER NOT NULL DEFAULT 0,  -- x100
    iva_usd            INTEGER NOT NULL DEFAULT 0,  -- x100
    total_usd          INTEGER NOT NULL DEFAULT 0,  -- x100
    total_bs           INTEGER NOT NULL DEFAULT 0,  -- x100
    vuelto_usd         INTEGER NOT NULL DEFAULT 0,  -- x100
    estado             TEXT    NOT NULL DEFAULT 'COMPLETADA',
    anulada_por        INTEGER NULL REFERENCES usuario(id),
    anulada_en         TEXT    NULL,
    motivo_anulacion   TEXT    NULL,
    CONSTRAINT ck_venta_estado CHECK (estado IN ('COMPLETADA','ANULADA'))
);
CREATE INDEX IF NOT EXISTS ix_venta_fecha ON venta (fecha_hora);
CREATE INDEX IF NOT EXISTS ix_venta_sesion ON venta (caja_sesion_id);

CREATE TABLE IF NOT EXISTS venta_detalle (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id           INTEGER NOT NULL REFERENCES venta(id),
    producto_id        INTEGER NOT NULL REFERENCES producto(id),
    lote_id            INTEGER NULL REFERENCES lote(id),
    descripcion        TEXT    NOT NULL,            -- copia del nombre
    cantidad           INTEGER NOT NULL,            -- x1000
    precio_unit_usd    INTEGER NOT NULL,            -- x10000, con IVA incluido
    alicuota_pct       INTEGER NOT NULL,            -- x100, copia de la alicuota
    base_imponible_usd INTEGER NOT NULL,            -- x100
    iva_usd            INTEGER NOT NULL,            -- x100
    total_linea_usd    INTEGER NOT NULL,            -- x100
    costo_unitario_usd INTEGER NOT NULL,            -- x10000; RN-19, congelado
    CONSTRAINT ck_vd_cantidad CHECK (cantidad > 0)
);
CREATE INDEX IF NOT EXISTS ix_venta_detalle_producto ON venta_detalle (producto_id);
CREATE INDEX IF NOT EXISTS ix_venta_detalle_venta ON venta_detalle (venta_id);

CREATE TABLE IF NOT EXISTS venta_pago (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id   INTEGER NOT NULL REFERENCES venta(id),
    medio      TEXT    NOT NULL,
    moneda     TEXT    NOT NULL,
    monto      INTEGER NOT NULL,                    -- x100, en la moneda original
    monto_usd  INTEGER NOT NULL,                    -- x100, a la tasa de la venta
    referencia TEXT,
    CONSTRAINT ck_pago_medio CHECK (medio IN
        ('EFECTIVO','PAGO_MOVIL','PUNTO','TRANSFERENCIA')),
    CONSTRAINT ck_pago_moneda CHECK (moneda IN ('BS','USD')),
    CONSTRAINT ck_pago_monto CHECK (monto > 0)
);
CREATE INDEX IF NOT EXISTS ix_venta_pago_venta ON venta_pago (venta_id);

-- ---------------------------------------------------------------------
-- 7. GASTOS OPERATIVOS
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gasto_operativo (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria   TEXT    NOT NULL,
    descripcion TEXT    NOT NULL,
    monto_usd   INTEGER NOT NULL,                   -- x100
    periodo     TEXT    NOT NULL,                   -- AAAA-MM
    fecha       TEXT    NOT NULL,
    usuario_id  INTEGER NOT NULL REFERENCES usuario(id),
    CONSTRAINT ck_gasto_positivo CHECK (monto_usd > 0),
    CONSTRAINT ck_gasto_categoria CHECK (categoria IN
        ('ALQUILER','SERVICIOS','SUELDOS','OTROS'))
);
CREATE INDEX IF NOT EXISTS ix_gasto_periodo ON gasto_operativo (periodo);

-- ---------------------------------------------------------------------
-- 8. VISTAS DE APOYO
-- ---------------------------------------------------------------------

-- RN-11: la existencia es la suma de los movimientos, nunca un campo.
CREATE VIEW IF NOT EXISTS v_existencia AS
SELECT p.id                        AS producto_id,
       p.nombre                    AS nombre,
       COALESCE(SUM(m.cantidad), 0) AS existencia
FROM producto p
LEFT JOIN movimiento_inventario m ON m.producto_id = p.id
GROUP BY p.id, p.nombre;

-- RN-07: ultimo costo = compra confirmada mas reciente, desempate por id.
-- El original usaba DISTINCT ON, exclusivo de PostgreSQL.
CREATE VIEW IF NOT EXISTS v_ultimo_costo AS
SELECT producto_id, costo_unitario_usd, fecha
FROM (
    SELECT cd.producto_id,
           cd.costo_unitario_usd,
           c.fecha,
           ROW_NUMBER() OVER (
               PARTITION BY cd.producto_id
               ORDER BY c.fecha DESC, cd.id DESC
           ) AS fila
    FROM compra_detalle cd
    JOIN compra c ON c.id = cd.compra_id
    WHERE c.estado = 'CONFIRMADA'
)
WHERE fila = 1;

-- ---------------------------------------------------------------------
-- 9. DATOS INICIALES
-- ---------------------------------------------------------------------

INSERT OR IGNORE INTO alicuota_iva (codigo, nombre, porcentaje) VALUES
    ('EXENTO',   'Exento',              0),
    ('GENERAL',  'Alicuota general', 1600),
    ('REDUCIDA', 'Alicuota reducida', 800);

INSERT OR IGNORE INTO motivo_perdida (codigo, nombre) VALUES
    ('VENCIDO',           'Producto vencido'),
    ('DANADO',            'Producto danado o roto'),
    ('FALTANTE',          'Faltante o sustraccion'),
    ('MERMA_CHARCUTERIA', 'Merma de charcuteria'),
    ('CONSUMO_PROPIO',    'Consumo propio del negocio');

INSERT OR IGNORE INTO configuracion (clave, valor, descripcion) VALUES
    ('negocio.nombre',         '',       'Razon social del establecimiento'),
    ('negocio.rif',            '',       'RIF del establecimiento'),
    ('negocio.direccion',      '',       'Direccion fiscal'),
    ('negocio.telefono',       '',       'Telefono de contacto'),
    ('negocio.logo',           '',       'Ruta del archivo de logotipo para los reportes'),
    ('precio.redondeo_bs',     '1',      'Multiplo de redondeo del precio en bolivares'),
    ('precio.modo_redondeo',   'ARRIBA', 'Sentido del redondeo comercial'),
    ('vencimiento.dias_aviso', '15',     'Dias de aviso por defecto'),
    ('impresora.destino',      '',       'Impresora ESC/POS: nombre en Windows o ruta del dispositivo'),
    ('respaldo.ruta',          '',       'Carpeta de destino del respaldo diario'),
    ('respaldo.hora',          '22:00',  'Hora de ejecucion del respaldo'),
    ('bcv.url',                '',       'Origen de consulta de la tasa oficial');

-- Usuario de arranque. movimiento_inventario.usuario_id y caja_sesion son NOT
-- NULL, pero la autenticacion es de la Fase 4: sin esta fila las fases 2 y 3 no
-- podrian registrar nada. hash_clave vacio significa "sin clave definida" y no
-- puede autenticar: el asistente de primer arranque (Fase 6) la establece.
INSERT OR IGNORE INTO usuario (usuario, nombre, hash_clave, rol) VALUES
    ('admin', 'Administrador', '', 'ADMIN');
