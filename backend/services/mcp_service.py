# -*- coding: utf-8 -*-
"""MCP 总服务（v1.3 R3/R6）：运行时状态机 + 分层护栏 + 审计 + 生命周期。

职责（架构 §3.3 / PRD R3/R6）：
- 运行时状态机：_rt[name] = {client, tools, status, last_error, instructions,
  server_info, last_used, lock}；status ∈ untested/ok/error/stale。
- 按需拉起 + 崩溃自动重拉一次 + idle 600s 回收；notifications/tools/list_changed →
  标记 stale + 后台刷新（刷新在独立线程，避免占用 dispatcher 线程死锁）。
- 档位：derive_tier（注解推导，最宽 session，永不放宽 off）；resolve_tier
  （tierOverrides > 注解 > 兜底 always）；check_tool/call_tool 落审计 op=mcp_call。
- 后端二次 enforce 矩阵（防前端绕过）：off 放行 / session·always 需 decision∈{allow,
  session-trust} / 否则拒绝 + 审计 block；decision='deny'（用户拒绝）→ {info, skipped}。
- 结果渲染：文本拼接 / structuredContent 序列化 / isError / 超长 >20000 走 toolcache 截断落盘。
- 函数名净化：mcp__<server>__<tool>（[^A-Za-z0-9_-]→_、>64 截断 + hash6、tool_schemas 去重 _2）。

错误人话映射（共享知识 4）集中在 _spawn_fail_text/_version_text/_protocol_error_text。
"""
import hashlib
import json
import os
import re
import threading
import time

from ..logging_setup import get_logger
from .mcp_client import (
    MCP_PROTOCOL_VERSION, McpClient, McpProtocolError, McpTimeoutError, McpVersionError)
from .mcp_transport_http import HttpTransport
from .mcp_transport_stdio import StdioTransport
from .mcp_pool import WarmRegistry, WARM_ENTRY_IDLE_TTL

IDLE_TIMEOUT = 600            # stdio 空闲回收（秒，裁决③固定不暴露 UI）
CALL_TIMEOUT = 60             # tools/call 默认阈值（修复 F2 v1.4：可被每服务器 callTimeout 覆盖，10-300s）
CALL_TIMEOUT_MIN = 10         # 修复 F2（v1.4）：配置下限
CALL_TIMEOUT_MAX = 300        # 修复 F2（v1.4）：配置上限
CONNECT_TIMEOUT = 30          # 握手/冷启（npx 首次下载依赖）
LIST_TIMEOUT = 15             # tools/list
OUTPUT_CACHE_LIMIT = 20000    # 超长输出截断落盘阈值（字符）
IDLE_SWEEP_INTERVAL = 30      # 空闲回收扫描周期（秒）

_STATUS_PUBLIC = {'ok': 'ok', 'error': 'error'}   # untested/stale → 'stale'


def _entry_template():
    return {
        'client': None,
        'tools': [],
        'status': 'untested',
        'last_error': '',
        'instructions': '',
        'server_info': {},
        'last_used': 0.0,
        'lock': threading.RLock(),
    }


