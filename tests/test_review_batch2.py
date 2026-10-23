# -*- coding: utf-8 -*-
"""2026-10-24 全库 bug 扫描·核心 api 域复核批回归（13 项实证修复）。

锁定：
- P0 kill_process 预算超限分支（16 处 enforce_exec_ex 挂点唯一漏判）；
- P1 审计哈希链衔接校验（删除/重排可检出）+ 挂链与落盘同临界区（文件序==链序）；
- P2 guard：browser_fill token 摘要双形态归一 / 保护名单双形匹配 / .bad 备份；
- P2 sandbox GetLastError / checkpoint 部分失败 ok 口径；
- P2 api：get_audit_log 单次读 / save_export_file 先校验后消费 / set_workspace 走 set_cwd。

铁律：全部 hermetic（fresh_home 隔离 + monkeypatch；不触网、不起真进程）。
"""
import json
import os
from pathlib import Path

import pytest

from conftest import fresh_home  # noqa: F401  （autouse 隔离 HOME）


# ============================================================ P0：kill_process 预算超限

class TestKillProcessBudgetGate:
    def _api(self):
        from backend.api import Api
        return Api()

    def test_budget_exceeded_blocks_kill(self):
        """escalated 态：enforce_exec_ex 返回 (None, payload)——原直落
        kill_process（预算机制对结束进程完全失效），现必须结构化拦截。"""
        api = self._api()
        api._guard.arm()
        api._guard._cfg['approval_budget'] = {'limit': 5, 'used': 10,
                                              'escalated': True}
        called = []

        def _boom(pid=None, name=None):
            called.append((pid, name))
            return {'ok': True}

        orig = api._process.kill_process
        api._process.kill_process = _boom
        try:
            r = json.loads(api.kill_process(pid=None, name='notepad.exe', token=None))
            assert r.get('ok') is False, r
            assert r['error']['code'] == 'APPROVAL_BUDGET_EXCEEDED', r
            assert called == []                     # 未执行
        finally:
            api._process.kill_process = orig

    def test_normal_confirm_path_intact(self):
        """非 escalated 武装态：仍走 CONFIRM_REQUIRED（预算修正不短路授权链）。"""
        api = self._api()
        api._guard.arm()
        api._guard._cfg['approval_budget'] = {'limit': 5, 'used': 0,
                                              'escalated': False}
        r = json.loads(api.kill_process(pid=None, name='notepad.exe', token=None))
        assert r.get('error'), r                    # always 档无 token → 拒


# ============================================================ P1：审计哈希链

