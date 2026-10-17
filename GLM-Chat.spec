# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('glm-chat.html', '.'), ('libs', 'libs'), ('VERSION', '.')],
    # 修复 W2：懒加载依赖显式声明（原 frozen 包中 send2trash/PIL 静默缺失，
    # delete_path 回收站模式与 take_screenshot 在打包版失效）
    hiddenimports=['send2trash', 'PIL.ImageGrab'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='GLM-Chat',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['glm-chat.ico'],
)
