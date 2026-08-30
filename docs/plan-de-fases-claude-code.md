# Plan de desarrollo por fases — Sistema minimarket

**Borealis Software Solutions** · Opción C · 11 semanas

---

## Cómo usar este documento

Cada fase tiene un prompt listo para pegar en Claude Code. Antes de empezar:

1. Poné los tres documentos (`Especificación de Requisitos`, `Reglas de Negocio`, `Modelo de Datos`) en una carpeta `docs/` dentro del repositorio, exportados a PDF o Markdown.
2. Creá un `CLAUDE.md` en la raíz con el contenido de la sección siguiente. Claude Code lo lee automáticamente en cada sesión y evita que tengas que repetir el contexto.
3. Corré una fase por sesión. No encadenes dos: revisá y hacé commit antes de seguir.
4. Después de cada fase, corré `pytest` completo. Si algo de una fase anterior se rompió, arreglalo antes de avanzar.

---

## Archivo CLAUDE.md (crealo primero)

```markdown
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
dominio/     entidades y cálculos puros — no importa nada de las otras capas
datos/       esquema, migraciones, repositorios
servicios/   casos de uso, coordinan dominio + datos en transacciones
ui/          ventanas PySide6
infra/       impresora, tasa BCV, respaldo, bitácora, configuración
tests/
```
`dominio/` no importa `datos/`, `ui/` ni `infra/`. Esta regla no se negocia.

## Documentación
- `docs/reglas-de-negocio.pdf` — fórmulas RN-01 a RN-31 con ejemplos numéricos.
  Los ejemplos son la especificación: si el código da otro resultado, el código está mal.
- `docs/requisitos.pdf` — requisitos RF-01 a RF-64 y RNF-01 a RNF-14.
- `docs/modelo-de-datos.pdf` — las 23 tablas y sus relaciones.

## Convenciones
- Nombres de tablas, campos y variables de dominio en español.
- Docstrings citando el requisito o regla que implementan: `# RN-05`, `# RF-34`.
- Type hints en todas las funciones públicas.
```

---

# FASE 0 — Cimientos
**Semana 1** · En paralelo al diseño de pantallas

> Es la fase que más rinde. Un error en el módulo de dinero se propaga a todo
> el sistema y se descubre tarde. No avances hasta que los tests pasen.

```
Estoy construyendo un sistema de gestión para un minimarket en Venezuela.
Leé CLAUDE.md y docs/reglas-de-negocio.pdf antes de escribir código.

Necesito los cimientos del proyecto. Nada de interfaz gráfica todavía.

1. Estructura de carpetas según CLAUDE.md, con __init__.py y pyproject.toml
   (dependencias: PySide6, python-escpos, reportlab, pytest, requests).

2. Módulo dominio/dinero.py con:
   - Constantes de escala para cada magnitud (precio, total, cantidad, tasa, porcentaje)
   - Función redondear(valor: Decimal, decimales: int) -> Decimal que SIEMPRE
     usa ROUND_HALF_UP. Es la única función del sistema autorizada a redondear.
   - Funciones a_entero(valor, escala) y desde_entero(entero, escala) para
     convertir entre Decimal y el entero escalado que guarda SQLite.
   - Función convertir_a_bs(monto_usd, tasa) según RN-03.
   - Todas con type hints y tests.

3. Módulo dominio/impuestos.py con las fórmulas de RN-05 (desglose de un precio
   con IVA incluido), RN-08 (margen sobre costo) y RN-09 (precio desde margen).
   Prestá atención al orden de las operaciones y al momento del redondeo.

4. datos/esquema.sql: el esquema completo de las 23 tablas de
   docs/modelo-de-datos.pdf, adaptado a SQLite con enteros escalados.
   Incluí índices, CHECK constraints y los datos iniciales (alícuotas,
   motivos de pérdida, configuración).

5. datos/conexion.py: apertura de la base con WAL activado
   (PRAGMA journal_mode=WAL, PRAGMA foreign_keys=ON), creación del esquema si
   no existe, y un context manager para transacciones.

6. tests/test_dinero.py y tests/test_impuestos.py que verifiquen EXACTAMENTE
   los tres ejemplos trabajados de docs/reglas-de-negocio.pdf:
   - Ejemplo A: harina exenta, bulto de 20 a $12, margen 30%, tasa 210,500000
   - Ejemplo B: refresco gravado 16%, caja de 24 a $12,60, margen 35%
   - Ejemplo C: venta mixta con exento y gravado, pago de $5, vuelto en Bs
   Incluí también un test que verifique que el desglose inverso del ejemplo B
   devuelve la base imponible original.

