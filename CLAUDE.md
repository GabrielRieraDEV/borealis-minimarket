# Sistema de gestión para minimarket

Aplicación de escritorio para un minimarket en Venezuela. Un solo equipo,
una sola caja, sin conexión permanente a internet.

## Stack
- Python 3.12
- PySide6 (Qt 6) para la interfaz — NUNCA PyQt, por licencia
- SQLite en modo WAL, vía el módulo `sqlite3` de la biblioteca estándar
- Sin ORM: repositorios con SQL escrito a mano
- python-escpos para impresión térmica
- reportlab para PDF
- pytest para pruebas

## Reglas innegociables
1. NUNCA usar `float` para dinero. Siempre `decimal.Decimal`.
2. Todo `quantize` debe declarar `ROUND_HALF_UP` de forma explícita.
   El default de Python es ROUND_HALF_EVEN y contradice la especificación.
3. Los importes se guardan en SQLite como enteros escalados:
   - precios y costos unitarios: x10.000 (4 decimales)
   - totales monetarios: x100 (2 decimales)
   - cantidades: x1.000 (3 decimales)
   - tasa de cambio: x1.000.000 (6 decimales)
   - porcentajes: x100 (2 decimales)
   La conversión vive SOLO en la capa `datos/`. El resto del código usa Decimal.
4. La existencia de un producto NUNCA es un campo editable. Es la suma de
   `movimiento_inventario`.
5. Cada línea de venta guarda copia del costo unitario del momento.
   Cambiar el costo de un producto no debe alterar ganancias históricas.
6. Nada se borra. Las correcciones son movimientos inversos.
7. El respaldo usa `conexion.backup(destino)`, NUNCA copia de archivo (WAL).
8. Todo texto visible al usuario va en español.

## Capas y dependencias

```
minimarket/
    dominio/     entidades y cálculos puros — no importa nada de las otras capas
    datos/       esquema, migraciones, repositorios
    servicios/   casos de uso, coordinan dominio + datos en transacciones
    ui/          ventanas PySide6
    infra/       impresora, tasa BCV, respaldo, bitácora, configuración
tests/
```

`dominio/` no importa `datos/`, `ui/` ni `infra/`. Esta regla no se negocia.
`ui/` no habla con `datos/`: pasa siempre por `servicios/`.

## Documentación

- `docs/reglas-de-negocio.md` — fórmulas RN-01 a RN-31 con ejemplos numéricos.
  Los ejemplos son la especificación: si el código da otro resultado, el código
  está mal (salvo la excepción anotada abajo en «Erratas detectadas»).
- `docs/requisitos.md` — requisitos RF-01 a RF-64 y RNF-01 a RNF-14.
- `docs/modelo-de-datos.md` — las 23 tablas y sus relaciones.
- `docs/esquema-postgres.sql` — esquema de referencia en sintaxis PostgreSQL.
  NO es el esquema de la aplicación: `minimarket/datos/esquema.sql` es la
  adaptación a SQLite con enteros escalados, y es la que manda.
- `docs/plan-de-fases-claude-code.md` — las 7 fases del proyecto.
- Los `.docx` son las fuentes originales; los `.md` son su extracción de texto.
  Si se edita un `.docx`, hay que regenerar el `.md`.

## Convenciones

- Nombres de tablas, campos y variables de dominio en español.
- Docstrings citando el requisito o regla que implementan: `# RN-05`, `# RF-34`.
- Type hints en todas las funciones públicas.
- Fechas y horas en zona local (RNF-14), como texto ISO 8601 sin zona:
  `AAAA-MM-DD` o `AAAA-MM-DD HH:MM:SS`. El esquema las pone con
  `DEFAULT (datetime('now','localtime'))`. Nunca `datetime('now')` a secas,
  que devuelve UTC.
- Ninguna función fuera de `dominio/dinero.py` llama a `quantize` ni multiplica
  por una escala a mano. Se usan `redondear`, `a_entero` y `desde_entero`.

## Estado del proyecto

Fase actual: **Fase 5 — Pérdidas, vencimientos y resultados** (sin empezar).

Fase 0 terminada: `dominio/dinero.py`, `dominio/impuestos.py`,
`datos/esquema.sql` (23 tablas + 2 vistas), `datos/conexion.py` y 80 pruebas
que verifican los ejemplos A, B y C.

Fase 1 terminada: `datos/repositorios/` (categoria, alicuota, producto, tasa,
configuracion), `dominio/producto.py`, `dominio/tasa.py`, `servicios/catalogo.py`,
`servicios/tasa.py`, `infra/bcv.py` y la interfaz (`ui/principal.py`,
`ui/productos.py`, `ui/categorias.py`, `ui/tasa.py`, `ui/comunes.py`).
116 pruebas. La app arranca con `python -m minimarket`.