class TestAuditChainLinkage:
    def _chain(self, tmp_path):
        from backend.services.audit_chain import AuditChain
        return AuditChain(path=str(Path(tmp_path) / 'chain.json'))

    def test_verify_ok_forward_and_reversed(self, tmp_path):
        ch = self._chain(tmp_path)
        entries = [ch.append({'op': 'op%d' % i, 'detail': {'i': i}})
                   for i in range(4)]
        assert ch.verify(entries)['ok'] is True          # 正序
        assert ch.verify(list(reversed(entries)))['ok'] is True   # 倒序窗口（read_audit 口径）

    def test_verify_detects_deletion(self, tmp_path):
        """删除中间条目：原实现仍 ok（删除不可检出），现衔接断裂必报。"""
        ch = self._chain(tmp_path)
        entries = [ch.append({'op': 'op%d' % i, 'detail': {'i': i}})
                   for i in range(4)]
        tampered = [entries[0], entries[2], entries[3]]  # 删掉 entries[1]
        r = ch.verify(tampered)
        assert r['ok'] is False and '衔接' in r['reason']

    def test_verify_detects_reorder(self, tmp_path):
        ch = self._chain(tmp_path)
        entries = [ch.append({'op': 'op%d' % i, 'detail': {'i': i}})
                   for i in range(4)]
        r = ch.verify([entries[0], entries[2], entries[1], entries[3]])
        assert r['ok'] is False and '衔接' in r['reason']

    def test_verify_detects_swap_attack(self, tmp_path):
        """偷换中间条目内容（重算自身 hash 但衔接对不上上游）。"""
        ch = self._chain(tmp_path)
        entries = [ch.append({'op': 'op%d' % i, 'detail': {'i': i}})
                   for i in range(3)]
        from backend.services.audit_chain import entry_hash
        forged = dict(entries[1])
        forged['detail'] = {'i': 999}                    # 攻击者改内容并重算自身 hash
        body = {k: v for k, v in forged.items() if k not in ('hash', 'prev_hash')}
        forged['hash'] = entry_hash(forged['prev_hash'], body)
        r = ch.verify([entries[0], forged, entries[2]])
        assert r['ok'] is False                          # forged.prev_hash 指向 e0，但 e2.prev 指向真 e1

    def test_audit_file_order_matches_chain_order(self, tmp_path):
        """挂链与落盘同一临界区：并发审计下文件序==链序（衔接校验不误报）。"""
        import threading
        from backend.services.guard_service import GuardService
        g = GuardService(audit_path=str(Path(tmp_path) / 'a.jsonl'))
        errs = []

        def worker(i):
            try:
                for k in range(10):
                    g.audit('op', {'i': i * 100 + k}, 'check')
            except Exception as e:                       # pragma: no cover
                errs.append(e)

        ts = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(10)
        assert not errs
        raw = g.read_audit(limit=1000, offset=0)
        entries = json.loads(raw)['entries']             # 倒序（最新在前）
        vr = g.audit_chain_verify(entries)
        assert vr['ok'] is True, vr                      # 文件序==链序（并发不误报）


# ============================================================ P2：guard 三处

class TestGuardReviewFixes:
    def test_fill_digest_dual_shape(self):
        """签发侧（text 原文）与执行侧（text_len）摘要必须一致——原执行侧
        恒 text_len:0，armed 态 token 永拒。"""
        from backend.services.guard_service import GuardService
        issue = GuardService._canonical_detail(
            'browser_fill', {'selector': '#pw', 'text': 'abcde'})
        exec_ = GuardService._canonical_detail(
            'browser_fill', {'selector': '#pw', 'text_len': 5})
        assert issue == {'selector': '#pw', 'text_len': 5}
        assert issue == exec_

    def test_fill_token_issue_consume_roundtrip(self, tmp_path):
        """端到端：前端 detail 签发 token → api.browser_fill detail 消费成功。"""
        from backend.services.guard_service import GuardService
        g = GuardService(guard_path=str(Path(tmp_path) / 'g.json'))
        g.arm()
        detail_issue = {'selector': '#pw', 'text': 'secret'}
        tok = g.issue_confirm_token('browser_fill', detail_issue)
        assert tok.get('token')                          # guard 层返回 {token,ttl}（api 层包 ok）
        detail_exec = {'selector': '#pw', 'text_len': 6}
        assert g.consume_token('browser_fill', detail_exec, tok['token']) is True

    def test_path_protected_matches_plain_form_under_redirection(self, tmp_path, monkeypatch):
        """OneDrive/junction 重定向：realpath 偏移后字面登记仍命中（双形匹配）。"""
        from backend.services import guard_service as gs
        g = gs.GuardService(guard_path=str(Path(tmp_path) / 'g.json'))
        g._cfg['protect_paths'] = [gs._norm_pattern(r'C:\Users\x\Documents')]
        monkeypatch.setattr(gs.os.path, 'realpath',
                            lambda p: str(p).replace('Documents', 'OneDriveDocs')
                            if 'Documents' in str(p) else str(p))
        assert g._path_protected(r'C:\Users\x\Documents\note.md') == \
            gs._norm_pattern(r'C:\Users\x\Documents')
        assert g._path_protected(r'C:\Windows\system32\cmd.exe') is None

    def test_corrupt_guard_json_leaves_bad_backup(self, tmp_path):
        """guard.json 损坏：留 .bad 备份再回落默认（原无声清零且无迹可寻）。"""
        from backend.services.guard_service import GuardService
        guard_json = Path(tmp_path) / 'g.json'
        guard_json.write_text('{corrupt!!!', encoding='utf-8')
        gs = GuardService(guard_path=str(guard_json))
        assert Path(str(guard_json) + '.bad').exists()
        cfg = json.loads(gs.get_config())
        assert isinstance(cfg, dict)