Terminá corriendo pytest y mostrame que pasa todo.
```

---

# FASE 1 — Catálogo y tasa del día
**Semanas 2 y 3** · RF-01 a RF-13

```
Continuamos con el sistema del minimarket. Fase 1: catálogo y tasa de cambio.
Leé CLAUDE.md. La Fase 0 ya está hecha y sus tests pasan.

Implementá los requisitos RF-01 a RF-13 de docs/requisitos.pdf:

1. datos/repositorios/: repositorios para categoria, alicuota_iva, producto y
   tasa_cambio. SQL a mano. Toda conversión de entero escalado a Decimal ocurre
   acá y en ningún otro lado.

2. dominio/producto.py: la entidad y su lógica de precios, apoyándose en
   dominio/impuestos.py de la Fase 0. Incluí la resolución del margen aplicable
   (el del producto si existe, si no el de su categoría).

3. servicios/catalogo.py: casos de uso de alta, modificación y baja lógica de
   productos, y el recálculo en bloque de precios de una categoría (RF-08).

4. servicios/tasa.py: registro de tasa manual y automática. La consulta al BCV
   va en infra/bcv.py con timeout corto; si falla no debe bloquear nada, solo
   devolver None y registrar el intento. Una sola tasa por fecha (RN-02).

5. ui/: ventana principal con navegación por teclado, pantalla de productos con
   tabla y búsqueda, formulario de alta y edición, pantalla de categorías y
   diálogo de carga de tasa. Interfaz en español.

6. La búsqueda de productos debe cumplir RNF-03: menos de un segundo sobre 3.000
   productos. Generá un script tests/datos_prueba.py que cargue 3.000 productos
   ficticios y un test que mida el tiempo de búsqueda.

7. Tests de los servicios y repositorios sobre una base temporal.

Importante: el precio que se guarda en producto.precio_venta_usd YA INCLUYE IVA.
No lo confundas con la base imponible.
```

---

# FASE 2 — Compras, costos e inventario
**Semana 4** · RF-14 a RF-27

```
Fase 2 del sistema del minimarket: compras e inventario.
Leé CLAUDE.md. Las fases 0 y 1 están terminadas.

Implementá RF-14 a RF-27 de docs/requisitos.pdf y las reglas RN-06, RN-07,
RN-11 a RN-18 de docs/reglas-de-negocio.pdf.

1. Repositorios de proveedor, compra, compra_detalle, pago_proveedor, lote y
   movimiento_inventario.

2. dominio/inventario.py: el kardex. La existencia de un producto es la SUMA de
   sus movimientos, nunca un campo. Implementá también la selección de lote por
   vencimiento más próximo (RN-15) y el cálculo del último costo (RN-07).

3. servicios/compras.py: registrar una compra completa dentro de UNA sola
   transacción — encabezado, líneas, lotes si corresponde, y los movimientos de
   entrada de inventario. Si algo falla, no debe quedar nada a medias (RNF-06).
   Al confirmar, devolvé la lista de productos cuyo precio de venta quedó por
   debajo del margen objetivo con el nuevo costo.

4. La conversión de presentación a unidad (RN-06) se captura POR LÍNEA de compra,
   no en la ficha del producto. Un mismo producto puede venir en bulto de 20 en
   una compra y de 24 en la siguiente.

5. servicios/inventario.py: consulta de existencias, alertas de mínimo (RF-24) y
   ajuste por conteo físico (RF-25), este último restringido a administrador.

6. Anulación de compras con movimientos inversos (RF-20). Nada se borra.

7. ui/: pantalla de compras con detalle editable, pantalla de proveedores,
   consulta de existencias con filtro de bajo stock, y diálogo de ajuste.

8. Tests: que la existencia calculada coincida con la suma de movimientos después
   de una secuencia de compras, ventas simuladas, ajustes y anulaciones.
   Incluí un test de rollback: una compra que falla a mitad no deja movimientos.
```

---

# FASE 3 — Ventas y caja
**Semanas 5 y 6** · RF-34 a RF-45

> El corazón del sistema y el hito del segundo pago del contrato.

```
Fase 3 del sistema del minimarket: punto de venta y caja.
Leé CLAUDE.md. Las fases 0 a 2 están terminadas.

Implementá RF-34 a RF-45 y las reglas RN-19 a RN-26.

