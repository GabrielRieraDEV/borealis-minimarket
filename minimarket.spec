# -*- mode: python ; coding: utf-8 -*-
"""Empaquetado con PyInstaller en modo onedir (punto 4 de la Fase 6).

    pyinstaller minimarket.spec --noconfirm

Queda `dist/Minimarket/Minimarket.exe`, que es lo que instala `instalador/
minimarket.iss`. Onedir y no onefile a proposito: onefile descomprime todo en
un temporal en cada arranque, y el equipo de la caja no tiene ese tiempo ni ese
disco para regalar.

Los tres recursos que no se detectan solos:

- `esquema.sql`, que es un dato y no un modulo. Sin el, la primera apertura de
  la base falla.
- `capabilities.json` de python-escpos, que la biblioteca lee en tiempo de
  ejecucion para saber que sabe hacer cada impresora.
- Las fuentes Type 1 de reportlab, que viven como datos del paquete.

No hay icono todavia: cuando el cliente mande el suyo, va como `recursos/
minimarket.ico` y se nombra en `icon=` aca y en el .iss.
"""

from PyInstaller.utils.hooks import collect_data_files

datos = [
    ("minimarket/datos/esquema.sql", "minimarket/datos"),
    *collect_data_files("escpos"),
    *collect_data_files("reportlab"),
]

analisis = Analysis(
    ["minimarket/__main__.py"],
    pathex=[],
    binaries=[],
    datas=datos,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    # PySide6 entero pesa cientos de megas; la aplicacion usa Widgets y nada
    # mas. Si alguna pantalla llegara a necesitar Qml o WebEngine, sacar el
    # modulo de esta lista es todo el cambio.
    excludes=[
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtMultimedia",
        "tkinter",
    ],
    noarchive=False,
)

pyz = PYZ(analisis.pure)

exe = EXE(
    pyz,
    analisis.scripts,
    [],
    exclude_binaries=True,
    name="Minimarket",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # es una aplicacion de ventana: sin consola detras
)

coleccion = COLLECT(
    exe,
    analisis.binaries,
    analisis.datas,
    strip=False,
    upx=False,
    name="Minimarket",
)
