# -*- coding: utf-8 -*-
"""安装器一键构建（v1.7.0；2026-10-24 复核批补载荷 sha256 嵌入）。

用法：
  python installer/build_setup.py            # 全量：应用 exe → 卸载器 → 安装器
  python installer/build_setup.py --app-only # 仅构建应用 Harbor.exe（等价 Harbor.spec）

产物（dist/）：
  Harbor.exe                    应用本体（onefile）
  Harbor-Uninstall.exe          卸载器（小，安装时随包进安装目录）
  Harbor-Setup-<version>.exe    安装器（内嵌上面两个 + 载荷 sha256 清单，双击即向导）

每个构建步骤的 PyInstaller 参数均为内联字面量列表（无动态拼装）。
"""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLER_DIR = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, 'dist')
PY = sys.executable


def _check(r):
    if r.returncode != 0:
        print('命令失败：exit %d' % r.returncode)
        sys.exit(r.returncode)


def version():
    with open(os.path.join(ROOT, 'VERSION'), encoding='utf-8') as f:
        return f.read().strip()


def build_app():
    if not os.path.exists(os.path.join(ROOT, 'harbor.html')):
        print('未找到 harbor.html，请先 node frontend/build.js')
        sys.exit(1)
    print('+ PyInstaller Harbor.spec')
    r = subprocess.run([sys.executable, '-m', 'PyInstaller',
                        'Harbor.spec', '--noconfirm', '--clean'],
                       cwd=ROOT)
    _check(r)


def build_uninstaller():
    env = dict(os.environ, HARBOR_BUILD='uninstaller')
    print('+ PyInstaller installer/Harbor-Setup.spec (uninstaller)')
    r = subprocess.run([sys.executable, '-m', 'PyInstaller',
                        os.path.join('installer', 'Harbor-Setup.spec'),
                        '--noconfirm', '--clean',
                        '--distpath', DIST,
                        '--workpath', os.path.join(ROOT, 'build', 'uninstaller')],
                       cwd=ROOT, env=env)
    _check(r)


def build_setup():
    # 载荷完整性强校验：构建期把 Harbor.exe 的 sha256 写入清单文件并随 datas
    # 嵌入安装器（installer_core.install() 落地前对拍——同尺寸损坏载荷不再照装）
    payload = Path(DIST) / 'Harbor.exe'
    if not payload.is_file():
        print('异常：找不到应用载荷 %s' % payload)
        sys.exit(1)
    _h = hashlib.sha256()
    with open(payload, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            _h.update(chunk)
    sha_file = Path(ROOT) / 'build' / 'setup_payload.sha256'
    sha_file.parent.mkdir(parents=True, exist_ok=True)
    sha_file.write_text(_h.hexdigest(), encoding='utf-8')
    env = dict(os.environ, HARBOR_BUILD='setup',
               HARBOR_PAYLOAD=str(payload),
               HARBOR_UNINSTALLER=os.path.join(DIST, 'Harbor-Uninstall.exe'),
               HARBOR_PAYLOAD_SHA256_FILE=str(sha_file))
    print('+ PyInstaller installer/Harbor-Setup.spec (setup)')
    r = subprocess.run([sys.executable, '-m', 'PyInstaller',
                        os.path.join('installer', 'Harbor-Setup.spec'),
                        '--noconfirm', '--clean',
                        '--distpath', DIST,
                        '--workpath', os.path.join(ROOT, 'build', 'setup')],
                       cwd=ROOT, env=env)
    _check(r)


def main():
    v = version()
    print('Harbor 安装器构建 · VERSION=%s' % v)
    if '--app-only' in sys.argv:
        build_app()
        print('完成：dist/Harbor.exe')
        return
    build_app()
    build_uninstaller()
    build_setup()
    ok = (os.path.exists(os.path.join(DIST, 'Harbor-Setup-%s.exe' % v))
          and os.path.exists(os.path.join(DIST, 'Harbor-Uninstall.exe')))
    print('完成：' if ok else '异常：',
          'dist/Harbor-Setup-%s.exe（双击安装）' % v)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
