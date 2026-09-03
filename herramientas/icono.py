"""Genera el icono de la aplicacion a partir del logotipo.

    python -m herramientas.icono

Lee `recursos/logo.png`, recorta al contenido (el logo viene centrado en un
lienzo apaisado con aire a los lados), lo cuadra y escribe
`recursos/minimarket.ico` con los tamanos que Windows usa. El `.ico` se
regenera cuando cambie el logo; a mano no se toca.

Pillow ya esta instalado porque reportlab lo usa; no es una dependencia nueva.
"""

from pathlib import Path

from PIL import Image

RECURSOS = Path("recursos")
LOGO = RECURSOS / "logo.png"
ICONO = RECURSOS / "minimarket.ico"
TAMANOS = [16, 24, 32, 48, 64, 128, 256]


def main() -> None:
    imagen = Image.open(LOGO).convert("RGBA")
    imagen = imagen.crop(imagen.getchannel("A").getbbox())
    lado = max(imagen.size)
    cuadrado = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    cuadrado.paste(
        imagen, ((lado - imagen.width) // 2, (lado - imagen.height) // 2)
    )
    cuadrado.save(ICONO, sizes=[(t, t) for t in TAMANOS])
    print(f"{ICONO} ({lado}x{lado} de origen, {len(TAMANOS)} tamanos)")


if __name__ == "__main__":
    main()
