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
    __main__.py  arranque: abre la base y se la entrega a la interfaz
    dominio/     entidades y cálculos puros — no importa nada de las otras capas
    datos/       esquema, migraciones, repositorios
    servicios/   casos de uso, coordinan dominio + datos en transacciones
    ui/          ventanas PySide6
    infra/       impresora, tasa BCV, respaldo, bitácora, rutas, configuración
tests/
```

`dominio/` no importa `datos/`, `ui/` ni `infra/`. Esta regla no se negocia.
`ui/` no habla con `datos/`: pasa siempre por `servicios/`. Se verifica con
`grep -rn "from minimarket.datos" minimarket/ui/` — tiene que dar vacío.

El único módulo que conoce dos capas a la vez es `minimarket/__main__.py`, que
es el armado de la aplicación: abre la conexión y llama a `ui.principal.main`
con ella. Las pantallas la reciben ya abierta y no saben de dónde salió.

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

Fase actual: **terminado**. Las siete fases estan cerradas.

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

Fase 5 terminada: `dominio/inventario.py` (`Perdida`, `MotivoPerdida`,
`SaldoLoteProducto`), `dominio/reportes.py` (`GastoOperativo`,
`ResultadoPeriodo`, RN-29), `datos/repositorios/` (perdida, gasto, y
`ultimo_costo_a_fecha` en producto), `servicios/perdidas.py`,
`servicios/gastos.py`, tres reportes más en `servicios/reportes.py` y la
interfaz (`ui/perdidas.py` con el registro y el panel de vencimientos,
`ui/gastos.py`, `ui/inicio.py`). 270 pruebas.

Antes de la Fase 6 se saldó la deuda anotada: `ui/` dejó de importar
`datos/`, el arranque se movió a `minimarket/__main__.py` con
`infra/rutas.py`, y se midió RNF-04 sobre un mes de operación. 272 pruebas.

Fase 6 terminada: `infra/bitacora.py` (RNF-13), `ui/asistente.py` (asistente de
primer arranque), la importación de catálogo desde CSV en `servicios/catalogo.py`,
`minimarket.spec` (PyInstaller onedir), `instalador/minimarket.iss` (Inno Setup),
`herramientas/demostracion.py` y `herramientas/capturas.py`, y la documentación
(`README.md` de instalación, `docs/manual-de-usuario.md` con capturas).
295 pruebas.

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

Resueltas en la Fase 5:

- **RN-18 necesitaba una consulta nueva**: `v_ultimo_costo` siempre da el
  último costo de todos. `repo_producto.ultimo_costo_a_fecha` acota por
  `compra.fecha <= fecha`, para que una pérdida de marzo no se valorice con
  una compra de julio.
- **Producto sin compra previa a la fecha**: la pérdida se registra igual,
  valorizada en cero, y `Perdida.determinable` es False. Mismo criterio que
  `FilaGanancia.determinable` del margen sin costo.
- **Una pérdida, varios lotes**: si la salida toca dos lotes, `perdida.lote_id`
  queda en NULL y el reparto real vive en los movimientos. Es la misma decisión
  que ya se había tomado para `venta_detalle.lote_id` en la Fase 3.
- **RF-31 filtra en el dominio, no en SQL**: `repo_inventario.lotes_con_saldo`
  devuelve todos los lotes vivos y `en_alerta_vencimiento` (RN-17) decide
  cuáles avisan, con los días configurados de cada producto. El techo está
  anotado con un `ponytail:` en el repositorio.
- **`REGISTRAR_GASTOS`** se suma a `PERMISOS` (solo ADMIN). La sección 6 no
  nombra los gastos operativos; van con el mismo criterio que las pérdidas.
- **RF-54 se pide con `VER_EXISTENCIAS`**, no con `VER_REPORTES`: quien atiende
  el mostrador tiene que poder ver qué se le está por vencer. La valorización
  de esos lotes es otra cosa y va en el reporte de pérdidas, que sí es de
  administrador.
- **Gastos por mes, sin prorrateo (RN-29)**: `gastos.total` suma los `periodo`
  entre `desde[:7]` y `hasta[:7]`. Un rango que arranca a mitad de agosto se
  lleva el alquiler de agosto entero, que es exactamente lo que la regla pide.
- **Atajos de teclado**: las teclas de función F4, F6, F7, F9 y F12 ya estaban
  tomadas ADENTRO de las pantallas, así que la navegación de ventana nueva usa
  Ctrl+letra. De paso se corrigió el F4 de «Reportes» que la Fase 4 había
  puesto en conflicto con el F4 de «cliente» del punto de venta.
- **`combo_productos`** se mudó de `ui/compras.py` a `ui/comunes.py` y ahora
  pasa por `catalogo.listado_completo`. Era el único selector de producto y lo
  necesitaba también la pantalla de pérdidas.

Saldadas antes de la Fase 6:

- **`ui/` ya no importa `datos/`**. Las catorce consultas sueltas que quedaban
  en `categorias.py`, `compras.py` y `productos.py` pasan por
  `servicios/catalogo.py` y `servicios/compras.py`. `ultimo_costo` y
  `listar_compras` quedaron detrás de su permiso, que es lo que faltaba: eran
  el agujero por el que un cajero podía ver costos si llegaba a la pantalla.
- **El arranque salió de `ui/`**: `infra/rutas.base_de_datos` decide dónde vive
  el archivo y `minimarket/__main__.py` abre la conexión. `ui.principal.main`
  ahora la recibe. La Fase 6 empaqueta ese punto de entrada sin tocar la
  interfaz.
- **Existencia en caché: medida, no hace falta.** Con 3.000 productos, 500
  ventas y 316 lotes, el reporte más lento es el inventario valorizado con
  0,044 s contra los 5 s de RNF-04. La vista `v_existencia` se queda como está;
  materializarla no compra nada. Lo fija
  `tests/test_rendimiento.test_la_existencia_calculada_no_necesita_cache`.
- **`lotes_con_saldo` devolviendo todos los lotes: medido, no hace falta.**
  RF-54 sobre 316 lotes tarda 0,011 s. RN-17 sigue viviendo una sola vez, en el
  dominio.
- **RNF-04 quedó cubierto por pruebas**: los nueve reportes sobre un mes de
  operación, en `tests/test_rendimiento.py`. `tests/datos_prueba.py` ahora
  marca vencimiento en charcutería, carnicería y hortalizas, porque sin lotes
  la medición de RF-31 y RF-54 corría sobre una tabla vacía.

Resueltas en la Fase 6:

- **Clave del administrador**: `DialogoClaveInicial` se borró.
  `ui/asistente.AsistentePrimerArranque` ocupa su lugar y en la misma pantalla
  deja la clave, los datos fiscales, el logotipo, la carpeta de respaldo y la
  primera tasa. Sigue llamando a `usuarios.establecer_clave_inicial`, que no
  cambió. Lo único obligatorio es la clave: trabar la instalación porque el
  cliente todavía no eligió pendrive no ayuda a nadie.
- **RNF-09 y RNF-13 son la misma decisión**: `infra/bitacora.anotar` guarda el
  texto de la excepción del sistema operativo en el archivo y la pantalla
  muestra qué hacer. Los cuatro puntos que incrustaban el error técnico
  (`respaldo.ejecutar`, `configuracion.restaurar`, `impresora.imprimir`,
  `ui/reportes.exportar`) pasaron por ahí. El resto de los `avisar(str(error))`
  se revisó y queda: son `ErrorServicio`, redactados para el usuario.
- **Una excepción no controlada no cierra la aplicación**: `bitacora.configurar`
  instala `sys.excepthook`, que registra con traza y avisa. El aviso lo pone
  `ui/comunes.avisar_error_no_controlado`, para que `infra/` no importe Qt.
- **`negocio.logo`** es una clave de configuración más y se dibuja en el
  encabezado de los PDF. En la nota de entrega no: la impresora térmica pide
  convertir la imagen a raster y eso es otro problema. Un logo ilegible no
  tumba el reporte, sale sin logo y queda anotado.
- **Importación de catálogo: todo o nada.** Con una fila mal, no entra ninguna
  y se devuelve la lista de errores por fila. Importar «las que se pueda»
  dejaría el archivo a medio cargar, y la segunda pasada duplicaría todo
  producto sin código de barras. Vive en `servicios/catalogo.py` y no en un
  módulo aparte, porque reusa la misma validación que el alta de a uno.
  Solo CSV: leer `.xlsx` nativo pide openpyxl entero para un archivo que el
  cliente carga una vez.
- **Las categorías no se crean solas** al importar: la fila se rechaza con el
  nombre que no existe. Inventarles un margen objetivo rompería RN-09 en
  silencio para todos sus productos.
- **La carpeta de datos la crea la aplicación, no el instalador**: el `.iss`
  no tiene sección `[Dirs]`. El instalador corre elevado y armaría la carpeta
  en el perfil del administrador, no en el de quien atiende la caja. Como no la
  crea, tampoco la borra al desinstalar.
- **Las capturas del manual se generan por programa**
  (`herramientas/capturas.py` con `QWidget.grab()` sobre la base de
  demostración). Hechas a mano envejecen con la primera pantalla que cambie.
- **La base de demostración no reusa `tests/datos_prueba.py`**: ese genera
  3.000 productos con nombres inventados para medir tiempos y para capacitar
  hace falta lo contrario, un puñado de productos que el cajero reconozca.

- **Icono y logotipo**: `recursos/logo.png` es el del cliente (Provisiones
  Jireh C.A.). `herramientas/icono.py` lo recorta y genera
  `recursos/minimarket.ico`, que va en el `.exe`, en el instalador y como dato
  del paquete; `infra/rutas.icono` lo encuentra empaquetado o desde el código,
  y `ui/principal.main` lo pone en `QApplication.setWindowIcon` porque Qt no
  hereda el icono del ejecutable. Si cambia el logo, se corre el script y
  se reempaqueta; el `.ico` no se edita a mano.

- **Identidad visual en un solo archivo**: `ui/estilo.py` es una hoja QSS con
  la paleta del logotipo (verde de la cinta, crema del sello, dorado de las
  letras) sobre el estilo Fusion, porque el nativo de Windows ignora media
  hoja. Ninguna pantalla trae colores propios: `inicio.py` usa `ESTILO_BIEN`
  y `ESTILO_MAL` de ahí. Lo que necesita trato distinto lleva
  `setObjectName` y se selecciona por `#nombre` (el campo del lector, el
  panel del total, el botón principal del cobro). Fuentes: Segoe UI y
  Bahnschrift para los totales, que Windows 10 trae; no se empaqueta ninguna.
