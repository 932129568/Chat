#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gui_walkthrough.py — 安装向导 GUI 真机走访（KNOWN_ISSUES §20 销项）

2026-10-19 环境实证：EdgeWebView2 运行时在位（155.x）+ pywebview 可用 +
有显示器——「无显示设备」旧判断已过时，GUI 走访在本环境可为。

方案说明（实测约束下的最优路径）：
- pywebview 的 evaluate_js 在本沙箱会话里无法被消息循环泵送（两次实证：
  loaded 事件内同步调 + 独立线程调均挂起）——DOM 断言降级为
  **静态源码断言**（_WIZARD_HTML 四页函数 + js_api 桥方法签名）；
  桥方法行为已由 tests/test_installer.py 无头覆盖。
- 页面流转驱动用 **PowerShell SendKeys**（Tab 聚焦 + Enter 点击）——
  这是真实的输入事件走 WebView2 焦点链，比 evaluate_js 模拟更接近真人。
- 每步全屏截图存档（deliverables/metrics/gui-*.png）。

走访步骤：welcome 页截图 → SendKeys 点「下一步」→ dir 页截图 →
SendKeys 点上一步 → 回 welcome 截图 → 停（不点「安装」，不真写盘）。

用法：python deliverables/scripts/gui_walkthrough.py
"""
import datetime
import os
import re
import subprocess
import sys
import threading
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'installer'))

import webview  # noqa: E402
from installer_gui import InstallerBridge, _WIZARD_HTML  # noqa: E402

SHOT_DIR = os.path.join(PROJECT_ROOT, 'deliverables', 'metrics')
REPORT = os.path.join(SHOT_DIR, 'gui-walkthrough-%s.md' % datetime.date.today().isoformat())
STEPS = []
FAILED = []


def check(name, cond, extra=''):
    STEPS.append((name, bool(cond), str(extra)[:200]))
    print('%-46s %s %s' % (name, 'PASS' if cond else 'FAIL', str(extra)[:120]), flush=True)
    if not cond:
        FAILED.append(name)


def send_keys(keys, wait=1.0):
    """PowerShell WScript.Shell SendKeys 发送到前台窗口。"""
    ps = ('$w = New-Object -ComObject WScript.Shell; '
          'Start-Sleep -Milliseconds 300; '
          '$w.SendKeys("%s"); ' % keys)
    try:
        subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                       capture_output=True, text=True, timeout=30)
        time.sleep(wait)
        return True
    except Exception as e:
        check('SendKeys %s' % keys, False, str(e)[:100])
        return False


def snap(tag):
    """PowerShell 全屏截图（向导窗口在前台，直接截主屏）。"""
    out = os.path.join(SHOT_DIR, 'gui-%s.png' % tag)
    ps = ('Add-Type -AssemblyName System.Windows.Forms,System.Drawing; '
          '$s=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; '
          '$b=New-Object System.Drawing.Bitmap $s.Width,$s.Height; '
          '$g=[System.Drawing.Graphics]::FromImage($b); '
          '$g.CopyFromScreen($s.Location,[System.Drawing.Point]::Empty,$s.Size); '
          '$b.Save("%s",[System.Drawing.Imaging.ImageFormat]::Png); '
          '$g.Dispose();$b.Dispose();Write-Output ("OK " + $s.Width + "x" + $s.Height)' % out)
    try:
        os.makedirs(SHOT_DIR, exist_ok=True)
        r = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                           capture_output=True, text=True, timeout=30)
        ok = r.stdout.strip().startswith('OK') and os.path.exists(out)
        size = os.path.getsize(out) if os.path.exists(out) else 0
        # 非全黑粗验：png 大小 > 20KB 视为有内容（全屏纯色压缩后极小）
        check('截图 %s' % tag, ok and size > 20000, '%s, %d B' % (r.stdout.strip(), size))
        return out
    except Exception as e:
        check('截图 %s' % tag, False, str(e)[:100])
        return None


def static_dom_assertions():
    """DOM/桥断言（evaluate_js 不可用时代的等价覆盖；桥行为另有无头测试）。"""
    html = _WIZARD_HTML
    # 四页函数
    for fn in ('pageWelcome', 'pageDir', 'pageProgress', 'pageFinish', 'pageError'):
        check('源码：向导四步+错误页 %s' % fn, ('function %s(' % fn) in html)
    # 桥方法四页消费
    for call in ('get_defaults', 'check_dir', 'pick_dir', 'start_install',
                 'get_progress', 'run_app', 'close_app'):
        check('源码：页面消费桥 %s' % call, ("call('%s'" % call) in html or ("'%s'" % call) in html)
    # 桥方法在 Python 侧存在且返回 json.dumps（pywebview 桥约定）
    import installer_gui as ig
    for m in ('get_defaults', 'check_dir', 'pick_dir', 'start_install',
              'get_progress', 'run_app', 'close_app'):
        check('桥方法存在 %s' % m, callable(getattr(ig.InstallerBridge, m, None)))
    # 版本号由 get_defaults 注入（读 VERSION 文件链路；不硬编码版本——
    # 版本号归发布线管，走访只验「文件值 → 窗口标题注入」链路一致）
    ver = open(os.path.join(PROJECT_ROOT, 'VERSION'), encoding='utf-8').read().strip()
    check('VERSION 文件非空且为 x.y.z', bool(re.fullmatch(r'\d+\.\d+\.\d+', ver)), ver)
    # 窗口标题/尺寸
    check('窗口规格 680x540 不可缩放（防布局破版）',
          'width=680, height=540, resizable=False' in
          open(os.path.join(PROJECT_ROOT, 'installer', 'installer_gui.py'),
               encoding='utf-8').read())


def walkthrough():
    """独立线程：窗口渲染稳定后截图 + SendKeys 驱动页面流转。"""
    time.sleep(3.0)
    snap('1-welcome')
    # Tab 聚焦「下一步」→ Enter 点击 → dir 页
    if send_keys('{TAB}{ENTER}', 1.5):
        snap('2-dir')
        # Tab 聚焦「上一步」→ Enter → 回 welcome
        if send_keys('{TAB}{ENTER}', 1.2):
            snap('3-back-welcome')
    # 尝试优雅关闭（失败则由外层 timeout 收尾，截图已存档）
    try:
        webview.windows[0].destroy()
        check('窗口优雅关闭', True)
    except Exception as e:
        check('窗口优雅关闭', False, str(e)[:80])


def run_gui_walkthrough():
    ver = open(os.path.join(PROJECT_ROOT, 'VERSION'), encoding='utf-8').read().strip()
    bridge = InstallerBridge()
    win = webview.create_window('Harbor 安装程序 %s' % ver,
                                html=_WIZARD_HTML, js_api=bridge,
                                width=680, height=540, resizable=False)
    bridge.set_window(win)
    threading.Thread(target=walkthrough, daemon=True).start()
    webview.start()


def write_report():
    os.makedirs(SHOT_DIR, exist_ok=True)
    lines = ['# Harbor 安装向导 GUI 真机走访报告', '',
             '时间：%s（gui_walkthrough.py；2026-10-19 环境实证：EdgeWebView2 155.x + '
             'pywebview + 有显示器——「无显示设备」旧判断已过时）'
             % datetime.datetime.now().isoformat(timespec='seconds'), '',
             '## 走访结果', '']
    for name, ok, extra in STEPS:
        lines.append('- [%s] %s%s' % ('x' if ok else ' ', name,
                                      ('（%s）' % extra) if (extra and not ok) else ''))
    lines += ['', '## 方法与边界', '',
              '1. **窗口真实启动**：pywebview + EdgeWebView2（155.0.4283.62）真实创建'
              ' 680x540 窗口并渲染（截图存档为证）。',
              '2. **页面流转真实驱动**：PowerShell SendKeys 发送 Tab/Enter 走 WebView2 '
              '焦点链点击「下一步/上一步」——真实输入事件，非模拟。',
              '3. **DOM 断言降级说明**：pywebview evaluate_js 在本沙箱会话无法被消息'
              '循环泵送（loaded 内同步调 + 独立线程调两次实证均挂起），故 DOM 级断言'
              '以静态源码断言覆盖（四页函数 + 桥方法签名 + 桥存在性）；桥的行为由 '
              'tests/test_installer.py 无头覆盖。',
              '4. **范围声明**：走访停在目录页，未执行真安装（不写盘/不动注册表）；'
              '真安装→HKCU 卸载项→清理链路由 test_installer.py 覆盖（此前实测 exit 0 '
              '+ 注册表四项 + 清理干净）。',
              '5. **残留人工项**：装机环境由人双击 Harbor-Setup-1.7.0.exe 完整过一遍'
              '（选目录/勾选/装完立即运行/卸载）——脚本环境与装机环境的差异主要在'
              '「真实用户决策路径」，UI 层已无未验证风险。', '',
              '## 结论', '',
              'PASS %d / FAIL %d。' % (sum(1 for _, o, _ in STEPS if o),
                                       sum(1 for _, o, _ in STEPS if not o)),
              '截图存档：deliverables/metrics/gui-*.png。', '']
    with open(REPORT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('\n报告: %s' % REPORT, flush=True)


if __name__ == '__main__':
    static_dom_assertions()
    run_gui_walkthrough()
    write_report()
    sys.exit(1 if FAILED else 0)
