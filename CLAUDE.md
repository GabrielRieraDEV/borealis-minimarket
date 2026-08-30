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

Fase actual: **Fase 2 — Compras, costos e inventario** (sin empezar).

Fase 0 terminada: `dominio/dinero.py`, `dominio/impuestos.py`,
`datos/esquema.sql` (23 tablas + 2 vistas), `datos/conexion.py` y 80 pruebas
que verifican los ejemplos A, B y C.

Fase 1 terminada: `datos/repositorios/` (categoria, alicuota, producto, tasa,
configuracion), `dominio/producto.py`, `dominio/tasa.py`, `servicios/catalogo.py`,
`servicios/tasa.py`, `infra/bcv.py` y la interfaz (`ui/principal.py`,
`ui/productos.py`, `ui/categorias.py`, `ui/tasa.py`, `ui/comunes.py`).
116 pruebas. La app arranca con `python -m minimarket`.

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

Pendientes para fases posteriores:

- **RF-27** (bloquear venta sin existencia) figura en el rango de la Fase 2
  pero se hace cumplir en `servicios/venta.py`, Fase 3.
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