1. Repositorios de caja_sesion, cliente, venta, venta_detalle y venta_pago.

2. dominio/venta.py: cálculo de totales según RN-20. Cada línea calcula su total,
   se redondea a dos decimales, y recién después se suman. NO recalcules el IVA
   sobre el total del documento: conviven productos exentos y gravados.
   Separá exento, base imponible e IVA (RN-21).

3. CRÍTICO (RN-19): cada línea de venta guarda copia del costo unitario vigente
   al momento de la venta, además del precio y la alícuota. Escribí un test que
   verifique que cambiar el costo de un producto después de una venta NO altera
   la ganancia calculada de esa venta.

4. servicios/venta.py: registrar la venta completa en UNA transacción —
   encabezado, líneas, pagos y movimientos de salida de inventario.
   Pago mixto según RN-22 y vuelto según RN-23. Solo los medios en efectivo
   generan vuelto; un excedente por punto de venta o transferencia se rechaza.

5. servicios/caja.py: apertura y cierre. Una sola sesión abierta a la vez.
   El cierre calcula el esperado por medio de pago y la diferencia (RN-26).
   Sin sesión abierta no se puede vender (RF-44).

6. ui/venta.py: la pantalla más importante del sistema. Debe ser operable
   ÍNTEGRAMENTE por teclado (RNF-08). El campo de código de barras mantiene el
   foco permanente; el lector se comporta como teclado y termina con Enter.
   Mostrá total en USD y en Bs simultáneamente. F-teclas para las acciones
   frecuentes. El registro de una línea debe tardar menos de 300 ms (RNF-02).

7. infra/impresora.py: nota de entrega por ESC/POS con datos fiscales del
   negocio, datos del cliente si los hay, detalle y desglose de exento, base
   imponible e IVA (RF-39). Diseñá la estructura del comprobante pensando en que
   más adelante se conectará una máquina fiscal.
   Si la impresora no responde, la venta ya está registrada: mostrá un aviso y
   ofrecé reimprimir, nunca pierdas la venta.

8. Anulación con clave de administrador y motivo obligatorio (RN-25).

9. Tests del ejemplo C de las reglas de negocio, de la secuencia completa
   apertura → varias ventas → cierre, y de que una venta interrumpida no deja
   inventario descontado.
```

---

# FASE 4 — Usuarios, reportes y respaldo
**Semana 7** · RF-48 a RF-64

```
Fase 4 del sistema del minimarket: seguridad, reportes y respaldo.
Leé CLAUDE.md. Las fases 0 a 3 están terminadas.

Implementá RF-48 a RF-52, RF-56 a RF-64 y la tabla de permisos de la sección 6
de docs/reglas-de-negocio.pdf.

1. servicios/usuarios.py: autenticación con hash y sal (usá hashlib.scrypt o
   bcrypt, nunca hash simple). Dos perfiles: ADMIN y CAJERO.

2. Control de permisos aplicado en la capa de SERVICIOS, no solo ocultando
   botones en la interfaz. Un cajero no debe poder acceder a costos ni márgenes
   aunque llegue a la pantalla por otro camino (RF-58).

3. infra/auditoria.py: bitácora de anulaciones, ajustes, cambios de precio y
   modificaciones de usuarios (RF-59).

4. servicios/reportes.py: ventas por período con totales por medio de pago,
   inventario valorizado, ganancia por producto y por categoría, y cierre de caja.
   La ganancia usa el costo CONGELADO en la línea de venta (RN-27, RN-28).

5. Libro de ventas (RF-52): agrupado por fecha, con exento, base imponible, IVA y
   total, expresado en bolívares a la tasa de CADA operación, no a la tasa de hoy
   (RN-31). Las ventas anuladas aparecen con importes en cero e indicación de su
   condición. Dejá la estructura de columnas fácil de ajustar: el formato final
   lo confirma el contador del cliente.

6. Exportación de reportes a PDF con reportlab, con encabezado del negocio.

7. infra/respaldo.py: respaldo diario automático usando conexion.backup(destino),
   NUNCA copia de archivo. Registro de cada intento en la tabla respaldo, aviso al
   administrador si la unidad no está disponible (RF-62), y restauración desde la
   aplicación (RF-63).

8. ui/: login, gestión de usuarios, pantalla de configuración y menú de reportes
   con selección de rango de fechas y vista previa.

9. Tests: que un cajero no pueda invocar servicios restringidos, que el respaldo
   genere un archivo restaurable, y que el libro de ventas cuadre con la suma de
   las ventas del período.
