# Sistema de gestión para minimarket

Aplicación de escritorio (Python 3.12 + PySide6 + SQLite) para un minimarket en
Venezuela: catálogo, tasa de cambio, compras, inventario por movimientos, punto
de venta, caja, pérdidas y reportes.

Borealis Software Solutions · Opción C.

El manual del usuario final está en
[`docs/manual-de-usuario.md`](docs/manual-de-usuario.md).

## Instalación en el equipo del cliente

1. Ejecutar `minimarket-instalador.exe` y aceptar la ruta que propone. Pide
   permisos de administrador una sola vez, para escribir en Archivos de
   programa; después la aplicación corre como usuario común.
2. Abrir **Minimarket** desde el escritorio o el menú de inicio.
3. En el primer arranque aparece el **asistente de puesta en marcha**: clave del
   administrador, datos fiscales, logotipo, carpeta de respaldo y tasa del día.
   Lo único obligatorio es la clave; el resto se completa después en
   Archivo → Configuración.
4. Cargar el catálogo. Para más de unas decenas de productos conviene el
   importador: Archivo → *Guardar plantilla de catálogo…*, completarla en Excel
   y Archivo → *Importar catálogo desde CSV…*.

No hay servicios que configurar ni base de datos que instalar aparte (RNF-11).

### Dónde queda cada cosa

| | Ruta |
|--|------|
| Programa | `C:\Archivos de programa\Minimarket` |
| Base de datos | `%USERPROFILE%\Minimarket\minimarket.db` |
| Bitácora de errores | `%USERPROFILE%\Minimarket\minimarket.log` |
| Respaldos | la carpeta configurada, normalmente una unidad externa |

La base **no** vive dentro de Archivos de programa: ahí el usuario no tiene
permiso de escritura. Desinstalar el programa no borra la base ni los
respaldos. La variable de entorno `MINIMARKET_DB` cambia de lugar el archivo,
que es como se trabaja sobre la base de demostración sin tocar la real.

Si hay que reportar un problema, el archivo a mandar es `minimarket.log`.

### Volver a cero

El instalador no lleva datos: en un equipo nuevo el sistema arranca vacío,
con el asistente de puesta en marcha. Para dejar en cero un equipo donde ya
se probó —el del desarrollador antes de entregar, o el del cliente después de
la capacitación— se cierra el programa y se borra el contenido de
`%USERPROFILE%\Minimarket` (`minimarket.db`, `minimarket.log` y los
`.db-wal` / `.db-shm` si están). Al abrir de nuevo vuelve el asistente.
`demostracion.db` es aparte y no molesta; se borra o no, según se quiera
seguir capacitando.

## Desarrollo

```
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
python -m minimarket
```

### Base de demostración para capacitar

```
python -m herramientas.demostracion
set MINIMARKET_DB=%USERPROFILE%\Minimarket\demostracion.db
python -m minimarket
```

Deja un minimarket andando: catálogo, existencia con lotes por vencer, la caja
del día abierta, ventas hechas, una pérdida y un gasto. Usuarios `admin` /
`demo1234` y `maria` / `caja1234`. Se puede rehacer las veces que haga falta.

Las capturas del manual se regeneran con `python -m herramientas.capturas`
sobre esa misma base.

### Empaquetado

```
pyinstaller minimarket.spec --noconfirm
ISCC.exe instalador\minimarket.iss
```

El primer comando deja `dist\Minimarket\` (modo onedir) y el segundo
`instalador\salida\minimarket-instalador.exe`. Inno Setup 6.3 o superior.

El icono sale de `recursos/logo.png`; si cambia el logotipo,
`python -m herramientas.icono` regenera `recursos/minimarket.ico` antes de
empaquetar.

## Estructura

```
minimarket/dominio/     cálculos puros (dinero, IVA, márgenes, inventario, venta)
minimarket/datos/       esquema SQLite y repositorios con SQL a mano
minimarket/servicios/   casos de uso transaccionales
minimarket/ui/          ventanas PySide6
minimarket/infra/       impresora, tasa BCV, respaldo, bitácora, PDF, rutas
recursos/               logotipo del cliente e icono generado
herramientas/           base de demostración y capturas del manual
tests/                  pruebas pytest
docs/                   requisitos, reglas de negocio, modelo de datos, manual
instalador/             script de Inno Setup
```

`CLAUDE.md` en la raíz tiene las reglas de implementación innegociables y las
erratas detectadas en la documentación. Leerlo antes de tocar código.

## Estado

Las siete fases están terminadas.

| Fase | Alcance | Requisitos |
|------|---------|-----------|
| 0 ✅ | Cimientos: dinero, impuestos, esquema, conexión | RN-03, RN-05, RN-08, RN-09 |
| 1 ✅ | Catálogo y tasa del día | RF-01 a RF-13 |
| 2 ✅ | Compras, costos e inventario | RF-14 a RF-27 |
| 3 ✅ | Ventas y caja | RF-34 a RF-45 |
| 4 ✅ | Usuarios, reportes y respaldo | RF-48 a RF-64 |
| 5 ✅ | Pérdidas, vencimientos y resultados | RF-28 a RF-33, RF-46, RF-47, RF-53 a RF-55 |
| 6 ✅ | Empaquetado y puesta en marcha | RNF-11 a RNF-13 |

El detalle de cada fase está en `docs/plan-de-fases-claude-code.md`.
