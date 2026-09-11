# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['D:\\Main Work\\SnapCursorX All Data\\SnapCursorX - Dev Mode\\App\\Main.py'],
    pathex=['D:\\Main Work\\SnapCursorX All Data\\SnapCursorX - Dev Mode\\App'],
    binaries=[],
    datas=[('D:\\Main Work\\SnapCursorX All Data\\SnapCursorX - Dev Mode\\Assets', 'Assets'), ('D:\\Main Work\\SnapCursorX All Data\\SnapCursorX - Dev Mode\\Data', 'Data'), ('D:\\Main Work\\SnapCursorX All Data\\SnapCursorX - Dev Mode\\App\\Core\\ClickEngine.dll', 'App/Core'), ('D:\\Main Work\\SnapCursorX All Data\\SnapCursorX - Dev Mode\\App\\Core\\ClickEngine_input.dll', 'App/Core'), ('D:\\Main Work\\SnapCursorX All Data\\SnapCursorX - Dev Mode\\App\\Core\\ClickEngine_linear.dll', 'App/Core')],
    hiddenimports=['Core.build_info'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'numpy', 'matplotlib', 'pandas', 'scipy', 'tkinter', 'cv2', 'debugpy', 'PySide6.QtPdf', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtVirtualKeyboard'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SnapCursorX_SE',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='D:\\Main Work\\SnapCursorX All Data\\SnapCursorX - Dev Mode\\build\\version_info.txt',
    icon=['D:\\Main Work\\SnapCursorX All Data\\SnapCursorX - Dev Mode\\Assets\\app_icon.ico'],
    contents_directory='_internal',
    manifest='D:\\Main Work\\SnapCursorX All Data\\SnapCursorX - Dev Mode\\build\\manifest.xml',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SnapCursorX_SE',
)