class McpService:
    """MCP 总服务：被 Api 门面持有；配置经 McpConfigService，审计复用 GuardService。"""

    def __init__(self, config, guard, toolcache, logger=None):
        self._log = logger or get_logger()
        self._cfg = config
        self._guard = guard
        self._toolcache = toolcache
        self._rt = {}
        self._lock = threading.RLock()
        # 修复 ㉒：净化名 → 原名反解映射（tool_schemas 重建时刷新）
        self._server_alias = {}      # 净化 server 段 -> 原始服务器名
        self._tool_alias = {}        # (净化 server 段, 净化 tool 段含 _2 后缀) -> 原始工具名
        # 修复 S4①/W26：MCP 会话信任态（键 server__tool；切会话清空）
        self._session_trust = set()
        # 修复 S2（v1.5.1）：stdio 温启登记表（启用/测试后保留 client；IDLE 到期转
        # warm 独家持有，warm 600s 到期才真正关闭）+ spawn 打点（server → ms）
        self._warm = WarmRegistry()
        self._spawn_ms = {}
        self._reaper_stop = threading.Event()
        self._reaper = threading.Thread(target=self._idle_loop, daemon=True,
                                        name='mcp-idle-reaper')
        self._reaper.start()

    def clear_session_trust(self):
        """切会话清空 MCP 会话信任（Api.set_current_sid 检测 sid 变化时调用，W26）。"""
        with self._lock:
            self._session_trust.clear()

    # ============ 面板数据 ============
    def list_servers(self) -> list:
        """合并配置与运行时状态：[{name, transport, enabled, status, tool_count, last_error}]。"""
        out = []
        for s in self._cfg.list_servers():
            entry = self._rt.get(s['name']) or {}
            # 修复 ㉖：多字段快照在 entry 锁内读取（原无锁可撕开：status/tool_count 来自不同瞬间）
            with entry.get('lock', threading.RLock()):
                if not s['enabled']:
                    status, tool_count, last_error = 'disabled', 0, ''
                else:
                    status = _STATUS_PUBLIC.get(entry.get('status'), 'stale')
                    tool_count = len(entry.get('tools') or [])
                    last_error = entry.get('last_error') or ''
            out.append({'name': s['name'], 'transport': s['transport'],
                        'enabled': s['enabled'], 'status': status,
                        'tool_count': tool_count, 'last_error': last_error,
                        # 修复 F2（v1.4）：透出 callTimeout（前端桥接动态超时用；未配置=null→回落 60）
                        'callTimeout': s.get('callTimeout'),
                        # 修复 S2（v1.5.1）：温启状态与冷启耗时（面板「已预热/冷启 Nms」）
                        'warm': self._warm.get(s['name']) is not None,
                        'spawn_ms': self._spawn_ms.get(s['name'])})
        return out

    def save_server(self, name: str, cfg: dict, activate: bool = False) -> dict:
        """配置保存便捷入口（Api 装配用；实际逻辑在 McpConfigService）。"""
        return self._cfg.save_server(name, cfg, activate)

    def test_server(self, name) -> dict:
        """连接 + tools/list + 档位推导；不落 enabled；供「测试连接」与启用流程。"""
        cfg = self._cfg.get_server(name)
        if not cfg:
            return {'error': '服务器不存在: %s' % name}
        entry = self._ensure_entry(name)
        with entry['lock']:
            self._close_client(entry)      # 旧客户端（如有）先关，防子进程泄漏
            client, error = self._spawn_client(name, cfg)
            if error:
                entry['status'] = 'error'
                entry['last_error'] = error
                return {'error': error}
            try:
                tools = client.list_tools()
            except Exception as e:
                self._close_client(entry)
                entry['status'] = 'error'
                entry['last_error'] = self._failure_text(e)
                return {'error': entry['last_error']}
            entry['client'] = client
            entry['tools'] = tools
            entry['status'] = 'ok'
            entry['last_error'] = ''
            entry['server_info'] = client.server_info
            entry['instructions'] = client.instructions
            entry['last_used'] = time.monotonic()   # 修复 ㊉：空闲计时用单调时钟
            try:
                client.clear_list_changed()         # 修复 ⑨：list_changed 标志刷新后复位
            except Exception:
                pass
            snapshot = list(tools)
        # 修复 S2（v1.5.1）：测试成功即登记温启（entry 持有同一 client，
        # warm 仅作索引；_close_client 时同步摘除）
        self._warm.register(name, client)
        return {'ok': True, 'server_info': entry['server_info'],
                'protocol_version': MCP_PROTOCOL_VERSION,
                'instructions': entry['instructions'],
                'tools': [self._tool_view(name, t) for t in snapshot]}

    def get_server_detail(self, name) -> dict:
        """解密配置视图 + 运行时状态 + 工具现档位（编辑器回显用；裁决⑤）。"""
        cfg = self._cfg.get_server(name)
        if not cfg:
            return {'error': '服务器不存在: %s' % name}
        entry = self._rt.get(name) or {}
        with entry.get('lock', threading.RLock()):   # 修复 ㉖：快照读加锁
            status_raw = entry.get('status')
            last_error = entry.get('last_error') or ''
            tools_snap = list(entry.get('tools') or [])
            instructions = entry.get('instructions') or ''
            server_info = entry.get('server_info') or {}
        if not cfg.get('enabled'):
            status = 'disabled'
        else:
            status = _STATUS_PUBLIC.get(status_raw, 'stale')
        return {
            'ok': True, 'name': name,
            'transport': 'http' if cfg.get('url') else 'stdio',
            'status': status,
            'last_error': last_error,
            'config': cfg,
            'tierOverrides': cfg.get('tierOverrides') or {},
            'tools': [self._tool_view(name, t) for t in tools_snap],
            'instructions': instructions,
            'server_info': server_info,
            'decrypt_failed': cfg.get('decrypt_failed') or [],
        }

    # ============ 注入 ============
    def tool_schemas(self) -> list:
        """enabled 且 ok 的服务器 → OpenAI 函数定义（读缓存零 IO；stale/error 跳过）。"""
        enabled = {s['name'] for s in self._cfg.list_servers() if s.get('enabled')}
        with self._lock:
            names = [n for n, e in self._rt.items()
                     if e.get('status') == 'ok' and n in enabled]
        out, used = [], {}
        server_alias, tool_alias = {}, {}
        for name in names:
            entry = self._rt.get(name) or {}
            for tool in entry.get('tools') or []:
                fname = self._unique_name(
                    self.function_name(name, tool.get('name', '')), used)
                # 修复 ㉒：登记净化名反解映射（_2 去重后缀/特殊字符在派发时可还原原名）
                segs = fname.split('__', 2)
                if len(segs) == 3:
                    server_alias[segs[1]] = name
                    tool_alias[(segs[1], segs[2])] = tool.get('name', '')
                out.append({'type': 'function', 'function': {
                    'name': fname,
                    'description': '[MCP·%s] %s' % (
                        name, tool.get('description') or tool.get('name') or ''),
                    'parameters': tool.get('inputSchema')
                                  or {'type': 'object', 'properties': {}},
                }})
        with self._lock:
            self._server_alias = server_alias
            self._tool_alias = tool_alias
        return out

    # ============ 档位 ============
    @staticmethod
    def derive_tier(annotations: dict) -> str:
        """注解推导默认档位（注解不可信：最宽 session，永不放宽 off）。"""
        a = annotations or {}
        if a.get('destructiveHint') is True:
            return 'always'
        if a.get('readOnlyHint') is True:
            return 'session'
        return 'always'      # 无注解 → 保守每次确认

    @staticmethod
    def function_name(server: str, tool: str) -> str:
        """mcp__<server>__<tool> 净化（§3.6）。"""
        s = re.sub(r'[^A-Za-z0-9_-]', '_', str(server or '')).strip('_') or 'server'
        t = re.sub(r'[^A-Za-z0-9_-]', '_', str(tool or '')).strip('_') or 'tool'
        name = 'mcp__%s__%s' % (s, t)
        if len(name) > 64:                      # GLM/OpenAI 函数名上限
            h = hashlib.sha256(name.encode('utf-8')).hexdigest()[:6]
            name = name[:57] + '_' + h
        return name

    @staticmethod
    def _unique_name(name: str, used: dict) -> str:
        """同会话净化后重名 → _2/_3 后缀（保证 LLM 看到的函数名唯一）。"""
        if name not in used:
            used[name] = 1
            return name
        while True:
            used[name] += 1
            cand = '%s_%d' % (name, used[name])
            if cand not in used:
                used[cand] = 1
                return cand

    def _resolve_names(self, server, tool):
        """修复 ㉒：前端从净化函数名（mcp__srv__tool[_2]）反解出原始 server/tool。"""
        skey = str(server or '')
        tkey = str(tool or '')
        with self._lock:
            real_server = self._server_alias.get(skey, server)
            real_tool = self._tool_alias.get((skey, tkey), tool)
        return real_server, real_tool

    def resolve_tier(self, server: str, tool: str):
        """(tier, source)：tierOverrides > 注解推导 > 兜底 always（工具未缓存）。"""
        cfg = self._cfg.get_server(server) or {}
        override = (cfg.get('tierOverrides') or {}).get(tool)
        if override in ('always', 'session', 'off'):
            return override, 'override'
        entry = self._rt.get(server) or {}
        for t in entry.get('tools') or []:
            if t.get('name') == tool:
                annotations = t.get('annotations')
                if annotations:
                    return self.derive_tier(annotations), 'annotation'
                break
        return 'always', 'default'

    def _tool_view(self, server: str, tool: dict) -> dict:
        tier, source = self.resolve_tier(server, tool.get('name', ''))
        return {'name': tool.get('name', ''),
                'description': tool.get('description') or '',
                'annotations': tool.get('annotations') or {},
                'tier': tier, 'tier_source': source}

    # ============ 护栏 ============
    def check_tool(self, server: str, tool: str, arguments: dict = None) -> dict:
        """定档判定（前端确认框依据）：off=allow / always|session=confirm / 不可用=block。"""
        server, tool = self._resolve_names(server, tool)   # 修复 ㉒：净化名反解
        cfg = self._cfg.get_server(server)
        if not cfg:
            self._audit(server, tool, arguments, 'block')
            return {'action': 'block', 'reason': 'MCP 服务器 %s 不存在。' % server}
        if not cfg.get('enabled'):
            self._audit(server, tool, arguments, 'block')
            return {'action': 'block',
                    'reason': 'MCP 服务器 %s 未启用（可能已禁用或崩溃），请先在设置中测试连接。' % server}
        tier, source = self.resolve_tier(server, tool)
        self._audit(server, tool, arguments, 'check', tier=tier, source=source)
        if tier == 'off':
            return {'action': 'allow', 'tier': tier, 'tier_source': source}
        return {'action': 'confirm', 'tier': tier, 'tier_source': source,
                'reason': '该工具需要确认（档位 %s）。' % tier}

    def call_tool(self, server: str, tool: str, arguments: dict = None,
                  decision: str = 'deny', token: str = None) -> dict:
        """执行 MCP 工具（后端二次 enforce + 审计 + 按需拉起 + 结果渲染）。

        修复 S4①：护栏武装后（桌面 UI 会话），always 档还须一次性 confirm token，
        session 档须 token 或后端会话信任——前端注入伪造 decision='allow' 不再够用。"""
        arguments = arguments or {}
        server, tool = self._resolve_names(server, tool)   # 修复 ㉒：净化名反解
        cfg = self._cfg.get_server(server)
        if not cfg:
            self._audit(server, tool, arguments, 'block')
            return {'error': 'MCP 服务器 %s 不存在。' % server}
        if not cfg.get('enabled'):
            self._audit(server, tool, arguments, 'block')
            return {'error': 'MCP 服务器 %s 未启用（可能已禁用或崩溃），请先在设置中测试连接。' % server}
        tier, source = self.resolve_tier(server, tool)

        # 用户显式拒绝（任何档位）→ 审计 decision=deny + Agent 可见人话（§14: {info, skipped}）
        if decision == 'deny':
            self._audit(server, tool, arguments, 'decision', 'deny', tier, source)
            return {'info': '用户拒绝了本次 MCP 工具调用（%s · %s）。请调整方案或询问用户意图，'
                            '不要原样重试。' % (server, tool), 'skipped': True}
        # enforce 矩阵：off 放行；session/always 需 decision∈{allow, session-trust}
        if tier != 'off' and decision not in ('allow', 'session-trust'):
            self._audit(server, tool, arguments, 'block', decision or 'deny', tier, source)
            return {'error': '该工具需要确认（档位 %s）。请通过界面确认后重试，'
                             '不要绕过确认流程。' % tier}
        # 修复 S4①：武装后 token/会话信任后端强制（未武装环境保持原 decision 矩阵）
        if tier != 'off' and getattr(self._guard, 'armed', False):
            trust_key = '%s__%s' % (server, tool)
            token_ok = bool(token) and self._guard.consume_token(
                'mcp_call', {'server': server, 'tool': tool}, token)
            # 修复 W4（二轮）：信任判定不区分档位（与 guard 信任前移同型）——
            # 原只在 session 档查信任，always 档「本会话不再提示」登记后永不生效
            with self._lock:
                trusted = trust_key in self._session_trust
            if not token_ok and not trusted:
                self._audit(server, tool, arguments, 'block', 'token-missing', tier, source)
                return {'error': '该工具需要界面确认后携带一次性确认 token 执行（档位 %s），'
                                 '请通过界面确认流程，不要绕过。' % tier}
            if token_ok and decision == 'session-trust':
                with self._lock:
                    self._session_trust.add(trust_key)

        entry = self._ensure_entry(server)
        client, error = self._get_or_spawn(server, entry)
        if error:
            # 修复 建议⑱（二轮）：spawn 失败时退还已消耗的 token——
            # 用户在界面确认过，不应因服务器拉起失败被白扣一次确认
            if token and hasattr(self._guard, 'refund_token'):
                try:
                    self._guard.refund_token('mcp_call', {'server': server, 'tool': tool}, token)
                except Exception:
                    pass
            self._audit(server, tool, arguments, 'decision', decision, tier, source)
            return {'error': error}
        t0 = time.monotonic()
        # 修复 F2（v1.4）：每服务器 callTimeout 覆盖默认阈值（mcp_servers.json，10-300s）
        cfg_ro = self._cfg.get_server(server) or {}
        try:
            _ct = int(cfg_ro.get('callTimeout'))
        except (TypeError, ValueError):
            _ct = CALL_TIMEOUT
        eff_timeout = min(max(_ct, CALL_TIMEOUT_MIN), CALL_TIMEOUT_MAX)
        try:
            result = client.call_tool(tool, arguments, eff_timeout)
        except McpTimeoutError:
            entry['last_error'] = 'timeout'
            self._audit(server, tool, arguments, 'decision', decision, tier, source)
            # 修复 ㉑：超时时长用实际生效值而非硬编码
            return {'error': 'MCP 工具调用超时（%d 秒），已发送取消。可重试或确认服务器是否卡死。'
                             % eff_timeout}
        except McpProtocolError as e:
            entry['last_error'] = e.message
            self._audit(server, tool, arguments, 'decision', decision, tier, source)
            return {'error': self._protocol_error_text(e)}
        except Exception as e:
            entry['last_error'] = str(e)
            self._audit(server, tool, arguments, 'decision', decision, tier, source)
            return {'error': 'MCP 工具调用失败: %s' % e}
        rendered = self._render_result(result)
        self._audit(server, tool, arguments, 'decision', decision, tier, source)
        return rendered

    # ============ 生命周期 ============
    def _ensure_entry(self, name):
        with self._lock:
            entry = self._rt.get(name)
            if entry is None:
                entry = _entry_template()
                self._rt[name] = entry
            return entry

    def forget(self, name):
        """删除服务器时清运行时（关客户端）。"""
        name = str(name)
        with self._lock:
            entry = self._rt.pop(name, None)
        if entry is not None:
            with entry['lock']:
                self._close_client(entry, name)

    def shutdown(self) -> dict:
        """逆序关闭全部传输（main.py atexit 注册）。返回 {ok, closed}。"""
        self._reaper_stop.set()
        closed = 0
        with self._lock:
            entries = list(self._rt.values())
        for entry in entries:
            with entry['lock']:
                if entry.get('client') is not None:
                    try:
                        entry['client'].close()
                    except Exception:
                        pass
                    entry['client'] = None
                    closed += 1
        # 修复 S2（v1.5.1）：关闭全部温启条目（pop 出 client 逐个关，防子进程泄漏）
        for server in self._warm.stats()['warm']:
            stale = self._warm.pop(server)
            if stale is not None:
                try:
                    stale.close()
                except Exception:
                    pass
                closed += 1
        return {'ok': True, 'closed': closed}

    def _idle_loop(self):
        # 修复 ㉑：等待切片化（≤1s）保证 shutdown 及时响应，但扫描周期按 IDLE_SWEEP_INTERVAL
        # 计（原 min(30,1.0) 使每次唤醒都全量扫描，与常量意图不符）；
        # 修复 ㊉：空闲计时统一单调时钟（time.monotonic，不受系统时间回拨影响）。
        last_sweep = time.monotonic()
        while not self._reaper_stop.wait(1.0):
            now = time.monotonic()
            if now - last_sweep < IDLE_SWEEP_INTERVAL:
                continue
            last_sweep = now
            with self._lock:
                entries = list(self._rt.items())
            for srv_name, entry in entries:
                with entry['lock']:
                    client = entry.get('client')
                    if client is not None and now - (entry.get('last_used') or now) > IDLE_TIMEOUT:
                        # 修复 S2（v1.5.1）设计修正：到期直接关闭（原语义）——不停留
                        # warm 续期（那会把停用服务器的子进程多留 600s，泄漏面放大）；
                        # warm 只承担「启用预热 + 索引可见性」，回收兜底仍由 IDLE 负责。
                        try:
                            client.close()
                        except Exception:
                            pass
                        entry['client'] = None
                        self._warm.unregister(srv_name)
                        self._log.info('MCP 服务器空闲超 %ss，已回收子进程', IDLE_TIMEOUT)
            # 修复 S2：warm 过期条目清理（理论上已被 unregister/关闭覆盖，双保险防泄漏）
            for server in self._warm.reap():
                stale = self._warm.pop(server)
                if stale is not None:
                    try:
                        stale.close()
                    except Exception:
                        pass
                    self._log.info('温启条目 %s 超 %ss 未用，已关闭', server, WARM_ENTRY_IDLE_TTL)

    # ============ 拉起/重拉 ============
    def _get_or_spawn(self, name, entry=None):
        """双检锁：活客户端直接用；进程已死 → 重拉一次；无客户端 → 按需拉起。"""
        entry = entry or self._ensure_entry(name)
        cfg = self._cfg.get_server(name)
        if not cfg:
            return None, 'MCP 服务器 %s 不存在。' % name
        if not cfg.get('enabled'):
            return None, ('MCP 服务器 %s 未启用（可能已禁用或崩溃），'
                          '请先在设置中测试连接。' % name)
        with entry['lock']:
            client = entry.get('client')
            if client is not None:
                if client.is_alive():
                    entry['last_used'] = time.monotonic()
                    return client, None
                # 进程已死 → 自动重拉一次（R6 兜底）
                # 真实属性是 _transport（StdioTransport 有 returncode property；HTTP 无 → None → 显示 ?）
                rc = getattr(getattr(client, '_transport', None), 'returncode', None)
                self._close_client(entry)
                client, error = self._spawn_client(name, cfg)
                if error:
                    entry['status'] = 'error'
                    entry['last_error'] = (
                        'MCP 服务器进程已崩溃（退出码 %s），已自动重拉一次；仍失败请检查服务器后重试。%s'
                        % (rc if rc is not None else '?', error))
                    return None, entry['last_error']
                entry['client'] = client
                entry['status'] = 'ok'
                entry['last_error'] = ''
                entry['last_used'] = time.monotonic()
                self._relist(entry, client)
                return client, None
            # 按需拉起
            # 修复 S2（v1.5.1）：温启优先——warm 表有活 client（启用/测试后保留的）
            # 直接上车，跳过 spawn（首调用零延迟）；死的/过期的丢弃再走冷启
            warm_client = self._warm.get(name)
            if warm_client is not None:
                try:
                    if warm_client.is_alive():
                        entry['client'] = warm_client
                        entry['status'] = 'ok'
                        entry['last_error'] = ''
                        entry['last_used'] = time.monotonic()
                        self._relist(entry, warm_client)
                        return warm_client, None
                except Exception:
                    pass
                # 温启条目已死：摘掉并冷启
                try:
                    warm_client.close()
                except Exception:
                    pass
                self._warm.unregister(name)
            client, error = self._spawn_client(name, cfg)
            if error:
                entry['status'] = 'error'
                entry['last_error'] = error
                return None, error
            entry['client'] = client
            entry['status'] = 'ok'
            entry['last_error'] = ''
            entry['last_used'] = time.monotonic()
            self._warm.register(name, client)   # 修复 S2：冷启成功也登记温启
            self._relist(entry, client)
            return client, None

    def _relist(self, entry, client):
        """拉起后补一次 tools/list（重启后缓存为空时必须；异常不阻断调用）。"""
        try:
            entry['tools'] = client.list_tools()
            entry['server_info'] = client.server_info
            entry['instructions'] = client.instructions
            try:
                client.clear_list_changed()     # 修复 ⑨：标志复位
            except Exception:
                pass
        except Exception as e:
            self._log.debug('拉起后 tools/list 失败: %r', e)

    @staticmethod
    def _sanitize_secret_mapping(mapping):
        """修复 W21：解密失败的值（仍以 dpapi: 开头的密文串）置 ''，绝不下发子进程/HTTP 头。"""
        out = {}
        for k, v in (mapping or {}).items():
            s = str(v if v is not None else '')
            out[str(k)] = '' if s.startswith('dpapi:') else s
        return out

    def _spawn_client(self, name, cfg):
        """创建传输 + 客户端并握手。返回 (client, None) 或 (None, 人话错误)。

        修复 S2（v1.5.1）：spawn 打点（t0→ready 毫秒数，状态面板「冷启耗时 Nms」）。"""
        _t_spawn = time.monotonic()
        if cfg.get('url'):
            transport = HttpTransport(cfg['url'], self._sanitize_secret_mapping(cfg.get('headers')),
                                      logger=self._log)
            target = cfg['url']
        else:
            transport = StdioTransport(logger=self._log)
            # 修复 W19：precheck 做 expandvars 而原 spawn 不做，含 %VAR% 命令预检过但启动失败；
            # 拉起前统一展开环境变量
            command = os.path.expandvars(str(cfg.get('command') or ''))
            args = [os.path.expandvars(str(a)) for a in (cfg.get('args') or [])]
            target = command
            if not transport.start(command, args,
                                   self._sanitize_secret_mapping(cfg.get('env'))):
                return None, self._spawn_fail_text(target)
        client = McpClient(transport, logger=self._log)
        client.set_on_list_changed(lambda n=name: self._on_list_changed(n))
        try:
            client.connect()
        except McpVersionError as e:
            client.close()
            return None, self._version_text(e)
        except McpTimeoutError:
            client.close()
            return None, self._spawn_fail_text(target, '握手超时')
        except McpProtocolError as e:
            client.close()
            return None, self._spawn_fail_text(target, e.message)
        except Exception as e:
            client.close()
            return None, self._spawn_fail_text(target, str(e))
        self._spawn_ms[name] = round((time.monotonic() - _t_spawn) * 1000)   # 修复 S2：冷启打点
        return client, None

    def _on_list_changed(self, name):
        """tools/list_changed：标记 stale + 后台刷新（刷新在独立线程，不占 dispatcher）。

        修复 W22：entry 级 refreshing 去抖——通知洪泛时合并为一次刷新，不再每条起一个线程。"""
        entry = self._rt.get(name)
        if entry is None:
            return
        with entry['lock']:
            if entry.get('refreshing'):
                return
            entry['refreshing'] = True
            entry['status'] = 'stale'
            entry['last_error'] = ''
        threading.Thread(target=self._refresh_tools, args=(name,),
                         daemon=True, name='mcp-refresh').start()

    def _refresh_tools(self, name):
        entry = self._rt.get(name)
        if entry is None:
            return
        client = entry.get('client')
        if client is None:
            with entry['lock']:
                entry['refreshing'] = False
            return                      # 已回收：下次按需拉起时自然刷新
        # 修复 建议⑲（二轮）：list_tools 网络 IO 移出 entry 锁——原持锁做 15s 阻塞，
        # 期间 shutdown/call_tool/idle 回收全部干等
        try:
            tools = client.list_tools()
            with entry['lock']:
                entry['tools'] = tools
                entry['status'] = 'ok'
                entry['last_error'] = ''
                try:
                    client.clear_list_changed()     # 修复 ⑨：标志复位
                except Exception:
                    pass
        except Exception as e:
            with entry['lock']:
                entry['status'] = 'error'
                entry['last_error'] = self._failure_text(e)
        finally:
            with entry['lock']:
                entry['refreshing'] = False

    def _close_client(self, entry, name=None):
        # 修复 S2（v1.5.1）：显式关闭（删除/停用/崩溃重拉）时同步摘 warm——
        # 否则 warm 仍持死 client，下次 get 命中后 is_alive 检查才丢（多一次往返）
        if name is not None:
            self._warm.unregister(name)
        client = entry.get('client')
        entry['client'] = None
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    # ============ 结果渲染 ============
    def _render_result(self, result) -> dict:
        """MCP tools/call result → {ok, output} / {error}（isError）；超长截断落盘。"""
        result = result or {}
        text = self._content_text(result)
        if result.get('isError'):
            return {'error': text or 'MCP 工具返回执行错误（isError）。'}
        if not text:
            sc = result.get('structuredContent')
            if sc is not None:
                try:
                    text = json.dumps(sc, ensure_ascii=False, indent=2)
                except Exception:
                    text = str(sc)
        if not text:
            text = '（MCP 工具无返回内容）'
        if len(text) > OUTPUT_CACHE_LIMIT:
            cid = self._toolcache.cache(text)
            if cid:
                text = (text[:OUTPUT_CACHE_LIMIT] +
                        '\n…(输出过长已截断，全文 %d 字符；续读 read_more(cache_id="%s", '
                        'offset=0, limit=2000))' % (len(text), cid))
            else:
                # 修复 W19（二轮）：落盘失败也不能让超长原文进上下文（撑爆 prompt）
                self._log.warning('toolcache 落盘失败，超长输出已硬截断')
                text = (text[:OUTPUT_CACHE_LIMIT] +
                        '\n…(输出过长已截断；缓存落盘失败，无法 read_more 续读)')
        return {'ok': True, 'output': text}

    @staticmethod
    def _content_text(result) -> str:
        parts = []
        for item in (result or {}).get('content') or []:
            if not isinstance(item, dict):
                continue
            t = item.get('type')
            if t == 'text':
                parts.append(str(item.get('text') or ''))
            elif t in ('image', 'audio'):
                parts.append('[MCP %s %s，v1.3 不在对话中展示]'
                             % ('图片' if t == 'image' else '音频', item.get('mimeType') or ''))
            elif t == 'resource':
                res = item.get('resource') or {}
                parts.append('[MCP 资源 %s]' % (res.get('uri') or res.get('name') or ''))
            else:
                parts.append(json.dumps(item, ensure_ascii=False)[:500])
        return '\n'.join(p for p in parts if p)

    # ============ 错误人话映射（共享知识 4）============
    @staticmethod
    def _spawn_fail_text(target, extra='') -> str:
        base = ('无法启动 MCP 服务器（命令：%s）。请确认该命令已安装且可在命令行运行。'
                % (target or '?'))
        return base + ('（%s）' % extra if extra else '')

    @staticmethod
    def _version_text(e: McpVersionError) -> str:
        text = ('该 MCP 服务器支持协议版本 %s，GLM-Chat 支持 %s。请升级该服务器，'
                '或在设置中暂时禁用它。' % (e.server_version, MCP_PROTOCOL_VERSION))
        if e.supported:
            text += '（服务器支持版本：%s）' % ', '.join(str(v) for v in e.supported)
        return text

    @staticmethod
    def _protocol_error_text(e: McpProtocolError) -> str:
        if e.code == -32602:
            return '服务器未提供该工具（可能已升级/卸载）。可在设置中刷新工具列表后重试。'
        if e.code == -32601:
            # 修复 ㉑：此处是 tools/call 等【我方请求】收到的 -32601，原文案错配成服务器反向请求
            return '服务器不认识该请求方法（-32601），可能服务器版本过旧或该能力已被移除。'
        return 'MCP 协议错误（%s）：%s' % (e.code, e.message)

    @staticmethod
    def _failure_text(e) -> str:
        if isinstance(e, McpTimeoutError):
            return 'MCP 请求超时（%s 秒）。可重试或确认服务器是否卡死。' % e.timeout
        if isinstance(e, McpProtocolError):
            return McpService._protocol_error_text(e)
        return 'MCP 连接失败: %s' % e

    # ============ 审计 ============
    def _audit(self, server, tool, arguments, action, decision=None,
               tier='', source=''):
        """审计 op=mcp_call；detail 键 {server, tool, args, tier, tier_source}
        （禁用 path/name/head 键——避免审计查看器误渲染）。"""
        detail = {
            'server': str(server or ''),
            'tool': str(tool or ''),
            'args': self._args_summary(arguments),
            'tier': tier or '',
            'tier_source': source or '',
        }
        try:
            self._guard.audit('mcp_call', detail, action, decision)
        except Exception as e:
            self._log.warning('mcp_call 审计写入失败: %r', e)

    @staticmethod
    def _args_summary(arguments) -> str:
        try:
            s = json.dumps(arguments or {}, ensure_ascii=False)
        except Exception:
            s = str(arguments)
        return s[:200]
