-- =====================================================================
--  Sistema de gestión para minimarket — Opción C
--  Borealis Software Solutions
--  Esquema de base de datos · versión 1.0
--
--  Sintaxis: PostgreSQL.
--  Todos los importes usan NUMERIC (decimal de precisión fija).
--  Nunca usar tipos de punto flotante para valores monetarios.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. SEGURIDAD Y CONFIGURACIÓN
-- ---------------------------------------------------------------------

CREATE TABLE usuario (
    id            SERIAL PRIMARY KEY,
    usuario       VARCHAR(40)  NOT NULL UNIQUE,
    nombre        VARCHAR(120) NOT NULL,
    hash_clave    VARCHAR(255) NOT NULL,
    rol           VARCHAR(20)  NOT NULL,          -- ADMIN | CAJERO
    activo        BOOLEAN      NOT NULL DEFAULT TRUE,
    creado_en     TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_usuario_rol CHECK (rol IN ('ADMIN','CAJERO'))
);

CREATE TABLE configuracion (
    clave         VARCHAR(60)  PRIMARY KEY,
    valor         TEXT         NOT NULL,
    descripcion   VARCHAR(250),
    actualizado_en TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE TABLE auditoria (
    id            BIGSERIAL PRIMARY KEY,
    usuario_id    INTEGER      NOT NULL REFERENCES usuario(id),
    accion        VARCHAR(40)  NOT NULL,
    entidad       VARCHAR(40)  NOT NULL,
    entidad_id    INTEGER,
    datos_antes   TEXT,
    datos_despues TEXT,
    fecha_hora    TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE TABLE respaldo (
    id            SERIAL PRIMARY KEY,
    fecha_hora    TIMESTAMP    NOT NULL DEFAULT NOW(),
    ruta          VARCHAR(400) NOT NULL,
    tamano_bytes  BIGINT,
    estado        VARCHAR(20)  NOT NULL,          -- OK | ERROR
    mensaje       VARCHAR(400)
);

-- ---------------------------------------------------------------------
-- 2. CATÁLOGO
-- ---------------------------------------------------------------------

CREATE TABLE categoria (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(80)   NOT NULL UNIQUE,
    margen_objetivo NUMERIC(6,2)  NOT NULL DEFAULT 30.00,
    activo          BOOLEAN       NOT NULL DEFAULT TRUE
);

CREATE TABLE alicuota_iva (
    id          SERIAL PRIMARY KEY,
    codigo      VARCHAR(20)  NOT NULL UNIQUE,     -- EXENTO | GENERAL | REDUCIDA
    nombre      VARCHAR(60)  NOT NULL,
    porcentaje  NUMERIC(5,2) NOT NULL,
    activo      BOOLEAN      NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_alicuota_rango CHECK (porcentaje >= 0 AND porcentaje <= 100)
);

CREATE TABLE producto (
    id                  SERIAL PRIMARY KEY,
    codigo_barras       VARCHAR(40)  NULL,
    nombre              VARCHAR(150) NOT NULL,
    categoria_id        INTEGER      NOT NULL REFERENCES categoria(id),
    alicuota_iva_id     INTEGER      NOT NULL REFERENCES alicuota_iva(id),
    precio_venta_usd    NUMERIC(12,4) NOT NULL DEFAULT 0,   -- IVA incluido
    margen_objetivo     NUMERIC(6,2)  NULL,                 -- si es NULL usa el de la categoría
    existencia_minima   NUMERIC(12,3) NOT NULL DEFAULT 0,
    maneja_vencimiento  BOOLEAN       NOT NULL DEFAULT FALSE,
    dias_alerta_venc    INTEGER       NOT NULL DEFAULT 15,
    activo              BOOLEAN       NOT NULL DEFAULT TRUE,
    creado_en           TIMESTAMP     NOT NULL DEFAULT NOW(),
    actualizado_en      TIMESTAMP     NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_producto_precio CHECK (precio_venta_usd >= 0)
);

-- Índice único parcial: varios productos pueden no tener código de barras.
CREATE UNIQUE INDEX ux_producto_codigo_barras
    ON producto (codigo_barras) WHERE codigo_barras IS NOT NULL;
CREATE INDEX ix_producto_nombre ON producto (LOWER(nombre));
CREATE INDEX ix_producto_categoria ON producto (categoria_id);

CREATE TABLE lote (
    id                SERIAL PRIMARY KEY,
    producto_id       INTEGER     NOT NULL REFERENCES producto(id),
    codigo            VARCHAR(40),
    fecha_vencimiento DATE        NOT NULL,
    creado_en         TIMESTAMP   NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_lote_producto_venc ON lote (producto_id, fecha_vencimiento);

-- ---------------------------------------------------------------------
-- 3. TASA DE CAMBIO
-- ---------------------------------------------------------------------

CREATE TABLE tasa_cambio (
    id            SERIAL PRIMARY KEY,
    fecha         DATE          NOT NULL UNIQUE,
    valor         NUMERIC(18,6) NOT NULL,
    origen        VARCHAR(15)   NOT NULL,        -- BCV_AUTO | MANUAL
    usuario_id    INTEGER       NULL REFERENCES usuario(id),
    registrado_en TIMESTAMP     NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_tasa_positiva CHECK (valor > 0),
    CONSTRAINT ck_tasa_origen CHECK (origen IN ('BCV_AUTO','MANUAL'))
);

-- ---------------------------------------------------------------------
-- 4. COMPRAS
-- ---------------------------------------------------------------------

CREATE TABLE proveedor (
    id        SERIAL PRIMARY KEY,
    nombre    VARCHAR(150) NOT NULL,
    rif       VARCHAR(20),
    telefono  VARCHAR(30),
    contacto  VARCHAR(120),
    activo    BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE TABLE compra (
    id                  SERIAL PRIMARY KEY,
    proveedor_id        INTEGER       NOT NULL REFERENCES proveedor(id),
    numero_documento    VARCHAR(40),
    fecha               DATE          NOT NULL,
    tasa_id             INTEGER       NOT NULL REFERENCES tasa_cambio(id),
    total_usd           NUMERIC(14,2) NOT NULL DEFAULT 0,
    saldo_pendiente_usd NUMERIC(14,2) NOT NULL DEFAULT 0,
    estado              VARCHAR(15)   NOT NULL DEFAULT 'CONFIRMADA',
    usuario_id          INTEGER       NOT NULL REFERENCES usuario(id),
    observacion         VARCHAR(250),
    creado_en           TIMESTAMP     NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_compra_estado CHECK (estado IN ('CONFIRMADA','ANULADA'))
);
CREATE INDEX ix_compra_fecha ON compra (fecha);

CREATE TABLE compra_detalle (
    id                  SERIAL PRIMARY KEY,
    compra_id           INTEGER       NOT NULL REFERENCES compra(id),
    producto_id         INTEGER       NOT NULL REFERENCES producto(id),
    cant_presentacion   NUMERIC(12,3) NOT NULL,
    unid_x_presentacion NUMERIC(12,3) NOT NULL DEFAULT 1,
    cantidad_unidades   NUMERIC(14,3) NOT NULL,
    costo_present_usd   NUMERIC(12,4) NOT NULL,
    costo_unitario_usd  NUMERIC(12,4) NOT NULL,
    lote_id             INTEGER       NULL REFERENCES lote(id),
    CONSTRAINT ck_cd_cantidades CHECK (cant_presentacion > 0 AND unid_x_presentacion > 0)
);
CREATE INDEX ix_compra_detalle_producto ON compra_detalle (producto_id);

CREATE TABLE pago_proveedor (
    id          SERIAL PRIMARY KEY,
    compra_id   INTEGER       NOT NULL REFERENCES compra(id),
    fecha       DATE          NOT NULL,
    monto_usd   NUMERIC(14,2) NOT NULL,
    tasa_id     INTEGER       NOT NULL REFERENCES tasa_cambio(id),
    medio       VARCHAR(20)   NOT NULL,
    referencia  VARCHAR(60),
    CONSTRAINT ck_pago_positivo CHECK (monto_usd > 0)
);

-- ---------------------------------------------------------------------
-- 5. INVENTARIO
-- ---------------------------------------------------------------------

CREATE TABLE movimiento_inventario (
    id                 BIGSERIAL PRIMARY KEY,
    producto_id        INTEGER       NOT NULL REFERENCES producto(id),
    lote_id            INTEGER       NULL REFERENCES lote(id),
    tipo               VARCHAR(20)   NOT NULL,
    cantidad           NUMERIC(14,3) NOT NULL,   -- + entradas, - salidas
    costo_unitario_usd NUMERIC(12,4) NOT NULL DEFAULT 0,
    referencia_tipo    VARCHAR(30)   NOT NULL,   -- COMPRA | VENTA | PERDIDA | AJUSTE | INICIAL
    referencia_id      INTEGER       NOT NULL,
    fecha_hora         TIMESTAMP     NOT NULL DEFAULT NOW(),
    usuario_id         INTEGER       NOT NULL REFERENCES usuario(id),
    observacion        VARCHAR(250),
    CONSTRAINT ck_mov_cantidad CHECK (cantidad <> 0),
    CONSTRAINT ck_mov_tipo CHECK (tipo IN
        ('INICIAL','COMPRA','VENTA','ANULACION_VENTA','ANULACION_COMPRA','PERDIDA','AJUSTE'))
);
CREATE INDEX ix_mov_producto_fecha ON movimiento_inventario (producto_id, fecha_hora);
CREATE INDEX ix_mov_referencia ON movimiento_inventario (referencia_tipo, referencia_id);
CREATE INDEX ix_mov_lote ON movimiento_inventario (lote_id);

CREATE TABLE motivo_perdida (
    id      SERIAL PRIMARY KEY,
    codigo  VARCHAR(30) NOT NULL UNIQUE,
    nombre  VARCHAR(80) NOT NULL,
    activo  BOOLEAN     NOT NULL DEFAULT TRUE
);

CREATE TABLE perdida (
    id                 SERIAL PRIMARY KEY,
    producto_id        INTEGER       NOT NULL REFERENCES producto(id),
    lote_id            INTEGER       NULL REFERENCES lote(id),
    motivo_id          INTEGER       NOT NULL REFERENCES motivo_perdida(id),
    cantidad           NUMERIC(14,3) NOT NULL,
    costo_unitario_usd NUMERIC(12,4) NOT NULL,
    fecha              DATE          NOT NULL,
    usuario_id         INTEGER       NOT NULL REFERENCES usuario(id),
    observacion        VARCHAR(250),
    CONSTRAINT ck_perdida_cantidad CHECK (cantidad > 0)
);
CREATE INDEX ix_perdida_fecha ON perdida (fecha);

CREATE TABLE ajuste_inventario (
    id               SERIAL PRIMARY KEY,
    producto_id      INTEGER       NOT NULL REFERENCES producto(id),
    cantidad_sistema NUMERIC(14,3) NOT NULL,
    cantidad_fisica  NUMERIC(14,3) NOT NULL,
    diferencia       NUMERIC(14,3) NOT NULL,
    motivo           VARCHAR(200)  NOT NULL,
    usuario_id       INTEGER       NOT NULL REFERENCES usuario(id),
    fecha            TIMESTAMP     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------
-- 6. VENTAS Y CAJA
-- ---------------------------------------------------------------------

CREATE TABLE caja_sesion (
    id                  SERIAL PRIMARY KEY,
    usuario_apertura_id INTEGER       NOT NULL REFERENCES usuario(id),
    fecha_apertura      TIMESTAMP     NOT NULL DEFAULT NOW(),
    inicial_bs          NUMERIC(16,2) NOT NULL DEFAULT 0,
    inicial_usd         NUMERIC(14,2) NOT NULL DEFAULT 0,
    fecha_cierre        TIMESTAMP     NULL,
    usuario_cierre_id   INTEGER       NULL REFERENCES usuario(id),
    conteo_bs           NUMERIC(16,2) NULL,
    conteo_usd          NUMERIC(14,2) NULL,
    diferencia_bs       NUMERIC(16,2) NULL,
    diferencia_usd      NUMERIC(14,2) NULL,
    estado              VARCHAR(10)   NOT NULL DEFAULT 'ABIERTA',
    CONSTRAINT ck_caja_estado CHECK (estado IN ('ABIERTA','CERRADA'))
);

-- Solo una sesión abierta a la vez.
CREATE UNIQUE INDEX ux_caja_una_abierta
    ON caja_sesion ((estado)) WHERE estado = 'ABIERTA';

CREATE TABLE cliente (
    id               SERIAL PRIMARY KEY,
    tipo             VARCHAR(20)  NOT NULL DEFAULT 'CONSUMIDOR_FINAL',
    razon_social     VARCHAR(150),
    rif              VARCHAR(20)  UNIQUE,
    direccion_fiscal VARCHAR(250),
    telefono         VARCHAR(30),
    CONSTRAINT ck_cliente_tipo CHECK (tipo IN ('CONSUMIDOR_FINAL','EMPRESA'))
);

CREATE TABLE venta (
    id                 SERIAL PRIMARY KEY,
    numero             INTEGER       NOT NULL UNIQUE,
    caja_sesion_id     INTEGER       NOT NULL REFERENCES caja_sesion(id),
    usuario_id         INTEGER       NOT NULL REFERENCES usuario(id),
    cliente_id         INTEGER       NULL REFERENCES cliente(id),
    tasa_id            INTEGER       NOT NULL REFERENCES tasa_cambio(id),
    fecha_hora         TIMESTAMP     NOT NULL DEFAULT NOW(),
    exento_usd         NUMERIC(14,2) NOT NULL DEFAULT 0,
    base_imponible_usd NUMERIC(14,2) NOT NULL DEFAULT 0,
    iva_usd            NUMERIC(14,2) NOT NULL DEFAULT 0,
    total_usd          NUMERIC(14,2) NOT NULL DEFAULT 0,
    total_bs           NUMERIC(18,2) NOT NULL DEFAULT 0,
    vuelto_usd         NUMERIC(14,2) NOT NULL DEFAULT 0,
    estado             VARCHAR(12)   NOT NULL DEFAULT 'COMPLETADA',
    anulada_por        INTEGER       NULL REFERENCES usuario(id),
    anulada_en         TIMESTAMP     NULL,
    motivo_anulacion   VARCHAR(200)  NULL,
    CONSTRAINT ck_venta_estado CHECK (estado IN ('COMPLETADA','ANULADA'))
);
CREATE INDEX ix_venta_fecha ON venta (fecha_hora);
CREATE INDEX ix_venta_sesion ON venta (caja_sesion_id);

CREATE TABLE venta_detalle (
    id                 SERIAL PRIMARY KEY,
    venta_id           INTEGER       NOT NULL REFERENCES venta(id),
    producto_id        INTEGER       NOT NULL REFERENCES producto(id),
    lote_id            INTEGER       NULL REFERENCES lote(id),
    descripcion        VARCHAR(150)  NOT NULL,   -- copia del nombre
    cantidad           NUMERIC(14,3) NOT NULL,
    precio_unit_usd    NUMERIC(12,4) NOT NULL,   -- con IVA incluido
    alicuota_pct       NUMERIC(5,2)  NOT NULL,   -- copia de la alícuota
    base_imponible_usd NUMERIC(14,2) NOT NULL,
    iva_usd            NUMERIC(14,2) NOT NULL,
    total_linea_usd    NUMERIC(14,2) NOT NULL,
    costo_unitario_usd NUMERIC(12,4) NOT NULL,   -- copia del costo (RN-19)
    CONSTRAINT ck_vd_cantidad CHECK (cantidad > 0)
);
CREATE INDEX ix_venta_detalle_producto ON venta_detalle (producto_id);
CREATE INDEX ix_venta_detalle_venta ON venta_detalle (venta_id);

CREATE TABLE venta_pago (
    id         SERIAL PRIMARY KEY,
    venta_id   INTEGER       NOT NULL REFERENCES venta(id),
    medio      VARCHAR(20)   NOT NULL,  -- EFECTIVO | PAGO_MOVIL | PUNTO | TRANSFERENCIA
    moneda     VARCHAR(3)    NOT NULL,  -- BS | USD
    monto      NUMERIC(18,2) NOT NULL,  -- en la moneda original
    monto_usd  NUMERIC(14,2) NOT NULL,  -- equivalente a la tasa de la venta
    referencia VARCHAR(60),
    CONSTRAINT ck_pago_moneda CHECK (moneda IN ('BS','USD')),
    CONSTRAINT ck_pago_monto CHECK (monto > 0)
);
CREATE INDEX ix_venta_pago_venta ON venta_pago (venta_id);

-- ---------------------------------------------------------------------
-- 7. GASTOS OPERATIVOS
-- ---------------------------------------------------------------------

CREATE TABLE gasto_operativo (
    id          SERIAL PRIMARY KEY,
    categoria   VARCHAR(30)   NOT NULL,  -- ALQUILER | SERVICIOS | SUELDOS | OTROS
    descripcion VARCHAR(150)  NOT NULL,
    monto_usd   NUMERIC(14,2) NOT NULL,
    periodo     CHAR(7)       NOT NULL,  -- AAAA-MM
    fecha       DATE          NOT NULL,
    usuario_id  INTEGER       NOT NULL REFERENCES usuario(id),
    CONSTRAINT ck_gasto_positivo CHECK (monto_usd > 0)
);
CREATE INDEX ix_gasto_periodo ON gasto_operativo (periodo);

-- ---------------------------------------------------------------------
-- 8. VISTAS DE APOYO
-- ---------------------------------------------------------------------

-- Existencia actual por producto (RN-11)
CREATE VIEW v_existencia AS
SELECT p.id                AS producto_id,
       p.nombre,
       COALESCE(SUM(m.cantidad), 0) AS existencia
FROM producto p
LEFT JOIN movimiento_inventario m ON m.producto_id = p.id
GROUP BY p.id, p.nombre;

-- Último costo por producto (RN-07)
CREATE VIEW v_ultimo_costo AS
SELECT DISTINCT ON (cd.producto_id)
       cd.producto_id,
       cd.costo_unitario_usd,
       c.fecha
FROM compra_detalle cd
JOIN compra c ON c.id = cd.compra_id
WHERE c.estado = 'CONFIRMADA'
ORDER BY cd.producto_id, c.fecha DESC, cd.id DESC;

-- ---------------------------------------------------------------------
-- 9. DATOS INICIALES
-- ---------------------------------------------------------------------

INSERT INTO alicuota_iva (codigo, nombre, porcentaje) VALUES
    ('EXENTO',  'Exento',            0.00),
    ('GENERAL', 'Alícuota general', 16.00),
    ('REDUCIDA','Alícuota reducida', 8.00);

INSERT INTO motivo_perdida (codigo, nombre) VALUES
    ('VENCIDO',            'Producto vencido'),
    ('DANADO',             'Producto dañado o roto'),
    ('FALTANTE',           'Faltante o sustracción'),
    ('MERMA_CHARCUTERIA',  'Merma de charcutería'),
    ('CONSUMO_PROPIO',     'Consumo propio del negocio');

INSERT INTO configuracion (clave, valor, descripcion) VALUES
    ('negocio.nombre',        '',      'Razón social del establecimiento'),
    ('negocio.rif',           '',      'RIF del establecimiento'),
    ('negocio.direccion',     '',      'Dirección fiscal'),
    ('negocio.telefono',      '',      'Teléfono de contacto'),
    ('precio.redondeo_bs',    '1',     'Múltiplo de redondeo del precio en bolívares'),
    ('precio.modo_redondeo',  'ARRIBA','Sentido del redondeo comercial'),
    ('vencimiento.dias_aviso','15',    'Días de aviso por defecto'),
    ('respaldo.ruta',         '',      'Carpeta de destino del respaldo diario'),
    ('respaldo.hora',         '22:00', 'Hora de ejecución del respaldo'),
    ('bcv.url',               '',      'Origen de consulta de la tasa oficial');

-- =====================================================================
--  Fin del esquema
-- =====================================================================