- **El total del punto de venta va en bolívares grande y dólares chico**: es
  lo que el cliente paga y mira desde el otro lado del mostrador.
- **Prueba de humo de la interfaz**: `tests/test_interfaz.py` arma la ventana
  principal con todas las pestañas, los diálogos sueltos y una venta desde el
  lector sobre la base de demostración, en `QT_QPA_PLATFORM=offscreen`. Es lo
  que se rompe cuando se renombra un servicio y ninguna prueba de dominio se
  entera. `herramientas/capturas.py` hace lo mismo con la ventana entera y
  guarda las imágenes del manual.

- **`infra/bcv.py` consulta con `verify=False`**: el certificado de
  bcv.org.ve está firmado por una autoridad que Windows y Python no reconocen,
  y con la verificación puesta la consulta fallaba siempre con
  `CERTIFICATE_VERIFY_FAILED` (probado el 3 de septiembre de 2026; con la
  verificación apagada trajo 804,8109). Lo que viaja es un número público que
  el administrador ve antes de guardar; no hay credenciales de por medio.
- **La tasa se muestra con dos decimales** en la barra de estado, el inicio y
  el punto de venta, y con cuatro en la ventana de la tasa, que es como la
  publica el BCV. Se sigue guardando con seis (principio de precisión).
  Mostrar «210.500000» en la barra era ruido.

