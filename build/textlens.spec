# PyInstaller spec file for TextLens
# Usage: pyinstaller textlens.spec --clean --noconfirm
# Output: dist/TextLens/TextLens.exe

# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['../main.py'],
    pathex=['..'],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Explicitly include modules PyInstaller may miss
        'latex2mathml.converter',
        # mss screen-capture library + platform-specific backends
        'mss',
        'mss.tools',
        'mss.windows',
        'mss.linux',
        'mss.darwin',
        # matplotlib backend + mathtext (for LaTeX preview)
        'matplotlib',
        'matplotlib.figure',
        'matplotlib.backends.backend_agg',
        'matplotlib.mathtext',
        'matplotlib._mathtext',
        'matplotlib.font_manager',
        'pyparsing',
        # PIL plugins used by matplotlib for image I/O
        'PIL.PngImagePlugin',
        'PIL.BmpImagePlugin',
        'PIL.JpegImagePlugin',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim unused Qt modules to reduce size
        'PySide6.Qt3D',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtMultimedia',
        'PySide6.QtNetworkAuth',
        'PySide6.QtQuick3D',
        'PySide6.QtRemoteObjects',
        'PySide6.QtScxml',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtTest',
        'PySide6.QtTextToSpeech',
        'PySide6.QtWebChannel',
        'PySide6.QtWebEngine',
        'PySide6.QtWebSockets',
        'PySide6.QtXml',
        'tkinter',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TextLens',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # GUI app, no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='textlens.ico',  # Uncomment if you add an icon file
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TextLens',
)
