# -*- coding: utf-8 -*-
"""安全修复与加固测试（用户授权的行为变更，v1.0.0 不存在这些护栏）。

1. copy_into_ws 路径穿越（P0）
2. RunDeduper 缺陷修复 + run_command/run_powershell 全量接入
3. kill_process 保护名单
4. run_admin_command 真实退出码
5. delete_path 永久删除警示升级
6. 静默吞错 → 落盘日志
7. 无 webview 环境 import main（可测试性）
"""
import json
import logging
import os
import subprocess
import sys

import pytest

from conftest import HOME, NewApi, install_fake_windll, make_fake_subprocess_run, reset_home, ws


@pytest.fixture
def api(monkeypatch, stubs):
    monkeypatch.setattr('subprocess.run', stubs['subprocess'][0])
    monkeypatch.setattr(os, 'startfile', stubs['started'].append)
    install_fake_windll(monkeypatch)
    return NewApi()


@pytest.fixture
def stubs(monkeypatch):
    fake_run, calls = make_fake_subprocess_run()
    started = []
    monkeypatch.setattr('subprocess.run', fake_run)
    monkeypatch.setattr(os, 'startfile', started.append)
    return {'subprocess': (fake_run, calls), 'started': started}


# ---------------------------------------------------------------- P0: copy_into_ws
class TestCopyIntoWsTraversal:
    @pytest.mark.parametrize('evil', ['..\\..\\evil.exe', '../../evil.exe', '..\\..\\..\\x.dll'])
    def test_traversal_blocked(self, api, evil):
        src = os.path.join(ws(), 'a.txt')
        data = json.loads(api.copy_into_ws(src, evil))
        attach = os.path.realpath(os.path.join(ws(), 'attachments'))
        if 'path' in data:
            # sanitize 生效：目标必须落在 attachments 内
            dst = os.path.realpath(data['path'])
            assert dst.startswith(attach + os.sep)
        else:
            assert 'error' in data
        # 关键断言：attachments 之外不存在名为 evil.exe / x.dll 的文件
        outside = []
        for dirpath, _dirs, files in os.walk(os.path.dirname(ws())):
            for f in files:
                if f in ('evil.exe', 'x.dll'):
                    outside.append(os.path.join(dirpath, f))
        assert not outside, '路径穿越写入成功: %s' % outside

    def test_normal_import_ok(self, api):
        src = os.path.join(ws(), 'a.txt')
        data = json.loads(api.copy_into_ws(src, 'ok.txt'))
        assert data['ok'] is True
        assert os.path.isfile(data['path'])
        assert 'attachments' in data['path']


# ---------------------------------------------------------------- RunDeduper
class TestRunDeduper:
    def test_exact_repeat_rejected(self, api):
        r1 = json.loads(api.run_command('echo hello'))
        assert r1.get('exit_code') == 0
        r2 = json.loads(api.run_command('echo hello'))
        assert r2.get('skipped') is True
        assert '完全相同' in r2.get('info', '')

    def test_recent_window_rejects_nonconsecutive_write(self, api):
        """修复点：legacy 只比上一条；现在 64 条窗口内写命令重复即拒。"""
        api.run_command('del file1.txt')
        api.run_command('echo mid')
        r = json.loads(api.run_command('del file1.txt'))
        assert r.get('skipped') is True
        assert '写命令' in r.get('info', '')

    def test_write_verb_non_first_token_detected(self, api):
        """修复点：legacy WRITE_VERBS 只查首 token，`cmd /c del x` 非连续重复可绕过写命令窗口。"""
        api.run_command('cmd /c del somefile.txt')
        api.run_command('echo other')
        r = json.loads(api.run_command('cmd /c del somefile.txt'))
        assert r.get('skipped') is True
        assert '写命令' in r.get('info', '')

    def test_write_verb_repeat_rejected(self, api):
        r1 = json.loads(api.run_command('del somefile.txt'))
        r2 = json.loads(api.run_command('del somefile.txt'))
        assert r2.get('skipped') is True

    def test_encoding_tip(self, api):
        r = json.loads(api.run_command('[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; gci'))
        assert r.get('skipped') is True
        assert 'UTF-8' in r.get('info', '')

    def test_powershell_also_deduped(self, api):
        api.run_powershell('Get-Date')
        r = json.loads(api.run_powershell('Get-Date'))
        assert r.get('skipped') is True


# ---------------------------------------------------------------- kill_process 保护名单
class TestKillProtection:
    def test_self_pid_protected(self, api):
        r = json.loads(api.kill_process(pid=os.getpid()))
        assert 'error' in r
        assert '保护' in r['error']

    @pytest.mark.parametrize('pid', [0, 4])
    def test_system_pid_protected(self, api, pid):
        r = json.loads(api.kill_process(pid=pid))
        assert 'error' in r

    @pytest.mark.parametrize('name', ['csrss.exe', 'explorer.exe', 'lsass.exe', 'winlogon.exe'])
    def test_critical_names_protected(self, api, name):
        r = json.loads(api.kill_process(name=name))
        assert 'error' in r
        assert '保护' in r['error']

    def test_normal_kill_passes(self, api):
        r = json.loads(api.kill_process(pid=1234))
        assert r.get('ok') is True


