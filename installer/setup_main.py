# -*- coding: utf-8 -*-
"""Harbor 安装器入口（setup_main.py）。

文件名刻意避开 main.py——frozen 后 traceback 的 co_filename 是基名，
若叫 main.py 会与仓库根的应用 main.py 在 linecache 里撞车（调试事故源）。

用法：
  Harbor-Setup-x.y.z.exe            双击 → 图形化安装向导（pywebview）
  Harbor-Setup-x.y.z.exe /S          静默安装（默认目录或 --dir 指定）
  Harbor-Setup-x.y.z.exe --dir PATH  指定目录（配合 /S 或 GUI 预填）
  Harbor-Setup-x.y.z.exe --version   输出版本号
  Uninstall.exe                      卸载确认（原生 MessageBox 两问）
  Uninstall.exe /S [--purge]         静默卸载（默认保留用户数据）

GUI 技术栈：复用产品自身的 pywebview + 单文件 HTML（本机构建环境无 tkinter，
2026-10-19 实测决策）；WebView2 缺失时降级原生 MessageBox 指引 + 静默安装提示。
"""
import os
import sys

from installer_core import (app_version, default_install_dir, install,
                            read_install_manifest, registry_install_location,
                            uninstall)

SILENT = any(a in ('/S', '/s', '--silent', '-S') for a in sys.argv[1:])
UNINSTALL = any(a in ('/uninstall', '--uninstall', '-u') for a in sys.argv[1:])
PURGE = '--purge' in sys.argv[1:]


def _dir_arg(default=None):
    for i, a in enumerate(sys.argv[1:]):
        if a.startswith('--dir=') or a.startswith('/D='):
            v = a.split('=', 1)[1].strip().strip('"')
            return v or default
        if a in ('--dir', '/D') and i + 2 < len(sys.argv):
            v = sys.argv[i + 2].strip().strip('"')
            return v or default
    return default


def _resolve_uninstall_dir():
    """卸载目标定位链（按优先级）：

    1. `--dir` / `/D=` 显式参数（空值已由 _dir_arg 回落，不会命中）；
    2. frozen 时 Uninstall.exe 所在目录（需含 Harbor.exe 校验防误判）——
       其中 install.json 的 install_dir 字段优先于注册表读取（安装后
       目录被移动过时以清单为准，读不到再退回 exe 所在目录本身）；
    3. 注册表 HKCU Uninstall\\Harbor 的 InstallLocation；
    4. 默认每用户目录。

    取代原先两处硬编码 default_install_dir()——用户改过安装位置时
    卸载会打偏（删默认目录、留真实目录）。"""
    arg = _dir_arg(None)
    if arg:
        return arg
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if os.path.exists(os.path.join(exe_dir, 'Harbor.exe')):
            manifest = read_install_manifest(exe_dir)
            if manifest and manifest.get('install_dir'):
                return manifest['install_dir']
            return exe_dir
    reg = registry_install_location()
    if reg:
        return reg
    return default_install_dir()


def _log(msg):
    try:
        with open(os.path.join(os.environ.get('TEMP', '.'), 'harbor-setup.log'), 'a',
                  encoding='utf-8') as f:
            f.write(msg + '\n')
    except OSError:
        pass


def run_silent_install():
    target = _dir_arg(default_install_dir())
    _log('[install] target=%s' % target)
    res = install(target, progress_cb=lambda i, t, m: _log('[install] %d/%d %s' % (i, t, m)))
    _log('[install] result=%s' % {k: v for k, v in res.items() if k != 'warnings'})
    return 0 if res.get('ok') else 2


def run_silent_uninstall():
    install_dir = _resolve_uninstall_dir()
    _log('[uninstall] dir=%s purge=%s' % (install_dir, PURGE))
    res = uninstall(install_dir, purge_data=PURGE,
                    progress_cb=lambda i, t, m: _log('[uninstall] %d/%d %s' % (i, t, m)))
    _log('[uninstall] result=%s' % res)
    return 0 if res.get('ok') else 3


# ---------------- 原生 MessageBox（cmd_service 同款显式签名，防 64 位截断） ----------------
def _msgbox(text, title, flags):
    import ctypes
    if not hasattr(ctypes, 'windll'):
        return 0
    try:
        from ctypes import wintypes
        u32 = ctypes.windll.user32
        u32.MessageBoxW.restype = ctypes.c_int
        u32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR,
                                    wintypes.LPCWSTR, wintypes.UINT]
        return u32.MessageBoxW(0, text, title, flags)
    except Exception:
        return 0


_MB_YESNO = 0x04
_MB_YES = 6
_MB_ICONWARN = 0x30
_MB_ICONINFO = 0x40
_MB_ICONERR = 0x10


def _uninstall_gui_native():
    """卸载确认：原生两问（是否卸载 / 是否连用户数据一起删）——安装器行业标准形态。"""
    r = _msgbox('卸载 Harbor %s？\n\n将删除程序文件、快捷方式与系统注册信息。\n'
                '用户数据（配置/会话/密钥）默认保留在 ~/.glm-chat。' % app_version(),
                'Harbor 卸载程序', _MB_YESNO | _MB_ICONWARN)
    if r != _MB_YES:
        return 0
    r2 = _msgbox('同时删除用户数据吗？\n\n选「是」将删除 ~/.glm-chat'
                 '（含 API Key 与会话记录，不可恢复）。\n选「否」仅卸载程序。',
                 'Harbor 卸载程序 · 用户数据', _MB_YESNO | _MB_ICONWARN)
    purge = (r2 == _MB_YES)
    res = uninstall(_resolve_uninstall_dir(), purge_data=purge)
    if res.get('ok'):
        _msgbox('卸载完成。' + ('用户数据已删除。' if purge else '用户数据保留在 ~/.glm-chat。'),
                'Harbor 卸载程序', _MB_ICONINFO)
        return 0
    _msgbox('卸载失败：%s' % res.get('error', '未知错误'), 'Harbor 卸载程序', _MB_ICONERR)
    return 3


def _gui_fallback():
    """pywebview/WebView2 不可用：原生指引 + 静默安装提示（不假装能装）。"""
    _msgbox('无法启动图形安装界面（WebView2 运行时缺失或损坏）。\n\n'
            'Harbor 需要 Edge WebView2 Runtime（Windows 11 自带；Windows 10 请先在微软官网'
            '安装「Edge WebView2 Runtime」）。\n\n'
            '安装完成后，也可以静默方式安装：\nHarbor-Setup.exe /S',
            'Harbor 安装程序', _MB_ICONWARN)
    return 4


def main():
    if '--version' in sys.argv[1:] or '/V' in sys.argv:
        print(app_version())
        return 0
    if UNINSTALL:
        if SILENT:
            return run_silent_uninstall()
        return _uninstall_gui_native()
    if SILENT:
        return run_silent_install()
    # GUI：延迟 import——静默/卸载路径不加载 pywebview
    try:
        from installer_gui import run_gui
    except ImportError as e:
        _log('[gui] import 失败: %r' % e)
        return _gui_fallback()
    try:
        run_gui()
    except Exception as e:
        _log('[gui] 启动失败: %r' % e)
        return _gui_fallback()
    return 0


if __name__ == '__main__':
    sys.exit(main())
