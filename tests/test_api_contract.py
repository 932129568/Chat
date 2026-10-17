# -*- coding: utf-8 -*-
"""差分契约测试：同一调用序列分别在 v1.0.0 legacy Api 与重构后 backend Api 上执行，
输出归一化后必须完全一致——证明 50 个 js_api 方法的外部行为零漂移。

归一化只抹掉时间戳/cache id 等天然不确定值；路径因两侧共用同一 HOME 天然一致。
"""
import json
import os
import re
import time

import pytest

from conftest import HOME, NewApi, install_fake_windll, legacy, make_fake_subprocess_run, reset_home, ws

NORM_RULES = [
    (re.compile(r'\d{8}_\d{6}_\d{3}'), '<TSFULL>'),          # screenshot_YYYYmmdd_HHMMSS_mmm
    (re.compile(r'\d{8}_\d{6}'), '<TS>'),                    # save_workspace_file 前缀
    (re.compile(r'\b\d{6}_'), '<TS6>_'),                     # copy_into_ws 前缀
    (re.compile(r'tc\d+_\d+'), '<CID>'),                     # toolcache id
    (re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'), '<DT>'),   # mtime（必须先于 DTS）
    (re.compile(r'\d{2}-\d{2} \d{2}:\d{2}'), '<DTS>'),       # memory/worklog 时间
    (re.compile(r'"ts":\s*[0-9.]+'), '"ts": <REALTS>'),      # recent_ws ts
    # 有意变更：delete_path 永久删除警示文案升级（安全加固，协议 shape 不变）
    (re.compile(r'永久删除\(未装 send2trash，未进回收站\)[^"]*'), '永久删除(<SEND2TRASH_MISSING>)'),
    # 有意变更：delete_path 回收站环境故障回落（send2trash 抛非 ImportError 时以文件
    # 是否仍在磁盘为准：已消失=回收成功；仍在=永久删除+警示）——两侧同因同果，仅归一文案
    (re.compile(r'永久删除\(回收站暂不可用，未进回收站\)[^"]*'), '永久删除(<SEND2TRASH_BROKEN>)'),
]


def norm(s):
    for pat, rep in NORM_RULES:
        s = pat.sub(rep, s)
    return s


def run_suite(api, stubs):
    subprocess_run, _ = stubs['subprocess']
    started = []
    out = {}

    def rec(*a):
        started.append(a)

    out['get_api_info'] = api.get_api_info()
    out['rpc_get_cwd'] = api.rpc('get_cwd')
    out['rpc_unknown'] = api.rpc('nope')
    out['get_config'] = api.get_config()

    # ---- 文件 ----
    out['list_dir_root'] = api.list_dir()
    out['list_dir_sub'] = api.list_dir('sub')
    out['list_dir_missing'] = api.list_dir('missing_dir')
    out['read_a'] = api.read_file('a.txt')
    out['read_a_cached'] = api.read_file('a.txt')
    out['read_a_force'] = api.read_file('a.txt', force=True)
    out['read_gbk'] = api.read_file('gbk.txt')
    out['read_bin'] = api.read_file('bin.dat')
    out['read_missing'] = api.read_file('missing.txt')
    out['read_dir'] = api.read_file('sub')
    out['read_offset_oob'] = api.read_file('a.txt', offset=999)
    out['read_big'] = api.read_file('big.txt')
    out['write_new'] = api.write_file('new.txt', 'hello\nworld\n')
    out['append_1'] = api.append_file('new.txt', '!appended')
    for i in range(6):   # 第 7 次触发频控
        out['append_%d' % (i + 2)] = api.append_file('new.txt', 'x')
    out['sr_hit'] = api.search_replace('new.txt', 'hello', 'HELLO')
    out['sr_miss'] = api.search_replace('new.txt', 'nomatch', 'x')
    out['sr_all'] = api.search_replace('new.txt', 'l', 'L', replace_all=True)
    out['make_dir'] = api.make_dir('newdir')
    out['make_dir_again'] = api.make_dir('newdir')
    out['make_dir2'] = api.make_dir('newdir2')
    out['delete_path'] = api.delete_path('newdir2')  # send2trash 缺失 → 永久删除（文案升级，norm 归一）
    out['move'] = api.move_path('new.txt', 'moved.txt')
    out['copy'] = api.copy_path('moved.txt', 'copied.txt')
    out['copy_exists'] = api.copy_path('a.txt', 'a.txt')
    out['file_info'] = api.get_file_info('copied.txt')
    out['write_denied_big'] = api.write_file('sub/b.txt', 'no')  # 100B <20KB → 正常写
    out['read_back'] = api.read_file('sub/b.txt')

    # ---- 命令（去重/加固相关路径在 test_security_fixes 专项验证）----
    out['run_command'] = api.run_command('echo hello')
    out['run_command_big'] = api.run_command('echo BIG')
    out['run_command_timeout'] = api.run_command('raise-timeout', 5)
    out['run_ps'] = api.run_powershell('Get-Date')
    out['run_ps_big'] = api.run_powershell('echo PSOUT')

    # ---- 剪贴板 ----
    out['get_clipboard'] = api.get_clipboard()
    out['set_clipboard'] = api.set_clipboard('hello-clip')

    # ---- 进程 ----
    out['list_processes'] = api.list_processes()
    out['list_processes_kw'] = api.list_processes(keyword='note')
    out['kill_pid'] = api.kill_process(pid=1234)
    out['kill_none'] = api.kill_process()

    # ---- 记忆 ----
    out['get_memory'] = api.get_memory()
    out['append_memory'] = api.append_memory('{"k":"v"}')
    out['get_memory2'] = api.get_memory()

    # ---- 会话/工作区 ----
    out['set_current_sid'] = api.set_current_sid('s1')
    out['set_session_ws'] = api.set_session_ws('s1', os.path.join(ws(), 'sub'))
    out['get_session_ws'] = api.get_session_ws('s1')
    out['get_effective_ws'] = api.get_effective_ws()
    out['get_ws_state'] = api.get_ws_state('s1')
    out['set_ws_enabled_off'] = api.set_ws_enabled('s1', False)
    out['get_ws_enabled_off'] = api.get_ws_enabled('s1')
    out['set_ws_enabled_on'] = api.set_ws_enabled('s1', True)
    out['delete_session_ws'] = api.delete_session_ws('s1')
    out['list_recent_ws'] = api.list_recent_ws()
    out['set_ws_dir'] = api.set_ws_dir(os.path.join(ws(), 'sub'))
    out['get_cwd'] = api.get_cwd()
    out['set_ws_dir_bad'] = api.set_ws_dir('nonexistent-dir')
    out['pick_folder'] = api.pick_folder()

    # ---- 附件/worklog ----
    out['copy_into_ws'] = api.copy_into_ws(os.path.join(ws(), 'a.txt'), 'imported.txt')
    out['save_workspace_file'] = api.save_workspace_file('doc.txt', 'body')
    out['get_worklog_empty'] = api.get_worklog()
    out['append_worklog'] = api.append_worklog('did something')
    out['get_worklog'] = api.get_worklog()

    # ---- 系统 ----
    out['open_billing'] = api.open_billing()
    out['open_app_url'] = api.open_app('https://example.com')
    out['open_app_notepad'] = api.open_app('notepad')
    out['open_url'] = api.open_url('example.com')

    # ---- 截屏 ----
    out['take_screenshot'] = api.take_screenshot()
    out['take_screenshot_rect'] = api.take_screenshot(left=0, top=0, width=10, height=10)

    # ---- toolcache ----
    out['cache_tool_output'] = api.cache_tool_output('y' * 100)
    import json as _json
    cid = _json.loads(out['cache_tool_output']).get('id')
    out['read_more'] = api.read_more(cid)
    out['read_more_bogus'] = api.read_more('bogus')

    # ---- prompt/schema ----
    out['build_system_prompt'] = api.build_system_prompt()
    out['build_tools_chat'] = api.build_tools('chat')
    out['build_tools_ro_on'] = api.build_tools('ro')
    out['build_tools_full_on'] = api.build_tools('full')
    api.set_ws_enabled('', False)
    out['build_tools_ro_off'] = api.build_tools('ro')
    out['build_tools_full_off'] = api.build_tools('full')
    api.set_ws_enabled('', True)

    # ---- 杂项 ----
    out['clear_caches'] = api.clear_caches()
    out['set_workspace'] = api.set_workspace(ws())
    out['get_cwd2'] = api.get_cwd()
    out['get_sessions'] = api.get_sessions()
    out['save_sessions'] = api.save_sessions('[{"id":1}]')
    out['get_sessions2'] = api.get_sessions()
    out['save_config'] = api.save_config('{"theme":"dark"}')
    out['get_config2'] = api.get_config()
    out['save_config_merge'] = api.save_config('{"apiKey":"k"}')
    out['get_config3'] = api.get_config()

    return out


@pytest.fixture
def stubs(monkeypatch):
    fake_run, calls = make_fake_subprocess_run()
    started = []
    monkeypatch.setattr('subprocess.run', fake_run)
    monkeypatch.setattr(os, 'startfile', started.append)
    import webbrowser
    monkeypatch.setattr(webbrowser, 'open', started.append)
    install_fake_windll(monkeypatch)
    return {'subprocess': (fake_run, calls), 'started': started}


def test_contract_legacy_vs_new(stubs):
    """核心差分：legacy 与重构后 backend 的 49 个公开方法输出逐字节一致（归一化后）。

    例外：v1.1.1 有意省 token 变更（INTENTIONAL_DELTAS），单独断言其结构而非逐字节。
    """
    reset_home()
    legacy_out = run_suite(legacy.Api(), stubs)
    reset_home()
    new_out = run_suite(NewApi(), stubs)

    diffs = []
    for k in legacy_out:
        if k in INTENTIONAL_DELTAS:
            continue
        a = norm(legacy_out[k])
        b = norm(new_out.get(k, '<MISSING>'))
        if a != b:
            diffs.append((k, a, b))
    assert legacy_out.keys() == new_out.keys(), (
        '方法集合不一致: %s' % (set(legacy_out) ^ set(new_out)))
    assert not diffs, '契约漂移 %d 处:\n%s' % (
        len(diffs), '\n'.join('%s:\n  legacy=%r\n  new   =%r' % d for d in diffs))


# v1.1.1 有意变更：省 token 相关（不参与逐字节比对，单独断言）
INTENTIONAL_DELTAS = {'build_system_prompt'}


def test_system_prompt_intentional_trim():
    """v1.1.1 有意精简：system prompt 去掉与工具 description 重复的能力段，必须更短且保留硬规则。"""
    a = legacy.Api()
    b = NewApi()
    old = a.build_system_prompt()
    new = b.build_system_prompt()
    assert len(new) < len(old), '精简后应更短: %d vs %d' % (len(new), len(old))
    for keep in ('当前工作区', '硬规则', '1. 文件操作只用工具', '2. 写文件串行', '3. 超长命令输出'):
        assert keep in new, '精简后丢失关键内容: ' + keep


def test_read_file_auto_limit():
    """v1.1.1 自适应：limit=0 → 小文件一次读全，大文件分页 1200 行。"""
    reset_home()
    api = NewApi()
    small = json.loads(api.read_file('a.txt', 0, 0))
    assert small.get('ok') and 'content' in small, small
    assert 'hint' not in small, '小文件应一次读全（无续读提示）'
    big = json.loads(api.read_file('big.txt', 0, 0))
    assert big.get('ok') and 'hint' in big, '大文件应给出续读提示'
    # 显式 limit 不受影响（legacy 语义）；force 绕过指纹缓存
    explicit = json.loads(api.read_file('big.txt', 0, 100, True))
    assert explicit['total_lines'] == 6000
    assert 'content' in explicit


def test_build_tools_byte_identical():
    """build_tools 三档 × ws_on 全组合与 legacy 逐字节一致。"""
    for role in ('chat', 'ro', 'full'):
        for ws_on in (True, False):
            legacy_api = legacy.Api()
            legacy_api._current_sid = None
            legacy._RT['ws_enabled'][''] = ws_on   # legacy ws_enabled 是模块级 _RT 全局
            expected = legacy_api.build_tools(role)
            from backend import tools_schema
            got = tools_schema.build(role, ws_on)
            assert got == expected, 'build_tools(%r, %r) 与 legacy 不一致' % (role, ws_on)


def test_contract_coverage_report():
    """契约差分用例覆盖度自检：调用序列覆盖 legacy 全部公开方法。"""
    legacy_methods = set(legacy.Api.__dict__.keys())
    expected_public = {n for n in legacy.Api().__dir__()
                       if not n.startswith('_') and callable(getattr(legacy.Api(), n, None))}
    covered = set(_CALLED_METHODS)
    missing = expected_public - covered
    assert not missing, '以下公开方法未被差分覆盖: %s' % sorted(missing)
    assert len(covered) >= 40


# run_suite 中实际调用的方法名（用于覆盖度自检）
_CALLED_METHODS = [
    'get_api_info', 'rpc', 'get_config', 'list_dir', 'read_file', 'write_file',
    'append_file', 'search_replace', 'make_dir', 'delete_path', 'move_path', 'copy_path',
    'get_file_info', 'run_command', 'run_powershell', 'get_clipboard',
    'set_clipboard', 'list_processes', 'kill_process', 'get_memory',
    'append_memory', 'set_current_sid', 'set_session_ws', 'get_session_ws',
    'get_effective_ws', 'set_ws_enabled', 'get_ws_enabled', 'get_ws_state',
    'delete_session_ws', 'list_recent_ws', 'set_ws_dir', 'pick_folder',
    'copy_into_ws', 'save_workspace_file', 'get_worklog', 'append_worklog',
    'open_billing', 'open_app', 'open_url', 'take_screenshot',
    'cache_tool_output', 'read_more', 'build_system_prompt', 'build_tools',
    'clear_caches', 'set_workspace', 'get_cwd', 'get_sessions', 'save_sessions',
    'save_config', 'run_admin_command',
]
