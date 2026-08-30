# Sistema de gestión para minimarket

Aplicación de escritorio (Python 3.12 + PySide6 + SQLite) para un minimarket en
Venezuela: catálogo, tasa de cambio, compras, inventario por movimientos, punto
de venta, caja, pérdidas y reportes.

Borealis Software Solutions · Opción C.

## Puesta en marcha para desarrollo

```
python -m venv .venv
.venv\Scripts\activate
pip install pytest
pytest
```

`pip install -e ".[dev]"` recién hace falta cuando entre PySide6, en la Fase 1.

## Estructura

```
minimarket/dominio/     cálculos puros (dinero, IVA, márgenes, inventario, venta)
minimarket/datos/       esquema SQLite y repositorios con SQL a mano
minimarket/servicios/   casos de uso transaccionales
minimarket/ui/          ventanas PySide6
minimarket/infra/       impresora, tasa BCV, respaldo, bitácora, configuración
tests/                  pruebas pytest
docs/                   requisitos, reglas de negocio, modelo de datos, plan de fases
```

`CLAUDE.md` en la raíz tiene las reglas de implementación innegociables y las
erratas detectadas en la documentación. Leerlo antes de tocar código.

## Estado

Fase 0 terminada. Siguiente: Fase 1.

| Fase | Alcance | Requisitos |
|------|---------|-----------|
| 0 ✅ | Cimientos: dinero, impuestos, esquema, conexión | RN-03, RN-05, RN-08, RN-09 |
| 1 | Catálogo y tasa del día | RF-01 a RF-13 |
| 2 | Compras, costos e inventario | RF-14 a RF-27 |
| 3 | Ventas y caja | RF-34 a RF-45 |
| 4 | Usuarios, reportes y respaldo | RF-48 a RF-64 |
| 5 | Pérdidas, vencimientos y resultados | RF-28 a RF-33, RF-46, RF-47, RF-53 a RF-55 |
| 6 | Empaquetado y puesta en marcha | RNF-11 a RNF-13 |

El detalle de cada fase está en `docs/plan-de-fases-claude-code.md`.
