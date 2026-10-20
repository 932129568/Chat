# -*- coding: utf-8 -*-
"""Api 门面（对外契约层）：50 个 js_api 公开方法，签名/位置参数/返回协议逐字保持 v1.0.0。

红线（重构生命线）：
1. 方法名、参数个数、位置顺序不变——前端 callApi 按位置传参。
2. 三个"方言"原样保留：get_clipboard/set_clipboard（schema 里叫 clipboard_read/write）、
   append_memory(entry_json) 位置参数传 JSON 串。
3. 方法-only 表面：不挂公开可变属性（legacy L168-175 的 4 个公开属性已下沉为私有）。
4. 返回均为 JSON 字符串（get_cwd/get_worklog 裸文本协议保持 legacy 原样）。

v1.2 追加 guard/update/provider 共 10 个、v1.3 追加 mcp_* 共 10 个隐身方法（_V12_EXTRA）。
"""
import json
import os
import sys

from . import paths
from . import tools_schema
from .errors import err, ok
from .logging_setup import get_logger
from .runtime import RuntimeState
from .services.config_service import ConfigService
from .services.clipboard_service import ClipboardService
from .services.cmd_service import CmdService
from .services.file_service import FileService
from .services.guard_service import GuardService
from .services.hybrid_router import HybridRouter
from .services.local_model_service import LocalModelService
from .services.local_proxy import get_proxy
from .services.mcp_config_service import McpConfigService
from .services.mcp_service import McpService
from .services.process_service import ProcessService
from .services.provider_service import ProviderService
from .services.sandbox_service import SandboxService
from .services.screenshot_service import ScreenshotService
from .services.search_service import SearchService
from .services.software_service import SoftwareService
from .services.toolcache_service import ToolcacheService
from .services.update_service import UpdateService
from .services.webdav_service import WebDAVService
from .services.workspace_service import WorkspaceService
from .services import update_service as _update_mod

API_VERSION = 'v1.0.0'

# rpc 通用分发通道的私有方法白名单（v1.8.0 S 域）：用户自定义软件条目的
# CRUD 经 rpc 暴露（契约 js_api 方法面恰为 software×3——联调规范 §1.2，
# 不新增 _V12_EXTRA 方法、不进 get_api_info 自省面）。仅限这两个已知
# 安全的注册表写入入口，其余私有方法仍一律拒绝（原有防护不放松）。
_RPC_PRIVATE_OK = frozenset({'_software_save', '_software_remove'})

# v1.2 新增的 js_api 方法（guard / update / provider）+ v1.3 MCP（10 个）。
# 它们对 get_api_info() 的方法清单【隐身】：该输出与 legacy 逐字节比对（契约差分测试），
# 因此自省时排除。pywebview 桥接按属性枚举照常暴露这些方法，前端可直接调用。
# v1.5 预留接口（local_* 本地模型 / webdav_* 数据主权）：同样隐身，签名与返回
# shape 为终态（deliverables/dev-plan/reserved-interfaces-v15-2026-10-17.md）。
_V12_EXTRA = frozenset({
    'guard_get_config', 'guard_save_config', 'guard_check', 'guard_audit', 'get_audit_log',
    'guard_confirm_token', 'guard_session_trust',   # 修复 S4①：confirm-token 签发/会话信任登记
    'check_update', 'start_update_download', 'get_update_progress', 'apply_update',
    'test_provider_endpoint',
    # v1.3 MCP（10 个，同样对 get_api_info 隐身）
    'mcp_list_servers', 'mcp_save_server', 'mcp_delete_server', 'mcp_test_server',
    'mcp_get_server_detail', 'mcp_set_tool_tier', 'mcp_check_tool', 'mcp_call_tool',
    'mcp_import_claude', 'mcp_shutdown',
    # v1.5 本地模型预留接口（连接层 A + 适配层 B 判定）
    'local_probe', 'local_models',
    # v1.6 WebDAV 预留接口（数据主权；IO 为 reserved 占位）
    'webdav_get_config', 'webdav_save_config', 'webdav_test', 'webdav_export', 'webdav_restore',
    # 修复 W2（三轮）：任务开始钩子（重置后端命令去重器，与前端 per-task 生命周期对齐）
    'begin_task',
    # v1.6 沙箱（进程隔离/资源限制；配置独立文件 sandbox.json，不碰 config.json）
    'sandbox_get_config', 'sandbox_save_config', 'sandbox_status',
    # v1.6 T12 MCP resources（text 优先；blob 截断落盘；订阅存 mcp_servers.json 可选键）
    'mcp_list_resources', 'mcp_read_resource', 'mcp_save_subscriptions',
    # v1.6 HF-P0：本地 CORS 代理桥方法（file:// 页面直连不输出 CORS 头的本地
    # 模型服务器必被 Chromium 拒；前端 local 模式经此后端代理转发）
    'get_local_proxy',
    # v1.8.0 B 域·浏览器搜索（5 个；§8 两建议新增方法评审通过后追加。
    # get_api_info 零漂移同款隐身；build_tools include_agent 工具面属 C 域批次）
    'browser_search', 'browser_open', 'search_cache_stats',
    'search_status', 'browser_takeover',
    # v1.8.0 S 域·外部软件调用（3 个）+ H 域·混合路由（2 个）
    # + v1.8.5 A 域·任务授权与白名单（6 个，R5 裁决提前插）
    'software_list', 'software_probe', 'software_call',
    'hybrid_get_config', 'hybrid_save_config',
    'guard_task_grant', 'guard_task_revoke', 'guard_task_status',
    'guard_rule_list', 'guard_rule_add', 'guard_rule_remove',
})