Fase 2 terminada: `dominio/inventario.py` (kardex, RN-06, RN-11 a RN-18),
`dominio/compra.py`, `datos/repositorios/` (proveedor, compra, inventario,
usuario), `servicios/compras.py`, `servicios/inventario.py` y la interfaz
(`ui/compras.py`, `ui/inventario.py`). 160 pruebas.

Fase 3 terminada: `dominio/venta.py` (RN-19 a RN-26, tambien `CajaSesion`),
`datos/repositorios/` (venta —con detalle, pagos y cliente— y caja),
`servicios/venta.py`, `servicios/caja.py`, `infra/impresora.py` y la interfaz
(`ui/venta.py`, con el punto de venta, el cobro, el cliente fiscal y la caja).
193 pruebas.

Fase 4 terminada: `dominio/usuario.py` (roles, tabla de permisos y hash scrypt),
`dominio/reportes.py` (RN-27, RN-28, RN-31), `datos/repositorios/` (usuario
completo y reportes), `servicios/usuarios.py`, `servicios/reportes.py`,
`servicios/configuracion.py`, `infra/auditoria.py`, `infra/respaldo.py`,
`infra/pdf.py` y la interfaz (`ui/usuarios.py`, `ui/reportes.py`,
`ui/configuracion.py`, y `ui/principal.py` con el ingreso y las pestañas por
perfil). 240 pruebas.

Una fase por sesión. `pytest` completo al terminar cada una, y commit con el
número de fase en el mensaje.

### Entorno

`.venv` con el paquete instalado en modo editable (`pip install -e ".[dev]"`),
PySide6 incluido. `pythonpath = ["."]` en `pyproject.toml` mantiene a `pytest`
corriendo sin depender de la instalación.

La base vive en `~/Minimarket/minimarket.db`; la variable de entorno
`MINIMARKET_DB` la cambia de lugar (útil para probar sin tocar la real).

## Erratas detectadas en la documentación

Revisadas contra los cálculos antes de empezar. Se anotan acá para que el
código no las reproduzca:

- **Ejemplo B, «Precio en bolívares»**: el documento dice 173,08 Bs.
  `0,8222 × 210,500000 = 173,0731`, que con ROUND_HALF_UP a 2 decimales da
  **173,07**. El test debe esperar 173,07. El redondeo comercial al público
  (174,00) no cambia.
- El resto de los ejemplos A, B y C verifica exacto. En particular la
  comprobación inversa del ejemplo B (`0,8222 / 1,16 = 0,708793… → 0,7088`)
  solo cierra si se redondea a **4** decimales; a 2 no recupera la base.

## Decisiones que atraviesan varias fases

Resueltas en la Fase 0:

- **Usuario semilla**: `movimiento_inventario.usuario_id` y `caja_sesion` son
  NOT NULL, pero los usuarios son Fase 4. El esquema crea `admin` / ADMIN con
  `hash_clave` vacío, que no puede autenticar. La Fase 4 le pone autenticación
  real encima y la Fase 6 le establece la clave en el primer arranque.
- **RN-10 (redondeo comercial)** vive en `dominio/dinero.py` como
  `redondear_comercial`, porque los ejemplos A y B ya lo usan. Solo implementa
  el sentido «hacia arriba» que define la regla; `precio.modo_redondeo` queda en
  `configuracion` por si alguna vez hace falta otro.
- **Traducción a SQLite**: `v_ultimo_costo` usa `ROW_NUMBER` en vez de
  `DISTINCT ON`. `SERIAL` → `INTEGER PRIMARY KEY AUTOINCREMENT`, `NOW()` →
  `datetime('now','localtime')`, `BOOLEAN` → `INTEGER` 0/1 con CHECK,
  `NUMERIC(x,y)` → `INTEGER` escalado.

Resueltas en la Fase 1:

- **`ultimo_costo` (RN-07)** vive en `datos/repositorios/producto.py` y lee la
  vista `v_ultimo_costo`, porque RF-07 y RF-08 lo necesitan antes de que la
  Fase 2 traiga el repositorio de compras. Si la Fase 2 crea el suyo, que
  reutilice esta función en vez de duplicar la consulta.
- **RF-08** se parte en `previsualizar_recalculo` + `aplicar_recalculo`: el
  requisito exige confirmación previa del administrador, y así la pantalla
  muestra exactamente lo que se va a aplicar. Los productos sin costo de compra
  quedan fuera del recálculo.
