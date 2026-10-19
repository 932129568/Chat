# -*- coding: utf-8 -*-
"""安装器一键构建（v1.7.0）。

用法：
  python installer/build_setup.py            # 全量：应用 exe → 卸载器 → 安装器
  python installer/build_setup.py --app-only # 仅构建应用 Harbor.exe（等价 Harbor.spec）

产物（dist/）：
  Harbor.exe                    应用本体（onefile）
  Harbor-Uninstall.exe          卸载器（小，安装时随包进安装目录）
  Harbor-Setup-<version>.exe    安装器（内嵌上面两个，双击即向导）
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLER_DIR = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, 'dist')
PY = sys.executable


def _run(cmd, **kw):
    print('+', ' '.join(str(c) for c in cmd))
    r = subprocess.run(cmd, cwd=ROOT, **kw)
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
    _run([PY, '-m', 'PyInstaller', 'Harbor.spec', '--noconfirm', '--clean'])


def build_uninstaller():
    env = dict(os.environ, HARBOR_BUILD='uninstaller')
    _run([PY, '-m', 'PyInstaller', os.path.join('installer', 'Harbor-Setup.spec'),
          '--noconfirm', '--clean', '--distpath', DIST, '--workpath',
          os.path.join(ROOT, 'build', 'uninstaller')],
         env=env)


def build_setup():
    env = dict(os.environ, HARBOR_BUILD='setup',
               HARBOR_PAYLOAD=os.path.join(DIST, 'Harbor.exe'),
               HARBOR_UNINSTALLER=os.path.join(DIST, 'Harbor-Uninstall.exe'))
    _run([PY, '-m', 'PyInstaller', os.path.join('installer', 'Harbor-Setup.spec'),
          '--noconfirm', '--clean', '--distpath', DIST, '--workpath',
          os.path.join(ROOT, 'build', 'setup')],
         env=env)


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