```

---

# FASE 5 — Pérdidas, vencimientos y resultados
**Semanas 8 a 10** · RF-28 a RF-33, RF-46, RF-47, RF-53 a RF-55

```
Fase 5 del sistema del minimarket: pérdidas, vencimientos y ganancia real.
Leé CLAUDE.md. Las fases 0 a 4 están terminadas.

Implementá RF-28 a RF-33, RF-46, RF-47, RF-53 a RF-55, y las reglas RN-18,
RN-29 y RN-30.

1. servicios/perdidas.py: registro de pérdidas con motivo, valorizadas al último
   costo vigente en la fecha de la pérdida (RN-18). Genera el movimiento de
   inventario correspondiente en la misma transacción.

2. Vencimientos: alerta de lotes próximos a vencer según los días configurados
   por producto (RF-31), y baja directa de un lote vencido como pérdida (RF-32).
   Un lote vencido con existencia NO bloquea la venta: solo aparece en la alerta.

3. servicios/gastos.py: carga de gastos operativos por período mensual (RF-46).

4. Reporte de ganancia real (RF-47, RN-29):
   ganancia_real = (base_imponible + exento) − CMV − pérdidas − gastos
   Los gastos NO se prorratean entre productos. Se restan del resultado global
   del período.

5. Reportes de pérdidas por motivo y de productos próximos a vencer.

6. ui/: pantalla de registro de pérdidas, panel de alertas de vencimiento,
   pantalla de gastos operativos y reporte de ganancia real del período.

7. Panel de inicio para el administrador que reúna las alertas: productos bajo
   mínimo, lotes por vencer y si el respaldo de ayer se ejecutó bien.

8. Tests: que una pérdida reduzca la existencia y el margen del período, y que la
   ganancia real coincida con el cálculo manual sobre un conjunto de datos
   conocido.
```

---

# FASE 6 — Empaquetado y puesta en marcha
**Semana 11** · RNF-11, RNF-12, RNF-13

```
Fase 6 final del sistema del minimarket: empaquetado e instalación.
Leé CLAUDE.md. Las fases 0 a 5 están terminadas.

1. Revisión completa: corré pytest y arreglá lo que falle. Verificá que se
   cumplen RNF-02, RNF-03 y RNF-04 (tiempos de respuesta) con los 3.000
   productos de prueba.

2. infra/bitacora.py: logging a archivo con rotación, para diagnóstico remoto
   (RNF-13). Que capture excepciones no controladas sin cerrar la aplicación.

3. Revisá TODOS los mensajes de error visibles: deben decir qué hacer, en
   español, sin trazas técnicas (RNF-09).

4. Empaquetado con PyInstaller en modo onedir. Verificá que se incluyan los
   recursos: esquema.sql, íconos, fuentes de reportlab.

5. Instalador con Inno Setup: acceso directo, desinstalador, creación de la
   carpeta de datos en una ruta escribible por el usuario (NO dentro de Program
   Files, la base de datos tiene que poder escribirse).

6. Asistente de primer arranque: datos fiscales del negocio, logotipo, creación
   del usuario administrador, ruta de respaldo y carga de la primera tasa.

7. Herramienta de carga inicial del catálogo desde CSV o Excel, con validación y
   reporte de errores por fila. El cliente va a cargar más de mil productos y no
   lo va a hacer uno por uno.

8. README de instalación y un manual de usuario breve en Markdown, con capturas,
   cubriendo: venta, cierre de caja, registrar compra, cargar tasa, registrar
   pérdida y consultar reportes.

9. Script de datos de demostración para la capacitación, separado de la base real.
```

---

## Recomendaciones de uso

**Una fase por sesión.** Claude Code trabaja mejor con objetivos acotados. Si la fase es larga, dividila en dos sesiones pero no mezcles fases.

**Revisá el código de la Fase 0 línea por línea.** Es la única que vale la pena auditar en detalle: todo lo demás se apoya en ella. En las siguientes, revisá los servicios y confiá más en la interfaz.

**Commit al terminar cada fase**, con el número de fase en el mensaje. Si algo se rompe tres semanas después, vas a querer poder volver.

**Las demos del contrato** caen naturalmente al final de las fases 1, 3 y 5. La demo del hito de pago es al terminar la Fase 3.

**Si Claude Code propone usar float, un ORM o PyQt**, cortalo y recordale el CLAUDE.md. Son los tres desvíos más probables.
