"""Tasa de cambio del dia.

El calculo (RN-03) vive en `dominio/dinero.convertir_a_bs`. Aca solo la entidad
que viaja entre capas.
"""

from dataclasses import dataclass
from decimal import Decimal

BCV_AUTO = "BCV_AUTO"
MANUAL = "MANUAL"


@dataclass(frozen=True)
class TasaCambio:
    """RF-09. Una sola por fecha (RN-02), con su origen y quien la cargo."""

    fecha: str  # AAAA-MM-DD
    valor: Decimal
    origen: str  # BCV_AUTO | MANUAL
    usuario_id: int | None = None
    registrado_en: str | None = None
    id: int | None = None