- **`infra/bcv.py`** raspa HTML de bcv.org.ve. Es frágil por naturaleza: ante
  cualquier falla devuelve `None`, registra en `logging` y nunca propaga. La
  carga manual (RF-11) es siempre la alternativa; RN-04 prohíbe heredar la tasa
  de ayer.
- **Dinero en la interfaz**: nunca `QDoubleSpinBox` (guarda `float`).
  `ui/comunes.a_decimal` lee los campos de texto y acepta coma o punto.

Resueltas en la Fase 2:

- **Usuario de las operaciones**: `servicios.USUARIO_ACTUAL = 1` (el `admin`
  semilla) mientras no haya autenticacion. La Fase 4 lo reemplaza por la sesion
  real y esa constante desaparece.
- **`repartir_por_lote` (RN-15)** devuelve `(None, sobrante)` cuando la salida
  excede los lotes, en vez de fallar. Quien decide si la venta procede es
  RF-27, que mira la existencia total y admite autorizacion del administrador.
- **Anulacion de compra (RF-20)**: se rechaza si la compra tiene pagos
  registrados o si parte de la mercancia ya salio, porque el inverso dejaria
  existencia negativa. La correccion en esos casos es un ajuste o una perdida.
- **`compra_detalle` y `pago_proveedor`** viven en un solo repositorio
  (`datos/repositorios/compra.py`) porque se escriben y se leen siempre con el
  encabezado. `lote` y `movimiento_inventario` comparten
  `datos/repositorios/inventario.py` por el mismo motivo.
- **`datos/repositorios/usuario.py`** existe adelantado y solo expone el rol,
  que es lo que RF-26 necesita. La Fase 4 le agrega alta, baja y autenticacion.
- **Aviso de margen**: `registrar_compra` devuelve los productos que quedaron
  por debajo del margen objetivo con el costo nuevo, pero NO toca precios.
  Cambiarlos sigue siendo el recalculo confirmado de RF-08.
- **Detalle de compra en la interfaz**: se edita agregando y quitando lineas,
  no celda por celda. La edicion en sitio con selector de producto adentro de
  la grilla es varias veces mas codigo y peor con teclado.

Resueltas en la Fase 3:

- **Moneda del vuelto (RN-23)**: la regla deja elegirla, pero `venta` no tiene
  columna donde guardarla. El vuelto se entrega en bolivares —que es el caso
  del ejemplo C y el del pais— y el arqueo lo descuenta del efectivo en Bs,
  ya redondeado por RN-10. Si alguna vez hace falta elegir, es una columna
  `vuelto_moneda` mas una migracion con `PRAGMA user_version`.
- **Arqueo (RN-26)**: `servicios/caja.py` calcula el esperado por medio y
  moneda. Solo los renglones de efectivo llevan conteo fisico y diferencia,
  que es lo unico que `caja_sesion` guarda; los medios electronicos se
  informan sin conteo porque se concilian contra el banco.
- **`dominio/venta.py` tambien tiene la caja** (`CajaSesion`, `LineaCierre`,
  `ResumenCierre`): son dos dataclases y una resta, no dan para un modulo.
- **Una linea de venta por producto, aunque la salida toque dos lotes**:
  `venta_detalle.lote_id` queda en NULL en ese caso y el reparto real vive en
  los movimientos, que es donde se consulta. Partir la linea cambiaria lo que
  ve el cliente en la nota por un detalle de almacen.
- **RF-27** se hace cumplir en `servicios/venta.py`: sin existencia no se
  vende, salvo que un administrador autorice (`autorizado_por`), y entonces la
  existencia queda negativa hasta que un ajuste la corrija.
- **Anulacion (RN-25)**: hoy se valida el ROL de administrador
  (`repo_usuario.es_administrador`), no la clave; la clave llega con la
  autenticacion de la Fase 4 y entra en el mismo punto.
- **Impresion (RF-39)**: `infra/impresora.nota_de_entrega` arma el texto y
  `imprimir` lo manda; el corte esta pensado para que la maquina fiscal
  reemplace solo el segundo paso. El destino sale de la clave de configuracion
  `impresora.destino`; si esta vacia la venta ni intenta imprimir, y si la
  impresora falla se avisa y se ofrece F9 para reimprimir.
- **Interfaz del punto de venta**: un unico campo con el foco permanente. La
  cantidad se teclea como `3*codigo` en vez de agregar un segundo campo por el
  que haya que saltar, y escanear dos veces el mismo producto acumula en el
  renglon que ya existe.

Resueltas en la Fase 4:

- **Sesión del usuario**: `servicios.USUARIO_ACTUAL` desapareció. En su lugar,
  `servicios/__init__.py` guarda la sesión (`iniciar_sesion`, `sesion`,
  `usuario_actual`) y `USUARIO_SEMILLA = 1` es el autor por defecto cuando no
  hay sesión, que es el caso de las pruebas y de `tests/datos_prueba.py`.
- **`ErrorServicio`** es la base de todas las excepciones de la capa. Existe
  porque `ErrorPermiso` puede salir de cualquier servicio y las pantallas
  atrapaban solo la excepción de su módulo. Toda pantalla nueva atrapa
  `ErrorServicio`, no la concreta.
- **Permisos (RF-58)**: la tabla de la sección 6 vive en `dominio/usuario.py`
  como `PERMISOS`, y `servicios/usuarios.exigir` es el único control de acceso.
  La interfaz esconde pestañas y reportes, pero eso es comodidad. Se agregó
  `VER_REPORTES` (solo ADMIN), que la sección 6 no nombra: cubre el reporte de
  ventas, el inventario valorizado y el libro de ventas. El cierre de la propia
  sesión sigue abierto al cajero.
- **Costos ocultos al cajero**: `servicios/inventario.consultar` devuelve
  `ultimo_costo=None` cuando el perfil no tiene `VER_COSTOS`, en vez de que la
  pantalla esconda la columna. El dato no viaja.
- **Anulación de ventas (RN-25)**: `anular_venta` acepta `autorizado_por`, el id
  que devuelve `usuarios.verificar` al validar la clave de un administrador sin
  desplazar la sesión del cajero. La bitácora guarda a los dos.
- **Bitácora (RF-59)**: `infra/auditoria.registrar` se llama DENTRO de la
  transacción de la operación registrada; si la operación se revierte, el
  asiento tampoco queda.
- **CMV en SQL (RN-27)**: `datos/repositorios/reportes.py` suma
  `(cantidad * costo + 50000) / 100000` con enteros, que es ROUND_HALF_UP y da
  lo mismo que `redondear(cantidad × costo, 2)` por línea. Es la única
  aritmética de escala fuera de `dominio/dinero.py`, y vive en `datos/`, que es
  la capa que conoce las escalas.
- **Respaldo diario (RF-61)**: sin hilo ni programador de tareas. Al arrancar,
  `configuracion.respaldo_automatico` mira si ya hubo uno hoy y si pasó la hora
  configurada. El equipo se apaga todas las noches; si algún día queda abierto,
  entra un `QTimer` en la ventana principal y el servicio no cambia.
- **Restauración (RF-63)**: se abre el respaldo en modo lectura y se hace
  `origen.backup(conexion_viva)`. Reemplaza el contenido de la base abierta sin
  tocar archivos, que es lo que WAL exige. Antes se verifica que el `.db` tenga
  las tablas del sistema.
- **Formato del libro de ventas**: `dominio/reportes.COLUMNAS_LIBRO` es la lista
  de columnas; la pantalla y el PDF la recorren. Cuando el contador del cliente
  confirme el formato (cláusula 6.7), se toca ahí y en ningún otro lado.

Pendientes para fases posteriores:

- **RN-17** (alerta de vencimiento) esta en `dominio/inventario.py` como
  `en_alerta_vencimiento`, sin consulta ni pantalla: RF-31 y RF-32 son Fase 5.
- **RF-53 a RF-55** (pérdidas, vencimientos y ganancia real) son Fase 5. Van a
  entrar en `servicios/reportes.py` con el mismo patrón: consulta agregada en
  `datos/repositorios/reportes.py`, fila en `dominio/reportes.py`, permiso
  `REPORTES_GANANCIA` y un generador más en `ui/reportes.py`.
- **Clave del administrador en el primer arranque**: hoy la pide
  `ui/principal.ingresar` con `DialogoClaveInicial`, porque sin eso no se puede
  entrar. La Fase 6 lo mueve al asistente de instalación; el servicio
  (`usuarios.establecer_clave_inicial`) no cambia.
- **Existencia en caché**: el modelo de datos la sugiere por volumen. Hoy es la
  vista `v_existencia`. No materializarla hasta que una medición sobre los 3.000
  productos de prueba lo justifique; RN-11 solo la permite si se recalcula desde
  los movimientos y nunca se edita.
- **Migraciones**: `abrir()` ejecuta `esquema.sql` completo en cada apertura y
  es idempotente (`IF NOT EXISTS` + `INSERT OR IGNORE`). Alcanza mientras el
  esquema solo crezca; el día que haya que cambiar una columna existente hace
  falta versionado con `PRAGMA user_version`.

## Los tres desvíos más probables

Si aparecen, son error: `float` para dinero, un ORM, o PyQt en vez de PySide6.
