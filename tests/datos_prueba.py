"""Catalogo ficticio para medir RNF-03 (busqueda sobre 3.000 productos).

Se puede correr suelto para dejar una base cargada a mano:
    python -m tests.datos_prueba ruta/a/prueba.db
"""

import random
import sqlite3
import sys
from decimal import Decimal

from minimarket.datos.conexion import abrir, transaccion
from minimarket.datos.repositorios import alicuota as repo_alicuota
from minimarket.datos.repositorios import categoria as repo_categoria
from minimarket.datos.repositorios import producto as repo_producto
from minimarket.dominio.producto import Categoria, Producto

CATEGORIAS = [
    ("Viveres", Decimal(30)),
    ("Charcuteria", Decimal(35)),
    ("Carniceria", Decimal(28)),
    ("Hortalizas", Decimal(40)),
    ("Bebidas", Decimal(35)),
    ("Limpieza", Decimal(45)),
    ("Quincalleria", Decimal(60)),
    ("Bisuteria", Decimal(80)),
    ("Electronicos", Decimal(25)),
    ("Tabaco", Decimal(20)),
]

_SUSTANTIVOS = [
    "Harina", "Arroz", "Pasta", "Aceite", "Azucar", "Cafe", "Leche", "Jabon",
    "Refresco", "Queso", "Jamon", "Papel", "Detergente", "Pila", "Cargador",
    "Arete", "Cigarrillo", "Salsa", "Atun", "Galleta",
]
_MODIFICADORES = [
    "premium", "clasico", "familiar", "economico", "importado", "nacional",
    "extra", "light", "grande", "pequeno",
]


def crear_categorias(conexion: sqlite3.Connection) -> list[int]:
    with transaccion(conexion):
        return [
            repo_categoria.crear(conexion, Categoria(None, nombre, margen))
            for nombre, margen in CATEGORIAS
        ]


def cargar(conexion: sqlite3.Connection, cantidad: int = 3000) -> list[int]:
    """Crea las categorias y `cantidad` productos con nombre y codigo unicos."""
    azar = random.Random(20260829)  # semilla fija: la medicion es comparable
    categorias = crear_categorias(conexion)
    alicuotas = [a.id for a in repo_alicuota.listar(conexion)]
    with transaccion(conexion):
        return [
            repo_producto.crear(
                conexion,
                Producto(
                    nombre=(
                        f"{azar.choice(_SUSTANTIVOS)} "
                        f"{azar.choice(_MODIFICADORES)} {numero:04d}"
                    ),
                    codigo_barras=f"77{numero:011d}",
                    categoria_id=azar.choice(categorias),
                    alicuota_iva_id=azar.choice(alicuotas),
                    precio_venta_usd=Decimal(azar.randint(500, 500_000)) / 10_000,
                    existencia_minima=Decimal(azar.randint(0, 20)),
                ),
            )
            for numero in range(cantidad)
        ]


if __name__ == "__main__":
    destino = sys.argv[1] if len(sys.argv) > 1 else "prueba.db"
    conexion = abrir(destino)
    print(f"{len(cargar(conexion))} productos cargados en {destino}")