# ============================================================ P2：sandbox / checkpoint / api 三处

class TestMiscReviewFixes:
    def test_sandbox_uses_kernel32_get_last_error(self):
        """CreateProcessW 失败分支读 k32.GetLastError()（原 get_last_error
        在未开 use_last_error 的 windll 下恒 0；既有 H6 helper 注释里也提
        该词，故断言精确到赋值语句）。"""
        import inspect
        from backend.services import sandbox_service as ss
        src = inspect.getsource(ss)
        assert 'code = ctypes.get_last_error()' not in src
        assert 'code = k32.GetLastError()' in src

    def test_checkpoint_partial_failure_not_ok(self, tmp_path):
        """快照恢复部分文件失败 → ok=False（与 git 路径口径一致）。"""
        from backend.services.checkpoint_service import CheckpointService
        svc = CheckpointService()
        ws = Path(tmp_path) / 'ws'
        ws.mkdir()
        snap = Path(tmp_path) / 'snap'
        snap.mkdir()
        (snap / 'a.txt').write_text('v1', encoding='utf-8')     # 只备份了 a
        (ws / 'a.txt').write_text('v2-current', encoding='utf-8')
        manifest = {'files': [
            {'path': 'a.txt', 'sha256': 'x', 'snapshot': True},
            {'path': 'b.txt', 'sha256': 'y', 'snapshot': True},  # 快照缺失 → 恢复失败
        ]}
        r = svc._rollback_snapshot(manifest, str(ws), str(snap))
        assert r['ok'] is False
        assert r['failed'] == ['b.txt'] and r['restored'] == ['a.txt']

    def test_get_audit_log_reads_file_once(self):
        """get_audit_log 只读一次审计文件（原连调两次 read_audit 全量扫描）。"""
        from backend.api import Api
        api = Api()
        calls = {'n': 0}
        orig = api._guard.read_audit

        def counting(*a, **kw):
            calls['n'] += 1
            return orig(*a, **kw)

        api._guard.read_audit = counting
        try:
            api.get_audit_log(limit=10)
        finally:
            api._guard.read_audit = orig
        assert calls['n'] == 1

    def test_save_export_file_oversize_keeps_registration(self):
        """超 8MB：先校验后消费——路径登记不被消费，重试无需重走对话框。"""
        from backend.api import Api
        api = Api()
        export_target = Path(os.environ.get('TEMP', str(Path.cwd()))) / 'harbor_exp.csv'
        api._export_paths.add(os.path.normcase(os.path.abspath(str(export_target))))
        r = json.loads(api.save_export_file(str(export_target), 'x' * (9 * 1024 * 1024)))
        assert r.get('error') and '8MB' in r['error']
        assert os.path.normcase(os.path.abspath(str(export_target))) in api._export_paths

    def test_set_workspace_routes_via_set_cwd(self, tmp_path):
        """set_workspace 走 set_cwd 统一入口（锁内 abspath+落盘）。"""
        from backend.api import Api
        api = Api()
        ws = Path(tmp_path) / 'ws'
        ws.mkdir()
        r = json.loads(api.set_workspace(str(ws)))
        assert r.get('ok') is True
        assert os.path.normcase(api._config.cwd) == \
            os.path.normcase(os.path.abspath(str(ws)))