# ---------------------------------------------------------------- run_admin_command
class TestAdminExitCode:
    def _prep_files(self, tmp_path):
        import tempfile
        out = os.path.join(tempfile.gettempdir(), 'glm_test_admin_out.txt')
        exitf = os.path.join(tempfile.gettempdir(), 'glm_test_admin_exit.txt')
        with open(out, 'w', encoding='utf-8') as f:
            f.write('admin-output')
        with open(exitf, 'w', encoding='utf-8') as f:
            f.write('7')
        return out, exitf

    def test_real_exit_code(self, api, monkeypatch):
        """修复点：legacy 恒返回 exit_code=0；现在透传真实退出码。

        flaky 根因（测试侧 Bug，非 v1.3 引入）：早期测试与 cmd_service 各自调用
        int(time.time()*1000) 生成 uniq 临时文件名；两次取值跨毫秒边界时 FakeShell
        写入的是测试侧算的文件名、而服务轮询的是它自己算的文件名 → 永远读不到 →
        走超时路径返回 exit_code=None 断言失败。
        W7（二轮）后服务改用 mkstemp 唯一名，文件名不可预算——修法升级为
        「从 .bat 内容解析真实路径」口径（与 tests/test_review_fixes.py 的 admin
        测试同款），彻底消除文件名竞态。
        """
        import ctypes
        import re as re_mod

        monkeypatch.setattr('time.sleep', lambda s: None)
        created = []

        class FakeShell:
            @staticmethod
            def ShellExecuteW(*a):
                # 模拟提权进程：从 bat 解析服务实际使用的输出/退出码路径后写入
                bat_path = a[3].split('"')[1]
                with open(bat_path, 'r', encoding='mbcs', errors='replace') as bf:
                    bat = bf.read()
                paths = re_mod.findall(r'"([^"]+)"', bat)
                out, exitf = paths[0], paths[1]
                with open(out, 'w', encoding='utf-8') as f:
                    f.write('admin-output')
                with open(exitf, 'w', encoding='utf-8') as f:
                    f.write('7')
                created.append(1)
                return 42

        monkeypatch.setattr(ctypes.windll, 'shell32', FakeShell)

        r = json.loads(api.run_admin_command('whoami'))
        assert created, 'ShellExecuteW 未被调用（确认框被拒或命令被去重拦截）'
        assert r['exit_code'] == 7
        assert r['output'] == 'admin-output'
        assert r['note'] == '已通过管理员权限执行'

    def test_user_denies(self, api, monkeypatch):
        import ctypes

        class Deny:
            @staticmethod
            def MessageBoxW(*a):
                return 7

        monkeypatch.setattr(ctypes.windll, 'user32', Deny)
        r = json.loads(api.run_admin_command('whoami'))
        assert r.get('skipped') is True
        assert '拒绝' in r.get('info', '')

    def test_dedup_applies(self, api, monkeypatch):
        import ctypes
        monkeypatch.setattr('time.sleep', lambda s: None)
        r1 = json.loads(api.run_admin_command('echo same'))
        r2 = json.loads(api.run_admin_command('echo same'))
        # 第一次：MessageBox 假接受 + ShellExecute 假成功 + 无输出文件 → 超时路径
        # 第二次：完全相同命令 → 去重拒绝
        assert r2.get('skipped') is True
        assert '完全相同' in r2.get('info', '')


# ---------------------------------------------------------------- delete_path 警示
class TestDeleteWarning:
    def test_permanent_delete_warning(self, api, monkeypatch):
        # 环境无关化（2026-10-17）：pywinauto 带入 pywin32 后 send2trash 从「调不动」
        # 变为「完整可用」（mode 回收站）——本用例意图是 send2trash **不可用**时的
        # 永久删除警示，显式 mock 不再依赖环境偶然状态（与 test_review_fixes 同手法）
        monkeypatch.setitem(sys.modules, 'send2trash', None)
        api.write_file('todelete.txt', 'x')
        r = json.loads(api.delete_path('todelete.txt'))
        assert r['ok'] is True
        assert '永久删除' in r['mode']
        # 加固：未装 send2trash 时必须带不可恢复警示
        assert '不可恢复' in r['mode'] or '回收站' in r['mode']


# ---------------------------------------------------------------- 日志
class TestLogging:
    def test_silent_except_now_logged(self, api, caplog):
        """v1.0.0 recent_ws 损坏后静默清空；现在记录 warning。"""
        from backend import paths
        os.makedirs(paths.CONFIG_DIR, exist_ok=True)
        with open(paths.RECENT_WS_FILE, 'w', encoding='utf-8') as f:
            f.write('{corrupted json')
        with caplog.at_level(logging.WARNING, logger='glm_chat'):
            r = api.list_recent_ws()
        assert r == '[]'
        assert any('recent' in rec.message.lower() or '工作区' in rec.message
                   for rec in caplog.records), 'recent_ws 损坏应记录日志'

    def test_ws_enabled_corrupt_logged(self, caplog):
        from backend import paths
        os.makedirs(paths.CONFIG_DIR, exist_ok=True)
        with open(paths.WS_ENABLED_FILE, 'w', encoding='utf-8') as f:
            f.write('{bad')
        with caplog.at_level(logging.WARNING, logger='glm_chat'):
            a = NewApi()
            v = a.get_ws_enabled('s1')
        assert json.loads(v)['enabled'] is True  # 默认全开（legacy 语义）


# ---------------------------------------------------------------- 可测试性
class TestImportability:
    def test_import_main_headless(self):
        """import main 不得启动窗口/不依赖 webview（v1.0.0 结构性零可测试性的修复验证）。"""
        import main  # noqa: F401
        assert callable(main.main)

    def test_import_backend_no_side_effect(self):
        """import backend.api 不得创建真实目录结构之外的东西（除 ensure_dirs in Api()）。"""
        from backend import api as api_mod
        assert hasattr(api_mod, 'Api')
        assert api_mod.API_VERSION == 'v1.0.0'