class Api:
    def __init__(self):
        self._log = get_logger()
        paths.ensure_dirs()   # 修复 W1：目录就绪提前（原在末尾，服务初始化写文件可能先于它）
        # 公开可变属性（legacy L168-175）全部私有化，杜绝 pywebview CLR 枚举非序列化成员的崩溃面
        self._runtime = RuntimeState()
        self._config = ConfigService()
        self._workspace = WorkspaceService(self._runtime, self._config)
        self._toolcache = ToolcacheService()
        self._guard = GuardService()
        self._update = UpdateService()
        self._provider = ProviderService()
        self._files = FileService(self._runtime, self._workspace)
        self._cmds = CmdService(self._workspace, self._toolcache)
        self._clipboard = ClipboardService()
        self._process = ProcessService()
        self._screenshot = ScreenshotService()
        # v1.3 MCP：配置独立文件（不碰 config.json）；McpService 持有 config/guard/toolcache
        self._mcp_cfg = McpConfigService()
        self._mcp = McpService(self._mcp_cfg, self._guard, self._toolcache)
        # v1.5 本地模型（预留接口层：连接层 A 实现就绪 / 适配层 B 判定就绪）
        self._local = LocalModelService()
        # v1.6 HF-P0：本地 CORS 代理（file:// 页面直连不输出 CORS 头的本地服务器必失败）
        # ——Api 装配即启动（进程级单例，ensure_running 幂等）；前端经 get_local_proxy
        # 取基址，local 模式 fetch 改打代理（X-Harbor-Target 头携带真实 base_url）。
        # 启动失败不阻塞装配：前端拿不到代理基址时回落直连（行为不劣化）。
        try:
            get_proxy().ensure_running()
        except Exception as e:
            self._log.warning('本地 CORS 代理启动失败（本地端点将回落直连）: %r', e)
        # v1.6 WebDAV（预留接口层：校验与冲突判定就绪，IO 为 reserved 占位）
        self._webdav = WebDAVService()
        # v1.6 沙箱（Job Object 进程隔离 + 资源限制；fail-closed）
        self._sandbox = SandboxService()
        # v1.8.0 B 域·浏览器搜索（search_cache/ 独立目录，config.json 零污染；
        # 审计复用同一 GuardService 实例保持 audit_log.jsonl 单一口径）
        self._search = SearchService(guard=self._guard)
        # v1.8.0 S 域·外部软件调用（software.json 独立文件；审计复用同一
        # GuardService 实例；沙箱档位经 sandbox_service.limits_for_profile）
        self._software = SoftwareService(guard=self._guard, sandbox=self._sandbox,
                                         ws_root=lambda: self._workspace.effective_root(
                                             self._runtime.get_current_sid()))
        # v1.8.0 H 域·混合路由（hybrid.json 独立文件；决策 + 成本分账）
        self._hybrid = HybridRouter()
        # 修复 W6（二轮）：自更新强退（os._exit 绕过 atexit）前先关 MCP 子进程，防孤儿残留
        _update_mod.set_before_exit_hook(self._mcp.shutdown)

    def _set_window(self, win):
        """入口装配：窗口引用放 RuntimeState（legacy _RT['win']），不挂 js_api 表面。
        命名为私有：get_api_info 经 dir() 自省，公开方法集合必须与 v1.0.0 逐字一致。
        修复 S4：窗口就绪即武装护栏——此后 always/session 档在执行点强制 token/信任校验。"""
        self._runtime.win = win
        self._guard.arm()

    def clear_caches(self):
        self._files.file_fp.clear()
        # 修复 W6（三轮）：不再重置 cmd_deduper——压缩/切会话时调用本方法会把跨轮
        # 写命令去重洗白（重复 del 放行）；去重器生命周期改由 begin_task 对齐前端 per-task
        return 'ok'

    def begin_task(self):
        """修复 W2（三轮）：任务开始重置后端命令去重器——原进程级存活（仅 clear_caches
        清），跨任务「上一条」假拒绝；前端 deduper 是 per-task 预记账，两层生命周期
        经此钩子对齐。前端 runAgentLoop 起始调用（_V12_EXTRA 隐身，契约零漂移）。"""
        self._cmds.cmd_deduper.reset()
        return 'ok'

    # ============ 配置 ============
    def get_config(self):
        return self._config.get_config()

    def save_config(self, config_json):
        return self._config.save_config(config_json)

    def get_sessions(self):
        return self._config.get_sessions()

    def save_sessions(self, data):
        return self._config.save_sessions(data)

    def set_workspace(self, path):
        try:
            if os.path.isdir(path):
                self._config.cwd = path
                self._config._save_workspace()
                # 修复 ⑦（三轮）：set_workspace 不更新 recent 列表——经 api 直改目录
                # （会话绑定等路径）后 recent 不出现该目录，快捷条/面板下拉缺失
                try:
                    self._workspace.touch_recent_ws(path)
                except Exception:
                    pass
                return ok({'ok': True, 'path': self._config.cwd})
            return err(f'目录不存在: {path}')
        except Exception as e:
            return err(e)

    def get_cwd(self):
        return self._config.cwd

    def get_api_info(self):
        try:
            exe_path = sys.executable if getattr(sys, 'frozen', False) else 'python(main.py)'
        except Exception:
            exe_path = 'unknown'
        methods = sorted(n for n in dir(self)
                         if not n.startswith('_') and callable(getattr(self, n))
                         and n not in _V12_EXTRA)   # v1.2 新方法隐身：契约输出与 legacy 逐字节一致
        return ok({'version': API_VERSION, 'exe': exe_path, 'methods': methods})

    def rpc(self, name, payload_json='{}'):
        try:
            args = json.loads(payload_json or '{}')
        except Exception:
            args = {}
        if not isinstance(args, dict):
            args = {}
        name = str(name)
        func = getattr(self, name, None)
        if name == 'rpc' or name.startswith('_') and name not in _RPC_PRIVATE_OK \
                or not callable(func):
            return ok({'error': '未知方法: %s' % name})
        try:
            return func(**args)
        except Exception as e:
            return err(e)

    # ============ 文件操作 ============
    def list_dir(self, path=None):
        return self._files.list_dir(self._runtime.get_current_sid(), path)

    def read_file(self, path, offset=0, limit=800, force=False):
        return self._files.read_file(self._runtime.get_current_sid(), path, offset, limit, force)

    def write_file(self, path, content):
        return self._files.write_file(self._runtime.get_current_sid(), path, content)

    def append_file(self, path, content):
        return self._files.append_file(self._runtime.get_current_sid(), path, content)

    def search_replace(self, path, old, new, replace_all=False):
        return self._files.search_replace(self._runtime.get_current_sid(), path, old, new, replace_all)

    def make_dir(self, path):
        return self._files.make_dir(self._runtime.get_current_sid(), path)

    def delete_path(self, path, recycle=True, token=None):
        # v1.2 R2：保护名单后端强制执行（默认名单为空 → 行为与 legacy 完全一致）
        # 修复 S4①：武装后 always/session 档强制一次性 token / 会话信任
        # 修复 QA 发现：名单校验需工作区绝对路径——相对路径直接 abspath 会落到
        # 进程 CWD 使保护名单永不命中（相对路径调用下名单形同虚设）
        # 修复 W3（二轮）：护栏校验与执行复用同一次取的 sid（原两次取，
        # 会话切换 TOCTOU 会使名单与目标脱钩）
        sid = self._runtime.get_current_sid()
        abs_p, _ = self._files.resolve_abs(sid, path)
        reason = self._guard.enforce_exec('delete_path', {'path': path, 'abs_path': abs_p}, token)
        if reason:
            self._guard.audit('delete_path', {'path': path}, 'block', 'backend-enforced')
            return err(reason)
        return self._files.delete_path(sid, path, recycle)

    def move_path(self, path, new_path):
        return self._files.move_path(self._runtime.get_current_sid(), path, new_path)

    def copy_path(self, path, new_path):
        return self._files.copy_path(self._runtime.get_current_sid(), path, new_path)

    def get_file_info(self, path):
        return self._files.get_file_info(self._runtime.get_current_sid(), path)

    # ============ 命令执行 ============
    def run_command(self, cmd, timeout=60, token=None):
        # 修复 S4②：命令执行纳入护栏后端强制（默认 off 档 → 行为不变）
        reason = self._guard.enforce_exec('run_command', {'cmd': str(cmd or '')[:200]}, token)
        if reason:
            self._guard.audit('run_command', {'cmd': str(cmd or '')[:200]}, 'block', 'backend-enforced')
            return err(reason)
        return self._cmds.run_command(self._runtime.get_current_sid(), cmd, timeout,
                                      sandbox=self._sandbox.limits_for('run_command'))

    def run_powershell(self, cmd, timeout=60, token=None):
        reason = self._guard.enforce_exec('run_powershell', {'cmd': str(cmd or '')[:200]}, token)
        if reason:
            self._guard.audit('run_powershell', {'cmd': str(cmd or '')[:200]}, 'block', 'backend-enforced')
            return err(reason)
        return self._cmds.run_powershell(self._runtime.get_current_sid(), cmd, timeout,
                                         sandbox=self._sandbox.limits_for('run_powershell'))

    def run_admin_command(self, cmd, token=None, timeout=None):
        # 修复 S5/W8（三轮）：timeout 尾参接线——原签名丢 timeout（W13 二轮的「可调」
        # 是死参数），前端 150s 固定桥接超时与后端人审/轮询口径脱节（二次提权根因之一）。
        # 尾参追加保持旧调用形态 run_admin_command(cmd[, token]) 兼容。
        reason = self._guard.enforce_exec('run_admin_command', {'cmd': str(cmd or '')[:200]}, token)
        if reason:
            self._guard.audit('run_admin_command', {'cmd': str(cmd or '')[:200]}, 'block', 'backend-enforced')
            return err(reason)
        return self._cmds.run_admin_command(self._runtime.get_current_sid(), cmd, timeout)

    # ============ v1.6 沙箱（_V12_EXTRA 隐身）============
    def sandbox_get_config(self):
        """沙箱配置：开关 + 命令类别档位 + 各档限制（sandbox.json 独立存储）。"""
        return self._sandbox.get_config()

    def sandbox_save_config(self, cfg_json):
        return self._sandbox.save_config(cfg_json)

    def sandbox_status(self):
        """可用性（平台/创建能力）+ 启用态 + 进程级统计。"""
        return self._sandbox.status()

    # ============ 剪贴板 ============
    def get_clipboard(self, token=None):
        # 修复 S4②：clipboard_read 补 enforce 挂点（原完全无后端校验）
        reason = self._guard.enforce_exec('clipboard_read', {}, token)
        if reason:
            self._guard.audit('clipboard_read', {}, 'block', 'backend-enforced')
            return ok({'error': reason})
        return self._clipboard.get_clipboard()

    def set_clipboard(self, text, token=None):
        # 修复 S4②：clipboard_write 补 enforce 挂点
        detail = {'len': len(str(text if text is not None else ''))}
        reason = self._guard.enforce_exec('clipboard_write', detail, token)
        if reason:
            self._guard.audit('clipboard_write', detail, 'block', 'backend-enforced')
            return ok({'error': reason})
        return self._clipboard.set_clipboard(text)

    # ============ 进程 ============
    def list_processes(self, keyword=None):
        return self._process.list_processes(keyword)

    def kill_process(self, pid=None, name=None, token=None):
        # 修复 C1：按 pid 调用时先反查进程名，名单校验对 pid 路径同样生效
        detail = {'pid': pid if pid is not None else '', 'name': name or ''}
        if pid is not None:
            # 修复 S2：pid 非空时反查结果为权威（原仅在 name 为空时反查——伪造 name
            # 可完全架空名单：pid=<lsass>, name='notepad.exe' 即绕过）
            resolved = self._process.resolve_name_by_pid(pid)
            if resolved is None:
                # 修复 W8：反查失败武装态 fail-closed（未武装=测试/嵌入环境保持 legacy 放行，
                # 契约差分 kill_pid 用例依赖此口径）
                if self._guard.armed:
                    self._guard.audit('kill_process', detail, 'block', 'resolve-failed')
                    return ok({'error': '无法确认 pid=%s 对应的进程名（tasklist 反查失败），'
                                        '为防误杀系统进程已拒绝执行。' % pid})
            elif name and str(resolved).strip().lower() != str(name).strip().lower():
                self._guard.audit('kill_process', detail, 'block', 'name-spoofed')
                return ok({'error': 'pid=%s 实际进程名为 %s，与传入 name=%s 不一致，'
                                    '已拒绝（防伪造 name 绕过名单）' % (pid, resolved, name)})
            if resolved:
                detail['name'] = resolved
        # v1.2 R2：用户保护名单叠加在内置名单之上（默认名单为空 → 行为与 legacy 一致）
        # 修复 S4①：武装后 always/session 档强制一次性 token / 会话信任
        reason = self._guard.enforce_exec('kill_process', detail, token)
        if reason:
            self._guard.audit('kill_process', detail, 'block', 'backend-enforced')
            # 修复 ③（二轮）：原此处对含「保护名单」的文案二次追加「（保护名单）」后缀，
            # guard 理由文案已含名单说明，重复后缀删除
            return ok({'error': reason})
        return self._process.kill_process(pid, name)

    # ============ 记忆 ============
    def get_memory(self):
        return self._config.get_memory()

    def append_memory(self, entry_json):
        return self._config.append_memory(entry_json)

    def set_current_sid(self, sid):
        prev = self._runtime.get_current_sid()
        new_sid = sid or None
        self._runtime.set_current_sid(sid)
        if new_sid != prev:
            # 修复 W26：切会话清空后端会话信任态（与前端文案「本会话内不再提示」对齐）
            self._guard.clear_session_trust()
            self._mcp.clear_session_trust()
        return '{"ok":true}'

    # ============ 工作区 ============
    def set_session_ws(self, sid, path, enabled=True):
        return self._workspace.set_session_ws(sid, path, enabled)

    def list_recent_ws(self):
        return self._workspace.list_recent_ws()

    def get_session_ws(self, sid):
        return self._workspace.get_session_ws(sid)

    def get_effective_ws(self):
        return self._workspace.get_effective_ws(self._runtime.get_current_sid())

    def set_ws_enabled(self, sid, enabled):
        return self._workspace.set_ws_enabled(sid, enabled)

    def get_ws_enabled(self, sid):
        return self._workspace.get_ws_enabled(sid)

    def get_ws_state(self, sid):
        return self._workspace.get_ws_state(sid)

    def set_ws_dir(self, path):
        return self._workspace.set_ws_dir(path)

    def delete_session_ws(self, sid):
        return self._workspace.delete_session_ws(sid)

    def pick_folder(self, sid=None):
        return self._workspace.pick_folder(sid)

    def copy_into_ws(self, src, name):
        return self._workspace.copy_into_ws(self._runtime.get_current_sid(), src, name)

    def save_workspace_file(self, name, text):
        return self._workspace.save_workspace_file(self._runtime.get_current_sid(), name, text)

    def get_worklog(self):
        return self._workspace.get_worklog(self._runtime.get_current_sid())

    def append_worklog(self, text):
        return self._workspace.append_worklog(self._runtime.get_current_sid(), text)

    # ============ 系统 ============
    def open_billing(self):
        import webbrowser
        webbrowser.open('https://bigmodel.cn/usercenter/billing')
        return '{"ok":true}'

    def open_app(self, path, token=None):
        # 修复 W9（三轮）：open_app 纳入护栏（默认 off 档 → 行为不变，可在 guard.json
        # 提档加固）与命令去重（原不在护栏矩阵、无去重，模型连调 open_app('x.bat')
        # 即连开窗口——用户实测「反复打开 cmd 窗口」的弹窗面根因）
        try:
            path = str(path or '').strip()
            # 修复 H7（四轮）：unmark 回滚键必须在 path 被重写（shutil.which/join）之前固化，
            # 否则登记键（原始 path）与回滚键（重写后 path）不匹配，回滚成为 no-op。
            dkey = 'open_app ' + path
            reason = self._guard.enforce_exec('open_app', {'path': path[:200]}, token)
            if reason:
                self._guard.audit('open_app', {'path': path[:200]}, 'block', 'backend-enforced')
                return err(reason)
            tip = self._cmds.cmd_deduper.check(dkey)
            if tip:
                return ok({'info': tip, 'skipped': True})
            import re as _re
            if _re.match(r'^https?://', path):
                import webbrowser
                webbrowser.open(path)
                return ok({'ok': True, 'path': path})
            if not os.path.isabs(path):
                import shutil
                found = shutil.which(path)
                if found:
                    path = found
                else:
                    path = os.path.join(self._workspace.effective_root(self._runtime.get_current_sid()), path)
            os.startfile(path)
            return ok({'ok': True, 'path': path})
        except Exception as e:
            # 修复 W1（三轮）：打开失败回滚登记（合法重试不被去重误拦）
            try:
                self._cmds.cmd_deduper.unmark(dkey)
            except Exception:
                pass
            return err(e)

    def open_url(self, url):
        """用默认浏览器打开网页"""
        try:
            import webbrowser
            import re as _re
            u = str(url or '').strip()
            if not u:
                return err('缺少 url 参数')
            if not _re.match(r'^https?://', u):
                u = 'https://' + u
            webbrowser.open(u)
            return ok({'ok': True, 'url': u})
        except Exception as e:
            return err(e)

    def take_screenshot(self, left=None, top=None, width=None, height=None, token=None):
        # 修复 S4②：take_screenshot 补 enforce 挂点（原完全无后端校验）
        reason = self._guard.enforce_exec('take_screenshot', {}, token)
        if reason:
            self._guard.audit('take_screenshot', {}, 'block', 'backend-enforced')
            return ok({'error': reason})
        return self._screenshot.take_screenshot(left, top, width, height)

    # ============ toolcache ============
    def cache_tool_output(self, content):
        cid = self._toolcache.cache(content)
        if not cid:
            return ok({'ok': False, 'error': '落盘失败'})
        return ok({'ok': True, 'id': cid})

    def read_more(self, cache_id, offset=0, limit=400):
        return self._toolcache.read_more(cache_id, offset, limit)

    # ============ system prompt ============
    def build_system_prompt(self):
        sid = self._runtime.get_current_sid()
        # 修复（2026-10-18）：工作区关闭时不得注入路径/宣称文件能力——原先无条件注入
        # effective_root，导致快捷条显示「未启用工作区」但 AI 仍答「当前工作区: C:\...」
        # 并声称能操作文件夹（工具被裁了，模型却以为有）。
        # 实现 v1.6 T5①：沙箱边界告知段（防 Agent 误判「沙箱=绝对安全」）。
        # 注：本方法在契约 INTENTIONAL_DELTAS 白名单内（v1.1.1 省 token 先例 +
        # v1.6 T5 沙箱段增量），允许与 legacy 不同；单独断言结构而非逐字节。
        sandbox_notice = ''
        try:
            sandbox_notice = self._sandbox.prompt_notice() or ''
        except Exception:
            sandbox_notice = ''
        tail = ('\n' + sandbox_notice) if sandbox_notice else ''
        if not self._runtime.ws_enabled_for(sid, True):
            return ok(
                '你是 Harbor 内置编程助手。当前**未启用工作区**：不要假设或猜测任何工作区路径，'
                '不要主动列出/创建/修改文件或文件夹；用户要求文件/文件夹操作时，'
                '先请其打开输入框上方的「工作区」快捷条启用工作区。\n'
                '硬规则:\n'
                '1. 文件操作只用工具, 禁止用 Get-Content/Set-Content(后端已强制 UTF-8)。\n'
                '2. 写文件串行: 一次一个 write_file/append_file/search_replace, 等返回成功再写下一个。\n'
                '3. 超长命令输出会截断并给缓存 id, 需要全文用 read_more 分段取。' + tail)
        root = self._workspace.effective_root(sid)
        # v1.1.1 省 token：删掉与工具 description 重复的「系统能力」段（每轮省 ~130 字）
        return ok(
            '你是 Harbor 内置编程助手。当前工作区: ' + root + '\n'
            '硬规则:\n'
            '1. 文件操作只用工具, 禁止用 Get-Content/Set-Content(后端已强制 UTF-8)。\n'
            '2. 写文件串行: 一次一个 write_file/append_file/search_replace, 等返回成功再写下一个。\n'
            '3. 超长命令输出会截断并给缓存 id, 需要全文用 read_more 分段取。' + tail)

    # ============ 工具 schema（唯一数据源 tools_schema.py）============
    def build_tools(self, role='full', include_mcp=False, include_agent=False,
                    is_glm_endpoint=False):
        """v1.3：include_mcp=True 且 role='full' 时尾部追加 MCP 工具定义；
        默认路径（include_mcp=False）输出与 legacy 逐字节一致（契约红线）。

        v1.8.0 C 域：include_agent=True 且 role='full' 时尾部追加 Agent
        工具族（browser_search/browser_open/software_call）。R11 裁决
        （端点过滤）：is_glm_endpoint=True 时 browser_* 定义不进工具集
        （GLM 端点只出现前端追加的内置 web_search，两个搜索工具永不并存）；
        非 GLM 全量追加。include_agent=False 默认路径逐字节不变。
        """
        ws_on = self._runtime.ws_enabled_for(self._runtime.get_current_sid(), True)
        mcp_tools = None
        if include_mcp and role == 'full':
            mcp_tools = self._mcp.tool_schemas()
        return tools_schema.build(role, ws_on, mcp_tools,
                                  include_agent=include_agent,
                                  is_glm_endpoint=bool(is_glm_endpoint))

    # ============ v1.2 安全护栏（R2，_V12_EXTRA 隐身）============
    def guard_get_config(self):
        """护栏配置：三档矩阵 + 保护名单（guard.json 独立存储，不碰 config.json 契约）。"""
        return self._guard.get_config()

    def guard_save_config(self, cfg_json):
        return self._guard.save_config(cfg_json)

    def guard_check(self, op, detail_json='{}'):
        """三档判定：返回 {action: allow/confirm/block, reason?}。前端据 action 弹确认框或阻断。"""
        try:
            detail = json.loads(detail_json or '{}')
            if not isinstance(detail, dict):
                detail = {}
        except Exception:
            detail = {}
        r = self._guard.check(op, detail)
        self._guard.audit(op, detail, r.get('action', 'check'))
        return ok(r)

    def guard_audit(self, op, detail_json='{}', decision='allow'):
        """前端上报用户决策（allow/deny/session-trust），落审计日志。"""
        try:
            detail = json.loads(detail_json or '{}')
            if not isinstance(detail, dict):
                detail = {}
        except Exception:
            detail = {}
        return self._guard.audit(op, detail, 'decision', decision)

    def get_audit_log(self, limit=200, offset=0):
        """审计日志查看器数据源：倒序返回最新 limit 条（纯本地文件，无网络）。"""
        return self._guard.read_audit(limit, offset)

    def guard_confirm_token(self, op, detail_json='{}'):
        """修复 S4①：前端确认框「允许」后换取一次性 confirm token（TTL 60s，绑定 op+detail 摘要）。
        携带该 token 调实际 op 才能通过武装后的后端强制执行点。"""
        try:
            detail = json.loads(detail_json or '{}')
            if not isinstance(detail, dict):
                detail = {}
        except Exception:
            detail = {}
        r = self._guard.issue_confirm_token(op, detail)
        if r.get('error'):
            return err(r['error'])
        return ok(r)

    def guard_session_trust(self, op):
        """修复 S4①：登记本会话信任（对应确认框「本会话内不再提示」勾选；切会话自动清空）。"""
        r = self._guard.trust_session(op)
        if r.get('error'):
            return err(r['error'])
        return ok(r)

    # ============ v1.2 自动更新（R1，_V12_EXTRA 隐身）============
    def check_update(self, manifest_url=None):
        return self._update.check(manifest_url)

    def start_update_download(self, url, sha256, version=None):
        return self._update.start_download(url, sha256, version)

    def get_update_progress(self):
        return self._update.get_progress()

    def apply_update(self):
        return self._update.apply()

    # ============ v1.2 多模型（R6，_V12_EXTRA 隐身）============
    def test_provider_endpoint(self, base_url, api_key, model, timeout=15, local=False):
        """OpenAI 兼容端点连通性测试（后端 urllib，规避前端跨域）。

        v1.5：local=True 时走本地分支（免 Key 校验 / 超时默认 30s /
        503 冷启动识别为 loading 态而非失败）——roadmap A5：复用本通道，
        不新建测试通道。"""
        if local:
            return ok(self._local.test_local_endpoint(
                base_url, model, timeout=timeout or 30))
        return self._provider.test_endpoint(base_url, api_key, model, timeout=timeout)

    # ============ v1.5 本地模型（预留接口，_V12_EXTRA 隐身）============
    def local_probe(self, ports=None):
        """A2：本地服务器并行探测（11434/1234/8000/8080，各 2s 超时）。

        返回 {ok, reachable:[{base_url,kind,models,latency_ms}], unreachable, elapsed_ms}。
        ports 可传 JSON 数组字符串（如 '[11434,1234]'）或 None（默认四端口）。
        """
        port_list = None
        if ports:
            try:
                port_list = json.loads(ports) if isinstance(ports, str) else list(ports)
            except Exception:
                return err('ports 需要是 JSON 数组，如 [11434,1234]')
        return ok(self._local.probe(ports=port_list))

    def local_models(self, base_url, api_key=''):
        """A3：补拉模型清单（探测过期时用）。

        api_key 可选（v4「连接与模型」单端点合并）：非空时请求带
        `Authorization: Bearer {key}` —— 云端 OpenAI 兼容端点（DeepSeek/Moonshot/
        通义…）的 /models 清单需鉴权；本地服务器免 Key，单参调用行为不变。

        返回 {ok, base_url, models:[{id, ctx_window, tool_capable, estimated}]}。"""
        return ok(self._local.models(base_url, api_key=api_key))

    # ============ v1.6 HF-P0 本地 CORS 代理（_V12_EXTRA 隐身）============
    def get_local_proxy(self):
        """HF-P0：本地 CORS 代理基址——前端 local 模式 fetch 改打代理，
        X-Harbor-Target 请求头携带真实本地 base_url，代理仅转发回环目标
        （安全硬约束：非回环 403，防开放中继）并补齐 CORS 头 + 流式透传。

        返回 {ok, port, base_url}（base_url = http://127.0.0.1:<port>）；
        端口随机（127.0.0.1:0），Api 装配时已启动（幂等单例）。
        """
        return ok(get_proxy().info())

    # ============ v1.8.0 B 域·浏览器搜索（_V12_EXTRA 隐身）============
    def browser_search(self, params=None):
        """B1：浏览器搜索——检索式构造 → 缓存层（TTL 30min）→ 双通道取数
        （次窗优先/urllib 兜底）→ 解析提取 → 校验缓存 → 审计（op=web_search）。

        请求字段/成功响应/错误码见联调规范 §3.1；检出验证页 fail-fast 返回
        CAPTCHA_REQUIRED（error.takeover_id 交前端 63-search-panel 接管 UI，
        流程 2）。params 可为 dict 或 JSON 字符串（service 层归一）。
        """
        return ok(self._search.browser_search(params))

    def browser_open(self, params=None):
        """B2：打开 URL 提取正文（selector 覆盖/密度提取；超长截断落 toolcache，
        full_ref 经 read_more 续读）。审计 op=web_open；契约 §3.1。"""
        return ok(self._search.browser_open(params))

    def search_cache_stats(self):
        """B3：搜索缓存统计 {entries, hits, misses, ttl_minutes, size_kb}。
        读取类不落审计（面板脚注/设置区刷新，同 refreshWsCard 模式）。"""
        return ok(self._search.search_cache_stats())

    def search_status(self, task_id=''):
        """B4：搜索进度回报通道（面板 1s 轮询，规范 §2.4 方案 A）。
        task_id 缺省 = 当前活跃搜索；传入时校验归属（任务 id 或 takeover_id）。
        读取类不落审计（1s 轮询不灌爆审计文件）。"""
        return ok(self._search.search_status(str(task_id or '') or None))

    def browser_takeover(self, takeover_id, action):
        """B5：人工接管续跑/放弃（ux-flows 流程 2 步骤 4a/4b）。
        continue = 复检通过后续跑原管线，返回与 browser_search 同构的成功
        载荷（resumed:true）；仍验证页 → CAPTCHA_REQUIRED（retry ≤3）；
        abort → CAPTCHA_ABORTED。审计 op=search_takeover。"""
        return ok(self._search.browser_takeover(takeover_id, action))

    # ============ v1.8.0 S 域·外部软件调用（实现 v1.8.0 S1，_V12_EXTRA 隐身）============
    def software_list(self, status='all'):
        """S1：外部软件注册表列表（status=all|probed|missing；读取类不落审计）。
        响应 {ok, software:[{name, kind, status, version?, source,
        risk_default, actions:[{name, risk, arg_schema}]}]}——联调规范 §3.2。"""
        return ok(self._software.software_list(status))

    def software_probe(self, name=None):
        """S2：探测（PATH 扫描 + winreg 补探测 + --version 验身份）。
        缺省全部；name 未注册 → BAD_PARAMS（hint 回显可用名）。
        审计 op=software_probe。"""
        return ok(self._software.software_probe(name))

    def software_call(self, params=None):
        """S3：外部软件调用三形态（CLI 沙箱执行 / GUI 标题核验 / URI 协议）。
        参数按 action.arg_schema 硬校验（SCHEMA_INVALID + violations/example
        自校正回显）；exit_code≠0 仍走成功形状。审计 op=software_call。
        params 可为 dict 或 JSON 字符串（service 层归一）。"""
        return ok(self._software.software_call(params))

    def _software_save(self, name, entry=None):
        """S 域用户自定义条目 CRUD 之写（私有：经 rpc 通用分发通道暴露——
        契约方法面恰为 software×3（联调规范 §1.2），故不进 _V12_EXTRA、
        也不进 get_api_info 自省面）。entry 为 dict 或 JSON 字符串。"""
        if isinstance(entry, str):
            try:
                entry = json.loads(entry or '{}')
            except Exception as e:
                return err('条目解析失败: %s' % e)
        r = self._software.save(name, entry or {})
        if r.get('error'):
            return err(r['error'])
        return ok(r)

    def _software_remove(self, name):
        """S 域用户自定义条目 CRUD 之删（私有，经 rpc 暴露；预设不可删）。"""
        r = self._software.remove(name)
        if r.get('error'):
            return err(r['error'])
        return ok(r)

    # ============ v1.8.0 H 域·混合路由（实现 v1.8.0 H1，_V12_EXTRA 隐身）============
    def hybrid_get_config(self):
        """H1：读混合路由配置（hybrid.json 独立文件；缺失/损坏返回默认 +
        source=default——首启零配置可用，不报错）。读取类不落审计。"""
        return ok(self._hybrid.get_config())

    def hybrid_save_config(self, cfg_json):
        """H2：保存混合路由配置（部分更新语义；字段级校验失败 → BAD_PARAMS，
        hint 指明字段与合法域）。审计 op=hybrid_save_config。"""
        r = self._hybrid.save_config(cfg_json)
        if r.get('error'):
            field = r.get('field')
            hint = ('字段 %s 合法域：strategy auto|saver|quality；'
                    'local_budget_understand_s/local_budget_validate_s 1-30；'
                    'confidence_gate 0.5-0.95；cost_split_display true/false'
                    % field if field else None)
            e = {'code': 'BAD_PARAMS', 'message': r['error']}
            if hint:
                e['hint'] = hint
            return ok({'ok': False, 'error': e})
        return ok(r)

    # ============ v1.8.5 A 域·任务授权与白名单（实现 v1.8.0 A1，R5 裁决提前插；_V12_EXTRA 隐身）============
    def guard_task_grant(self, scope, ttl_seconds=7200):
        """A1：任务授权（进程内状态，不入 guard.json；TTL 默认 7200s（2h 上限
        口径）+ 空闲 30min 自动收回，先到者生效）。scope 枚举数组；
        ttl 60-86400，越界 → BAD_PARAMS（安全参数不静默夹逼）。"""
        r = self._guard.task_grant(scope, ttl_seconds)
        if r.get('error'):
            return err(r['error'])
        return ok(r)

    def guard_task_revoke(self, grant_id=None):
        """A2：收回授权（缺省=当前；幂等）。审计 op=guard_revoke。"""
        r = self._guard.task_revoke(grant_id)
        if r.get('error'):
            return err(r['error'])
        return ok(r)

    def guard_task_status(self):
        """A3：授权状态（#grantIndicator 倒计时校准源；含 idle_deadline 与
        remaining_s=min(expires_at,idle_deadline)-now，剩余 <600s 黄牌）。
        读取类不落审计。"""
        r = self._guard.task_status()
        if r.get('error'):
            return err(r['error'])
        return ok(r)

    def guard_rule_list(self):
        """A4：白名单规则列表（读取类不落审计）。"""
        r = self._guard.rule_list()
        if r.get('error'):
            return err(r['error'])
        return ok(r)

    def guard_rule_add(self, op_pattern, detail_pattern=None, note=None):
        """A5：添加白名单规则（窄规则优先；deny 清单覆盖的创建即拒 →
        GUARD_DENIED；detail 含写动词 → warn 不阻断）。"""
        r = self._guard.rule_add(op_pattern, detail_pattern, note)
        if r.get('error'):
            return err(r['error'])
        return ok(r)

    def guard_rule_remove(self, rule_id):
        """A6：删除白名单规则（幂等；删除即时生效）。"""
        r = self._guard.rule_remove(rule_id)
        if r.get('error'):
            return err(r['error'])
        return ok(r)

    # ============ v1.6 WebDAV 数据主权（预留接口，_V12_EXTRA 隐身）============
    def webdav_get_config(self):
        """[预留] 读取 WebDAV 配置（webdav.json，DPAPI 解密 password）。"""
        return ok(self._webdav.get_config())

    def webdav_save_config(self, cfg_json):
        """[预留] 保存 WebDAV 配置（校验通过；落盘执行器 v1.6 正式版）。"""
        return ok(self._webdav.save_config(cfg_json))

    def webdav_test(self, cfg_json='{}'):
        """[预留] WebDAV 连通性测试（PROPFIND）。"""
        return ok(self._webdav.test(cfg_json))

    def webdav_export(self):
        """导出备份（config+sessions+audit → MKCOL/PUT/manifest；用已存配置）。"""
        return ok(self._webdav.export('{}'))

    def webdav_restore(self, payload_json):
        """从备份恢复（下载 + sha256 对拍 + 三方冲突裁决 + 按策略落盘；用已存配置）。"""
        return ok(self._webdav.restore(payload_json, '{}'))

    # ============ v1.3 MCP（R1-R6，_V12_EXTRA 隐身）============
    @staticmethod
    def _mcp_parse_args(arguments_json):
        """arguments_json → dict（非法 JSON 按空对象，不抛）。"""
        try:
            args = json.loads(arguments_json or '{}')
        except Exception:
            args = {}
        return args if isinstance(args, dict) else {}

    def mcp_list_servers(self):
        """服务器列表（状态灯/工具数/开关数据源）。"""
        return ok({'ok': True, 'servers': self._mcp.list_servers()})

    def mcp_save_server(self, name, config_json):
        """保存服务器配置。enabled=true 时：结构校验 → DPAPI 加密 → 预检测 → 测试连接，
        任一步失败返回 {error: 人话} 且 enabled 不落盘（开关回弹由前端呈现）。"""
        try:
            cfg = json.loads(config_json or '{}')
        except Exception as e:
            return err('配置解析失败: %s' % e)
        if not isinstance(cfg, dict):
            return err('配置必须是 JSON 对象')
        name = str(name or '').strip()
        if not name:
            return err('服务器名称不能为空')
        want_enable = bool(cfg.get('enabled'))
        r = self._mcp.save_server(name, cfg, activate=want_enable)
        if r.get('error'):
            return err(r['error'])
        if not want_enable:
            return ok({'ok': True, 'name': name})
        t = self._mcp.test_server(name)
        if t.get('error'):
            # 测试连接失败 → 回弹 enabled=false（配置已保存，保持停用）
            revert = dict(cfg)
            revert['enabled'] = False
            self._mcp.save_server(name, revert, activate=False)
            return err(t['error'])
        return ok({'ok': True, 'name': name, 'tools': t.get('tools') or []})

    def mcp_delete_server(self, name):
        r = self._mcp_cfg.delete_server(name)
        if r.get('error'):
            return err(r['error'])
        self._mcp.forget(name)
        return ok({'ok': True})

    def mcp_test_server(self, name):
        r = self._mcp.test_server(name)
        if r.get('error'):
            return err(r['error'])
        return ok(r)

    def mcp_get_server_detail(self, name):
        r = self._mcp.get_server_detail(name)
        if r.get('error'):
            return err(r['error'])
        return ok(r)

    def mcp_set_tool_tier(self, server, tool, tier):
        r = self._mcp_cfg.set_tool_tier(server, tool, tier)
        if r.get('error'):
            return err(r['error'])
        return ok({'ok': True})

    def mcp_check_tool(self, server, tool, arguments_json='{}'):
        """护栏定档：{action: allow/confirm/block, tier, tier_source, reason?}；落审计 check。"""
        return ok(self._mcp.check_tool(server, tool, self._mcp_parse_args(arguments_json)))

    def mcp_call_tool(self, server, tool, arguments_json='{}', decision='deny', token=None):
        """执行 MCP 工具（decision 默认 deny；后端二次 enforce + 审计）。
        返回 {ok, output} / {error} / {info, skipped}（用户拒绝/不可用拦截）。
        语义：'deny'=用户拒绝；''/未知=缺失（按 §3.5 矩阵走 enforce 拒绝）。
        修复 S4①：武装后 always/session 档还须一次性 token 或后端会话信任。"""
        r = self._mcp.call_tool(server, tool, self._mcp_parse_args(arguments_json),
                                decision if decision is not None else 'deny', token=token)
        if r.get('skipped'):
            return ok({'info': r.get('info') or '', 'skipped': True})
        if r.get('error') is not None:
            return err(r['error'])
        return ok({'ok': True, 'output': r.get('output') or ''})

    def mcp_import_claude(self, config_json):
        """导入 claude_desktop_config.json：{ok, imported, skipped:[{name, reason}], total}。"""
        r = self._mcp_cfg.import_claude(config_json)
        if r.get('error'):
            return err(r['error'])
        return ok(r)

    def mcp_shutdown(self):
        """关停全部 MCP 传输（main.py atexit 注册 + 测试用）。"""
        return ok(self._mcp.shutdown())

    # ---- v1.6 T12 MCP resources（text 优先；blob 截断落盘；订阅持久化）----
    def mcp_list_resources(self, server):
        """resources/list：{ok, resources:[{uri,name,mimeType,...}], supported}。
        服务器不支持资源（-32601）→ supported=False + 空列表（不算错误）。"""
        r = self._mcp.list_resources(server)
        if r.get('error'):
            return err(r['error'])
        return ok({'ok': True, 'resources': r.get('resources') or [],
                   'supported': r.get('supported', True)})

    def mcp_read_resource(self, server, uri):
        """resources/read：text 类直接返回文本；blob 类落盘 toolcache 并给
        cache_id（read_more 分段取）。全程审计（op=mcp_resource）。"""
        r = self._mcp.read_resource(server, uri)
        if r.get('error'):
            return err(r['error'])
        return ok(r)

    def mcp_save_subscriptions(self, server, uris_json='[]'):
        """保存资源订阅（mcp_servers.json 新可选键 resourceSubs；Claude 兼容忽略）。"""
        r = self._mcp.save_subscriptions(server, uris_json)
        if r.get('error'):
            return err(r['error'])
        return ok(r)
