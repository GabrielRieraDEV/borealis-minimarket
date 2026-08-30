"""Casos de uso. La interfaz entra por aca y nunca toca `datos/`."""

# El usuario semilla que crea esquema.sql. `movimiento_inventario.usuario_id` y
# `compra.usuario_id` son NOT NULL y la autenticacion recien llega en la Fase 4:
# hasta entonces las operaciones se atribuyen a `admin`. Cuando haya sesion
# real, este valor sale de ella y esta constante desaparece.
USUARIO_ACTUAL = 1
