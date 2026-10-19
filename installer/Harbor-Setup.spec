# -*- mode: python ; coding: utf-8 -*-
"""Harbor 安装器打包规格（PyInstaller）。

同一 spec 两次构建，靠环境变量分流：
  HARBOR_BUILD=setup       → Harbor-Setup-x.y.z.exe（内嵌 payload/Harbor.exe 应用载荷）
  HARBOR_BUILD=uninstaller → Harbor-Uninstall.exe（无载荷，装进安装目录）

 datas 恒含 VERSION（安装器版本号单一数据源同源）。
"""
import os

_HERE = os.path.abspath(SPECPATH)   # SPECPATH 即 spec 所在目录（installer/）
_ROOT = os.path.dirname(_HERE)
_version = open(os.path.join(_ROOT, 'VERSION'), encoding='utf-8').read().strip()
_kind = os.environ.get('HARBOR_BUILD', 'setup')

_datas = [(os.path.join(_ROOT, 'VERSION'), '.')]
if _kind == 'setup':
    _payload = os.environ.get('HARBOR_PAYLOAD',
                              os.path.join(_ROOT, 'dist', 'Harbor.exe'))
    _datas.append((_payload, 'payload'))
    _datas.append((os.environ.get('HARBOR_UNINSTALLER',
                                  os.path.join(_ROOT, 'dist', 'Harbor-Uninstall.exe')),
                   'uninstall'))
    _exe_name = 'Harbor-Setup-%s' % _version
else:
    _exe_name = 'Harbor-Uninstall'

a = Analysis(
    [os.path.join(_HERE, 'setup_main.py')],
    pathex=[],
    binaries=[],
    datas=_datas,
    hiddenimports=['webview'],
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
    name=_exe_name,
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
    icon=[os.path.join(_ROOT, 'harbor.ico')],
)