Después de la entrega (1.1.0), a pedido del cliente:

- **`dominio/reportes.Equilibrio`**: ¿los márgenes cubren los gastos del mes?
  RN-29 responde después de cerrar el mes; esto responde durante, proyectando
  linealmente lo que las ventas dejaron (bruta − pérdidas) por días
  transcurridos contra días del mes, y comparando con los gastos del mes
  entero (que RN-29 no prorratea). Da dos remedios cuando no alcanza: ventas
  necesarias con el margen actual, o margen necesario con las ventas
  proyectadas. Vive en la pantalla de Inicio. Es un `ResultadoPeriodo` más
  dos enteros; no hay tabla nueva.
- **`gastos.repetir_mes_anterior`**: copia los gastos del mes anterior al mes
  indicado. Se niega si el mes ya tiene gastos (duplicaría el alquiler) o si
  el anterior está vacío. Los gastos siguen siendo por mes; esto solo evita
  cargarlos a mano.
- **El aviso de margen de la compra ahora aplica**: `ui/compras._avisar_margenes`
  ofrece «Aplicar los precios sugeridos» y pasa por `catalogo.aplicar_recalculo`,
  con lo que queda en la bitácora como cualquier cambio de precio. Antes era
  informativo y el cliente no encontraba dónde aplicar lo sugerido.

Pendientes:

- **El `.iss` no está compilado ni probado**: hace falta Inno Setup 6.3 en el
  equipo que arma la entrega. El `.spec` sí: `dist/Minimarket/Minimarket.exe`
  arranca, crea la base y escribe la bitácora.
- **Migraciones**: `abrir()` ejecuta `esquema.sql` completo en cada apertura y
  es idempotente (`IF NOT EXISTS` + `INSERT OR IGNORE`). Alcanza mientras el
  esquema solo crezca. El día que haya que cambiar una columna existente hace
  falta un runner con `PRAGMA user_version`; hasta entonces no se estampa nada,
  porque `user_version` arranca en 0 y esa primera migración puede leer el 0
  como «esquema base» sin perder información. Ojo con esto al publicar
  actualizaciones a un cliente que ya tenga datos: un `esquema.sql` cambiado no
  altera las tablas que ya existen.

## Los tres desvíos más probables

Si aparecen, son error: `float` para dinero, un ORM, o PyQt en vez de PySide6.
