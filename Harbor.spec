# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('harbor.html', '.'), ('libs', 'libs'), ('VERSION', '.'),
           # W0 R19：版本化提示词目录（prompt_loader 经 ../prompts 定位，frozen 同口径）
           ('backend/prompts', 'backend/prompts')],
    # 修复 W2：懒加载依赖显式声明（原 frozen 包中 send2trash/PIL 静默缺失，
    # delete_path 回收站模式与 take_screenshot 在打包版失效）
    hiddenimports=['send2trash', 'PIL.ImageGrab'],
    # 复核修正：pywin32 在 Py3.15 构建环境不可加载（pywin32-312 只带 313 DLL，
    # send2trash 的 COM 路径把 pythoncom 拉入图触发 hook-pythoncom 崩溃）——
    # 排除 pywin32 族，运行时 send2trash 自动回落 ctypes legacy 路径
    # （SHFileOperation，回收站功能不受影响）
    excludes=['pythoncom', 'pywintypes', 'win32api', 'win32com',
              'win32com.client', 'win32timezone', 'win32con',
              'win32gui', 'win32process', 'win32event'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
    name='Harbor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['harbor.ico'],
)
