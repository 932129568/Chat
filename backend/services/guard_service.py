# -*- coding: utf-8 -*-
"""安全护栏服务（v1.2 R2 + 修复 S4 + 实现 v1.8.0 A1：v1.8.5 A 域任务授权/白名单）。

设计（PRD §7.1 + 架构 §3.4）：
- 确认矩阵：delete_path / kill_process / clipboard_write / clipboard_read /
  take_screenshot 五个操作三档可配；修复 S4 起追加 run_command /
  run_powershell / run_admin_command 三个命令执行 op（默认 'off'，用户可在
  guard.json 中提档加固）：
    'always'  每次确认
    'list'    保护名单（命中名单 → 阻断；未命中 → 放行）
    'session' 会话内首次确认，之后放行（会话信任态后端持有，切会话清空）
- 保护名单：路径通配（fnmatch，支持 C:\\Users\\*\\Documents\\** 形式，大小写不敏感）
  + 进程名名单（叠加内置关键进程名单，默认非空——修复 S4③）。
- 后端强制（修复 S4①②）：桌面 UI 会话激活（Api._set_window 武装）后，
  always 档要求一次性 confirm token（带 TTL、绑定 op+detail 摘要、用后销毁）；
  session 档要求 token 或本会话已信任；off/list 放行；名单 block 无条件拦截。
  未武装（无窗口的测试/嵌入环境）保持 legacy 行为：只做名单 block。
- 审计日志：~/.glm-chat/audit_log.jsonl 追加式记录每次判定与用户决策（10MB 轮转，修复 W12）。

v1.8.5 A 域（任务授权 + 白名单，R5/R6 裁决）：
- **判定链**（新增维度插入，旧三档语义零迁移）：deny 清单 → allow_rules
  白名单 → task_grant 任务授权 → op 档 → 弹窗。旧 guard.json 无新键时
  行为 = 现行为（测试锁定）；
- **任务授权 grant**（进程内状态，**不入 guard.json**）：scope 枚举数组 +
  TTL（默认 7200s，60-86400）+ **空闲 30min（1800s）自动收回**（R6：
  grant 内操作刷新空闲计时，TTL 与空闲先到者生效）；授权内放行审计
  decision=grant（不逐条 toast）；deny 清单先于 grant 生效（授权不是免检）；
- **allow_rules 白名单**（guard.json 新增键，用户显式创建才写）：op/detail
  正则窄规则优先；deny 清单覆盖的规则创建即拒；命中审计 decision=rule。

存储：独立文件 guard.json（不碰 config.json——契约差分测试对 config.json 内容逐字节比对）。
"""
import datetime
import fnmatch
import json
import os
import re
import secrets
import threading
import time
from collections import deque

from .. import paths
from ..fio import atomic_write_json
from ..logging_setup import get_logger

GUARD_FILE = os.path.join(paths.CONFIG_DIR, 'guard.json')
AUDIT_LOG = os.path.join(paths.CONFIG_DIR, 'audit_log.jsonl')
AUDIT_MAX_BYTES = 10 * 1024 * 1024     # 修复 W12：审计日志 10MB 轮转
TOKEN_TTL = 60                         # confirm token 一次性有效时长（秒）

# 操作清单与默认档位（PRD Q3 平衡：破坏性最高的默认每次确认；被动/低危的默认会话内首次确认）
GUARD_OPS = ('delete_path', 'kill_process', 'clipboard_write', 'clipboard_read',
             'take_screenshot', 'run_command', 'run_powershell', 'run_admin_command',
             'open_app',
             # v1.8.0 §3.3 护栏与隐私：浏览器搜索默认 session 档（会话首次确认）；
             # 外部软件调用默认 session 档（§4.4：read/mutate 会话首次，dangerous
             # 由 preset risk 在 software_service 侧强制 always）
             'web_search', 'software_call')
DEFAULT_TIERS = {
    'delete_path': 'always',
    'kill_process': 'always',
    'clipboard_write': 'always',
    'clipboard_read': 'session',
    'take_screenshot': 'session',
    # 修复 S4：命令执行三 op 纳入矩阵；默认 off 保持既有行为零变化，用户可提档加固
    'run_command': 'off',
    'run_powershell': 'off',
    'run_admin_command': 'off',
    'open_app': 'off',   # 修复 W9（三轮）：默认 off 保持既有行为，提档后弹窗/ token 生效
    'web_search': 'session',      # v1.8.0 §3.3：浏览器搜索默认 session 档
    'software_call': 'session',   # v1.8.0 §4.4：软件调用默认 session 档
}

# ---- v1.8.5 A 域：任务授权 grant（进程内状态，不入 guard.json）----
GRANT_SCOPES = ('workspace_write', 'exec', 'app_launch')   # scope 枚举（§3.4）
GRANT_TTL_DEFAULT = 7200            # R6：默认 2h
GRANT_TTL_MIN, GRANT_TTL_MAX = 60, 86400
GRANT_IDLE_SECONDS = 1800           # R6：空闲 30min 自动收回
GRANT_EXPIRING_SOON_S = 600         # 剩余 <600s → expiring_soon 黄牌（§8.3）
# op → grant scope 映射（授权覆盖判定：scope 覆盖的 op 授权内放行）
_OP_GRANT_SCOPES = {
    'delete_path': 'workspace_write',
    'run_command': 'exec',
    'run_powershell': 'exec',
    'run_admin_command': 'exec',
    'open_app': 'app_launch',
}
# allow_rules 宽模式告警词（detail 含写动词 → warn，不阻断——架构 §3.4）
_RULE_WRITE_VERBS = ('del', 'delete', 'remove', 'rm', 'erase', 'move', 'copy',
                     'write', 'kill', 'format', 'mkfs', 'reg', 'regedit',
                     'setx', 'taskkill', 'stop-process', 'start-process',
                     'iex', 'invoke-expression', 'rd', 'rmdir', 'mkdir', 'md',
                     'new-item', 'ni', 'ri', 'cp', 'mv', 'remove-item')
# deny 语义最强的 op（白名单规则不得架空其保护名单）
_DENY_SENSITIVE_OPS = ('delete_path', 'kill_process')

# 无保护名单意义的操作：'list' 档对它们语义等同 off 是误导（W10），后端降级为每次确认
_LISTLESS_OPS = {'clipboard_write', 'clipboard_read', 'take_screenshot',
                 'run_command', 'run_powershell', 'run_admin_command',
                 'open_app'}   # 修复 W9（三轮）：open_app 无名单语义

# kill_process 内置保护（叠加用户名单；与 process_service.PROTECTED_NAMES 保持一致但独立声明，
# 避免 service 间反向依赖）。修复 S4③：内置关键进程名单默认非空。
_BUILTIN_PROTECTED_PROCESSES = {
    'system', 'system idle process', 'idle',
    'smss.exe', 'csrss.exe', 'wininit.exe', 'winlogon.exe',
    'services.exe', 'lsass.exe', 'svchost.exe', 'explorer.exe',
    'dwm.exe', 'sihost.exe', 'taskhostw.exe', 'ctfmon.exe',
}

OP_LABELS = {
    'delete_path': '删除文件/目录',
    'kill_process': '结束进程',
    'clipboard_write': '写入剪贴板',
    'clipboard_read': '读取剪贴板',
    'take_screenshot': '屏幕截图',
    'run_command': '执行命令',
    'run_powershell': '执行 PowerShell',
    'run_admin_command': '管理员命令',
    'open_app': '打开应用/链接',   # 修复 W9（三轮）
}

# token 可签发的操作集合（mcp_call 由 McpService 在 call_tool 校验）
_TOKEN_OPS = set(GUARD_OPS) | {'mcp_call'}


def _default_config():
    return {
        'tiers': dict(DEFAULT_TIERS),
        'protect_paths': [],
        'protect_processes': [],
        'trustedOps': [],          # 修复 UX-2（v1.4）：持久信任 op 列表（grill 裁决：op 级粒度）
    }


def _norm_pattern(p):
    """修复 W11：名单 pattern 入库统一 normcase+normpath，写法差异不再静默失效。"""
    return os.path.normcase(os.path.normpath(str(p).strip()))


class GuardService:
    def __init__(self, guard_path=None, audit_path=None, clock=None):
        self._log = get_logger()
        self._lock = threading.RLock()
        self._path = guard_path or GUARD_FILE
        self._audit_path = audit_path or AUDIT_LOG
        self._cfg = self._load()
        # 修复 S4①：进程内信任态（一次性 token + 会话信任 + 武装标志）
        self._tokens = {}              # token -> (op, detail_digest, expiry_ts)
        self._session_trust = set()    # 本会话已信任的 op（切会话清空，W26 同步语义）
        # W1：trace_id 钩子（Api 装配注入；None=审计不带 trace，向后兼容）
        self._trace_hook = None
        self._armed = False            # 桌面 UI 会话武装标志（Api._set_window 置位）
        # v1.8.5 A 域：任务授权 grant 进程内状态（不入 guard.json——铁律）
        self._clock = clock or time.time
        self._grants = {}              # grant_id -> grant dict
        self._current_grant_id = None

    # ---- 武装状态 ----
    def arm(self):
        """桌面 UI 会话激活标记：此后 always/session 档在执行点强制 token/信任校验。"""
        self._armed = True

    @property
    def armed(self):
        return self._armed

    # ---- 配置读写 ----
    def _load(self):
        cfg = _default_config()
        try:
            with open(self._path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                tiers = data.get('tiers')
                if isinstance(tiers, dict):
                    for k in GUARD_OPS:
                        v = tiers.get(k)
                        if v in ('always', 'list', 'session', 'off'):
                            cfg['tiers'][k] = v
                if isinstance(data.get('protect_paths'), list):
                    cfg['protect_paths'] = [_norm_pattern(p) for p in data['protect_paths']
                                            if str(p).strip()]
                if isinstance(data.get('protect_processes'), list):
                    cfg['protect_processes'] = [str(p).lower().strip() for p in data['protect_processes']
                                                if str(p).strip()]
                # 修复 UX-2（v1.4）：持久信任加载——白名单过滤未知 op
                if isinstance(data.get('trustedOps'), list):
                    cfg['trustedOps'] = [str(op) for op in data['trustedOps'] if str(op) in GUARD_OPS]
                # v1.8.5 A 域：allow_rules 白名单加载（旧配置无此键 → 不写入默认，
                # 行为与现行为逐字节一致——「用户显式创建才写」）
                rules = data.get('allow_rules')
                if isinstance(rules, list):
                    for r in rules:
                        norm = self._norm_rule(r)
                        if norm is not None:
                            cfg.setdefault('allow_rules', []).append(norm)
        except FileNotFoundError:
            pass
        except Exception as e:
            self._log.warning('护栏配置加载失败，按默认档位处理: %r', e)
        return cfg

    def get_config(self):
        with self._lock:
            return json.dumps(self._cfg, ensure_ascii=False)

    def save_config(self, cfg_json):
        try:
            incoming = json.loads(cfg_json) if isinstance(cfg_json, str) else cfg_json
            if not isinstance(incoming, dict):
                incoming = {}
            with self._lock:
                tiers = incoming.get('tiers')
                if isinstance(tiers, dict):
                    for k in GUARD_OPS:
                        v = tiers.get(k)
                        if v in ('always', 'list', 'session', 'off'):
                            self._cfg['tiers'][k] = v
                if isinstance(incoming.get('protect_paths'), list):
                    self._cfg['protect_paths'] = [_norm_pattern(p) for p in incoming['protect_paths']
                                                  if str(p).strip()]
                if isinstance(incoming.get('protect_processes'), list):
                    self._cfg['protect_processes'] = [str(p).lower().strip()
                                                      for p in incoming['protect_processes'] if str(p).strip()]
                # 修复 UX-2（v1.4）：持久信任读写（op 级；未知 op 拒绝）
                trusted = incoming.get('trustedOps')
                if trusted is not None:
                    if not isinstance(trusted, list):
                        return json.dumps({'error': 'trustedOps 必须是数组'}, ensure_ascii=False)
                    for op in trusted:
                        if str(op) not in GUARD_OPS:
                            return json.dumps({'error': '未知的信任操作: %s' % op}, ensure_ascii=False)
                    self._cfg['trustedOps'] = [str(op) for op in trusted]
                self._write_cfg_locked()   # 修复 S8：原子写
            return '{"ok":true}'
        except Exception as e:
            self._log.exception('护栏配置保存失败')
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def _write_cfg_locked(self):
        """guard.json 原子落盘（调用方持锁；allow_rules 键随 _cfg 整体保留）。"""
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        atomic_write_json(self._path, self._cfg, indent=2)

    @staticmethod
    def _norm_rule(raw):
        """allow_rules 单条归一（加载时过滤非法项：缺 id/pattern 或正则非法 → 跳过）。"""
        if not isinstance(raw, dict):
            return None
        rid = str(raw.get('rule_id') or '').strip()
        op_p = str(raw.get('op_pattern') or '').strip()
        if not rid or not op_p:
            return None
        try:
            re.compile(op_p)
        except re.error:
            return None
        d_p = str(raw.get('detail_pattern') or '').strip()
        if d_p:
            try:
                re.compile(d_p)
            except re.error:
                d_p = ''
        rule = {'rule_id': rid, 'op_pattern': op_p}
        if d_p:
            rule['detail_pattern'] = d_p
        try:
            rule['hits'] = max(0, int(raw.get('hits') or 0))
        except (TypeError, ValueError):
            rule['hits'] = 0
        rule['created_at'] = str(raw.get('created_at') or '')
        note = str(raw.get('note') or '').strip()[:200]
        if note:
            rule['note'] = note
        return rule

    # ---- 保护名单匹配 ----
    def _path_protected(self, path):
        raw = str(path or '').strip()
        if not raw:
            return None   # 修复 W11：空 path 不再 abspath('') 落到 CWD 误伤
        p = os.path.normcase(os.path.realpath(os.path.abspath(raw)))
        with self._lock:
            patterns = list(self._cfg['protect_paths'])
        for pat in patterns:
            if fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(p, pat + os.sep + '*'):
                return pat
        return None

    def _process_protected(self, name):
        n = str(name or '').strip().lower()
        if not n:
            return None
        with self._lock:
            user_list = list(self._cfg['protect_processes'])
        if n in _BUILTIN_PROTECTED_PROCESSES:
            return n
        if n in user_list:
            return n
        for pat in user_list:
            if fnmatch.fnmatch(n, pat):
                return pat
        return None

    # ---- 三档判定 ----
    def check(self, op, detail=None):
        """返回 dict：{action: 'allow'|'confirm'|'block', reason?, via?, ...}。

        v1.8.5 A 域判定链（新增维度插入，旧三档语义零迁移——旧 guard.json
        无新键时走法与原实现逐字节等价）：
        ① deny：保护名单 block（无条件，含授权内——授权不是免检）；
        ② allow_rules：白名单窄规则命中 → allow（via=rule）；
        ③ task_grant：活跃授权覆盖该 op 的 scope → allow（via=grant，
           同时刷新空闲计时 R6）；
        ④ op 档：持久信任 → allow；off → allow；list → allow/confirm；
        ⑤ always/session → confirm（弹窗）。
        """
        detail = detail or {}
        if op not in GUARD_OPS:
            return {'action': 'allow'}
        with self._lock:
            tier = self._cfg['tiers'].get(op, DEFAULT_TIERS.get(op, 'always'))

        # ① 保护名单优先于一切（名单命中 = 无条件阻断；deny 先于 grant/rules）
        if op == 'delete_path':
            # 修复 QA 发现：优先用调用方随 detail 传入的工作区绝对路径（abs_path），
            # 原始 path 可能是相对路径，abspath 会落到进程 CWD 导致名单永不命中
            hit = self._path_protected(detail.get('abs_path') or detail.get('path'))
            if hit:
                return {'action': 'block',
                        'reason': f'路径 {detail.get("path")} 命中保护名单（{hit}），已拒绝删除。如确需删除请用户手动操作或在设置中调整保护名单。'}
        if op == 'kill_process':
            # 修复 ⑦（并入 C1）：pid 不再当进程名做 fnmatch（用户名单含 * 时误伤一切）；
            # pid → 进程名的反查在 Api/process_service 层完成后随 detail.name 传入
            hit = self._process_protected(detail.get('name'))
            if hit:
                return {'action': 'block',
                        'reason': f'进程 {hit} 属于保护名单，已拒绝结束。如确需结束请用户手动操作或在设置中调整保护名单。'}

        # ② allow_rules 白名单（窄规则 > 松模式；命中审计 decision=rule）
        rule = self._match_rule(op, detail)
        if rule is not None:
            return {'action': 'allow', 'via': 'rule',
                    'rule_id': rule.get('rule_id')}

        # ③ task_grant 任务授权（deny 已先于此处生效；grant 内操作刷新空闲计时）
        grant = self._effective_grant()
        if grant is not None:
            need = _OP_GRANT_SCOPES.get(op)
            if need is None or need in grant['scope']:
                # R6：授权内操作刷新空闲计时（idle_deadline = 现在 + 1800s）
                self._touch_grant(grant)
                return {'action': 'allow', 'via': 'grant',
                        'grant_id': grant['grant_id']}

        # ④ op 档：持久信任（guard.json trustedOps，op 级）——重启仍生效。
        # 位置在名单 block 之后：保护名单永远优先于任何信任。
        with self._lock:
            if op in self._cfg.get('trustedOps', []):
                return {'action': 'allow', 'via': 'trusted-persistent'}

        if tier == 'off':
            return {'action': 'allow'}
        if tier == 'list':
            if op in _LISTLESS_OPS:
                # 修复 W10：无名单操作的 list 档语义等同 off 是误导，降级为每次确认
                return {'action': 'confirm', 'op': op, 'label': OP_LABELS.get(op, op)}
            return {'action': 'allow'}
        # always / session → 需要确认
        return {'action': 'confirm', 'op': op, 'label': OP_LABELS.get(op, op)}

    # ---- 后端强制执行（Api 门面挂点，防前端被绕过）----
    def enforce_block_only(self, op, detail=None):
        """仅执行保护名单阻断（不产生确认——确认是前端 UI 职责）。
        返回 block reason 字符串或 None。"""
        r = self.check(op, detail)
        if r.get('action') == 'block':
            return r.get('reason')
        return None

    def enforce_exec(self, op, detail=None, token=None):
        """修复 S4①②：执行点前端的确认不再是唯一防线——武装后后端强制校验。

        - 名单 block：无条件拦截（含未武装环境，保持既有契约行为）
        - v1.8.5 A 域：allow_rules 命中 → 放行 + 审计 decision=rule；
          task_grant 覆盖 → 放行 + 审计 decision=grant（不逐条 toast，防噪）
        - 未武装（无窗口的测试/嵌入环境）：always/session 不强制 token（legacy 兼容）
        - 武装后：always 档要求有效一次性 token；session 档要求 token 或本会话已信任；
          off/list 放行（listless 操作的 list 档按 always 处理，W10）
        返回拒绝原因字符串或 None。
        """
        r = self.check(op, detail)
        if r.get('action') == 'block':
            return r.get('reason')
        # v1.8.0 §4.4：dangerous action 强制 always（detail.force_always）——
        # 高危动作（git push --force/删除类）无视 op 档位与信任态，每次都要
        # 有效一次性 token（软件调用面在 api.software_call 置位）。
        if (detail or {}).get('force_always'):
            if token and self.consume_token(op, detail, token):
                self.audit(op, detail, 'decision', 'token-confirm')
                return None
            return ('该操作属高危动作（dangerous），需每次确认，但调用方未携带有效的'
                    '一次性确认 token。请通过界面确认后执行，不要绕过确认流程。')
        # v1.8.5 A 域：白名单/任务授权在执行点放行并记专项审计
        via = r.get('via')
        if via == 'rule':
            self._note_rule_hit(r.get('rule_id'))
            self.audit(op, detail, 'decision', 'rule')
            return None
        if via == 'grant':
            # 授权内操作不逐条 toast（规范 §3.4 铁律）；空闲计时刷新在 check() 内完成
            self.audit(op, detail, 'decision', 'grant')
            return None
        # 修复 UX-2（v1.4）：持久信任在执行点同样生效（check 已 allow，但未武装环境
        # 不走 check 的信任分支以外的逻辑也无副作用；此处显式短路并审计）
        with self._lock:
            persistent = op in self._cfg.get('trustedOps', [])
        if persistent:
            self.audit(op, detail, 'decision', 'trusted-persistent')
            return None
        if not self._armed:
            return None
        with self._lock:
            trusted = op in self._session_trust
        # 修复 QA 发现：会话信任对 always 档同样生效（PRD R3：always 档确认框的
        # 「本会话内不再提示」勾选即登记信任；原实现只在 session 档查信任，
        # 导致 always 档勾选后前端跳过弹窗、后端仍拒绝——信任承诺断裂）
        if trusted:
            return None
        with self._lock:
            tier = self._cfg['tiers'].get(op, DEFAULT_TIERS.get(op, 'always'))
        if tier == 'list' and op in _LISTLESS_OPS:
            tier = 'always'
        if tier in ('off', 'list'):
            return None
        if token and self.consume_token(op, detail, token):
            self.audit(op, detail, 'decision', 'token-confirm')
            return None
        return ('该操作需要用户在界面确认（护栏档位 %s），但调用方未携带有效的一次性确认 token。'
                '请通过界面确认后执行，不要绕过确认流程。' % tier)

    # ---- confirm token（修复 S4①：一次性 + TTL + 绑定 op+detail 摘要）----
    @staticmethod
    def _canonical_detail(op, detail):
        """detail 归一化：token 签发与执行点校验用同一摘要，避免键序/类型差异误判。"""
        d = detail or {}
        if op == 'delete_path':
            return {'path': str(d.get('path') or '')}
        if op == 'kill_process':
            if d.get('pid') not in (None, ''):
                return {'pid': str(d.get('pid'))}
            return {'name': str(d.get('name') or '').strip().lower()}
        if op == 'clipboard_write':
            # 修复 W1（二轮）：len 口径不一致——Python len() 数码点、JS length 数 UTF-16 码元，
            # 含 emoji 时两侧摘要不同、确认后仍被拦。摘要不绑 len（op 级确认足够）。
            return {}
        if op in ('run_command', 'run_powershell', 'run_admin_command'):
            return {'cmd': str(d.get('cmd') or '')[:200]}
        if op == 'open_app':
            return {'path': str(d.get('path') or '')[:200]}   # 修复 W9（三轮）
        if op == 'mcp_call':
            return {'server': str(d.get('server') or ''), 'tool': str(d.get('tool') or '')}
        return {}

    @classmethod
    def _digest(cls, op, detail):
        return json.dumps(cls._canonical_detail(op, detail),
                          sort_keys=True, ensure_ascii=False)

    def issue_confirm_token(self, op, detail=None):
        """签发一次性 confirm token：{token, ttl}。op 必须是受护栏操作。"""
        if op not in _TOKEN_OPS:
            return {'error': '未知护栏操作: %s' % op}
        token = secrets.token_hex(16)
        expiry = time.time() + TOKEN_TTL
        with self._lock:
            # 顺手清扫过期 token，防 map 膨胀
            now = time.time()
            self._tokens = {t: v for t, v in self._tokens.items() if v[2] > now}
            self._tokens[token] = (op, self._digest(op, detail), expiry)
        return {'token': token, 'ttl': TOKEN_TTL}

    def consume_token(self, op, detail, token):
        """校验并销毁一次性 token（先取后验，重放即失效）。"""
        if not token:
            return False
        with self._lock:
            rec = self._tokens.pop(str(token), None)
        if rec is None:
            return False
        tok_op, digest, expiry = rec
        if time.time() > expiry:
            return False
        return tok_op == op and digest == self._digest(op, detail)

    def refund_token(self, op, detail, token):
        """修复 建议⑱（二轮）：token 退还——调用方在校验通过后、实际执行前失败
        （如 MCP 服务器 spawn 失败）时调用，避免用户白确认一次。"""
        if not token:
            return False
        with self._lock:
            if str(token) in self._tokens:
                return False          # 已存在（异常路径），不覆盖
            self._tokens[str(token)] = (op, self._digest(op, detail),
                                        time.time() + TOKEN_TTL)
        return True

    # ---- 会话信任态（后端持有，切会话清空——W26 语义同步）----
    def trust_session(self, op):
        """登记本会话信任（对应前端「本会话内不再提示」勾选）。"""
        if op not in GUARD_OPS:
            return {'error': '未知护栏操作: %s' % op}
        with self._lock:
            self._session_trust.add(op)
        return {'ok': True}

    def clear_session_trust(self):
        """切会话/新会话时清空（Api.set_current_sid 检测到 sid 变化时调用）。"""
        with self._lock:
            self._session_trust.clear()
            self._tokens.clear()

    # ================================================== v1.8.5 A 域·任务授权
    @staticmethod
    def _iso(ts):
        """epoch → ISO8601 UTC（§4.3：全库统一 'Z' 后缀）。"""
        return datetime.datetime.fromtimestamp(
            float(ts), datetime.timezone.utc).replace(microsecond=0) \
            .isoformat().replace('+00:00', 'Z')

    @staticmethod
    def _norm_scope(scope):
        """scope 归一：枚举数组（或 '+/,/空格' 分隔字符串）→ set；非法 → None。"""
        if isinstance(scope, str):
            parts = [p for p in re.split(r'[+,/\s]+', scope) if p]
        elif isinstance(scope, (list, tuple, set)):
            parts = [str(p) for p in scope]
        else:
            return None
        scopes = {str(p).strip() for p in parts if str(p).strip()}
        if not scopes or not scopes <= set(GRANT_SCOPES):
            return None
        return scopes

    def _effective_grant(self):
        """当前活跃授权（惰性过期修剪：TTL 与空闲先到者生效——R6）。

        过期授权在首次访问时移除并落审计（decision=expired）；无活跃授权
        返回 None。持锁调用（RLock 可重入）。
        """
        with self._lock:
            gid = self._current_grant_id
            grant = self._grants.get(gid) if gid else None
            if grant is None:
                return None
            now = self._clock()
            if now >= grant['expires_at'] or now >= grant['idle_deadline']:
                expired_by = 'ttl' if now >= grant['expires_at'] else 'idle'
                self._grants.pop(gid, None)
                self._current_grant_id = None
                self._audit_grant_expired(gid, expired_by, grant)
                return None
            return grant

    def _audit_grant_expired(self, grant_id, expired_by, grant):
        """授权过期审计（惰性修剪时落；TTL 到期/空闲收回两因可分）。"""
        try:
            self.audit('guard_grant',
                       {'grant_id': grant_id, 'scope': ','.join(sorted(grant['scope'])),
                        'expired_by': expired_by}, 'grant', 'expired')
        except Exception:
            pass

    def _touch_grant(self, grant):
        """grant 内操作刷新空闲计时（R6：idle_deadline = 最后操作 + 1800s）。"""
        with self._lock:
            now = self._clock()
            grant['last_op_at'] = now
            grant['idle_deadline'] = now + GRANT_IDLE_SECONDS

    def task_grant(self, scope, ttl_seconds=GRANT_TTL_DEFAULT):
        """A1：创建任务授权（进程内状态，不入 guard.json——架构 §3.4 铁律）。

        Args:
            scope: 枚举数组（``workspace_write``/``exec``/``app_launch``）；
                空数组或非法枚举 → error（安全参数不静默夹逼）。
            ttl_seconds: 授权时长（60-86400，默认 7200=R6 的 2h 上限口径）。

        Returns:
            dict: ``{ok, grant_id, expires_at, idle_deadline, remaining_s,
            scope, granted_by}`` 或 ``{error}``。idle_deadline = 最后操作 +
            1800s（授权建立瞬间可能与 expires_at 相同或更短——先到者生效）。
        """
        scopes = self._norm_scope(scope)
        if scopes is None:
            return {'error': 'scope 需为非空枚举数组（合法值: %s）'
                    % '/'.join(GRANT_SCOPES)}
        ttl = ttl_seconds
        if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) \
                or int(ttl) != ttl:
            return {'error': 'ttl_seconds 需为整数（%d-%d 秒）'
                    % (GRANT_TTL_MIN, GRANT_TTL_MAX)}
        ttl = int(ttl)
        if ttl < GRANT_TTL_MIN or ttl > GRANT_TTL_MAX:
            return {'error': 'ttl_seconds 超出范围（%d-%d 秒），安全参数不静默夹逼'
                    % (GRANT_TTL_MIN, GRANT_TTL_MAX)}
        now = self._clock()
        grant_id = 'g_%s' % secrets.token_hex(8)
        grant = {
            'grant_id': grant_id, 'scope': scopes, 'granted_at': now,
            'expires_at': now + ttl, 'idle_deadline': now + GRANT_IDLE_SECONDS,
            'last_op_at': now, 'granted_by': 'user',
        }
        with self._lock:
            self._grants[grant_id] = grant
            self._current_grant_id = grant_id
        self.audit('guard_grant', {'grant_id': grant_id,
                                   'scope': ','.join(sorted(scopes)),
                                   'ttl': ttl}, 'grant', 'grant')
        return {'ok': True, 'grant_id': grant_id,
                'expires_at': self._iso(grant['expires_at']),
                'idle_deadline': self._iso(grant['idle_deadline']),
                'remaining_s': int(min(grant['expires_at'],
                                       grant['idle_deadline']) - now),
                'scope': sorted(scopes), 'granted_by': 'user'}

    def task_revoke(self, grant_id=None):
        """A2：收回任务授权（缺省=当前；幂等——本就无授权返回 revoked:false）。"""
        with self._lock:
            gid = str(grant_id).strip() if grant_id else self._current_grant_id
            if gid and gid in self._grants:
                self._grants.pop(gid, None)
                if self._current_grant_id == gid:
                    self._current_grant_id = None
                revoked = True
            else:
                revoked = False
        if revoked:
            self.audit('guard_revoke', {'grant_id': gid}, 'revoke', 'revoke')
        return {'ok': True, 'revoked': revoked}

    def task_status(self):
        """A3：授权状态（前端 #grantIndicator 倒计时校准源）。

        Returns:
            dict: ``{ok, active, grant_id?, expires_at?, idle_deadline?,
            remaining_s?, scope?, granted_by?, expiring_soon?}``——
            remaining_s = max(0, min(expires_at, idle_deadline) - now)
            （后端权威，含空闲收回语义）；剩余 <600s 附 expiring_soon。
        """
        grant = self._effective_grant()
        if grant is None:
            return {'ok': True, 'active': False}
        now = self._clock()
        remaining = max(0, int(min(grant['expires_at'],
                                   grant['idle_deadline']) - now))
        return {'ok': True, 'active': True, 'grant_id': grant['grant_id'],
                'expires_at': self._iso(grant['expires_at']),
                'idle_deadline': self._iso(grant['idle_deadline']),
                'remaining_s': remaining,
                'scope': sorted(grant['scope']),
                'granted_by': grant['granted_by'],
                'expiring_soon': remaining < GRANT_EXPIRING_SOON_S}

    # ================================================== v1.8.5 A 域·白名单
    def rule_add(self, op_pattern, detail_pattern=None, note=None):
        """A5：添加白名单规则（窄规则优先；deny 清单覆盖的创建即拒）。

        Args:
            op_pattern: op 名正则（空 → error；非法正则 → error）。
            detail_pattern: detail 文本正则（可选；非法 → error）。
            note: 备注（≤200 字符）。

        Returns:
            dict: ``{ok, rule_id, warn?}`` 或 ``{error, code?}``——
            deny 清单覆盖（对 delete_path/kill_process 的无 detail 宽规则，
            或 detail 直接命中保护进程/路径）→ ``{error, code:
            'GUARD_DENIED'}``；detail 含写动词 → warn（不阻断，架构 §3.4）。
        """
        op_p = str(op_pattern or '').strip()
        if not op_p:
            return {'error': 'op_pattern 不能为空'}
        try:
            op_rx = re.compile(op_p)
        except re.error as e:
            return {'error': 'op_pattern 不是合法正则: %s' % e}
        d_p = str(detail_pattern or '').strip()
        d_rx = None
        if d_p:
            try:
                d_rx = re.compile(d_p)
            except re.error as e:
                return {'error': 'detail_pattern 不是合法正则: %s' % e}
        covered = self._rule_covered_by_deny(op_rx, d_rx)
        if covered:
            return {'error': covered, 'code': 'GUARD_DENIED'}
        warn = None
        if d_p and any(re.search(r'\b%s\b' % re.escape(v), d_p, re.IGNORECASE)
                       for v in _RULE_WRITE_VERBS):
            warn = 'detail 含写动词，确认这是宽模式规则？（窄规则优先）'
        rule_id = 'r_%s' % secrets.token_hex(6)
        rule = {'rule_id': rule_id, 'op_pattern': op_p, 'hits': 0,
                'created_at': self._iso(self._clock())}
        if d_p:
            rule['detail_pattern'] = d_p
        note_s = str(note or '').strip()[:200]
        if note_s:
            rule['note'] = note_s
        with self._lock:
            self._cfg.setdefault('allow_rules', []).append(rule)
            self._write_cfg_locked()
        self.audit('guard_rule_add', {'rule_id': rule_id, 'op_pattern': op_p,
                                      'detail_pattern': d_p}, 'rule', 'allow')
        out = {'ok': True, 'rule_id': rule_id}
        if warn:
            out['warn'] = warn
        return out

    def _rule_covered_by_deny(self, op_rx, detail_rx):
        """deny 清单覆盖判定（规则创建时即拒——deny 先于白名单）。

        对 deny 语义最强的 op（delete_path/kill_process）：
        - 无 detail 约束的宽规则 → 拒（会架空保护名单）；
        - detail 正则直接命中内置保护进程名/用户保护路径模式 → 拒。
        返回拒绝人话或 None。
        """
        for op in _DENY_SENSITIVE_OPS:
            if not op_rx.search(op):
                continue
            if detail_rx is None:
                return ('该规则覆盖 %s 且无 detail 窄约束，会架空保护名单'
                        '（deny 清单先于白名单生效），已拒绝创建' % op)
            if op == 'kill_process':
                for name in sorted(_BUILTIN_PROTECTED_PROCESSES):
                    if detail_rx.search(name):
                        return ('detail 模式命中内置保护进程 %s'
                                '（deny 清单先于白名单生效），已拒绝创建' % name)
            else:
                with self._lock:
                    pats = list(self._cfg.get('protect_paths') or [])
                for pat in pats:
                    if detail_rx.search(pat):
                        return ('detail 模式命中保护路径 %s'
                                '（deny 清单先于白名单生效），已拒绝创建' % pat)
        return None

    def rule_list(self):
        """A4：白名单列表（可选字段缺失即缺省——§4.3）。"""
        with self._lock:
            rules = []
            for r in self._cfg.get('allow_rules') or []:
                item = {'rule_id': r.get('rule_id'),
                        'op_pattern': r.get('op_pattern'),
                        'hits': r.get('hits', 0),
                        'created_at': r.get('created_at', '')}
                if r.get('detail_pattern'):
                    item['detail_pattern'] = r['detail_pattern']
                if r.get('note'):
                    item['note'] = r['note']
                rules.append(item)
        return {'ok': True, 'rules': rules}

    def rule_remove(self, rule_id):
        """A6：删除白名单规则（幂等；删除即时生效）。"""
        rid = str(rule_id or '').strip()
        removed = False
        with self._lock:
            rules = self._cfg.get('allow_rules') or []
            for i, r in enumerate(rules):
                if r.get('rule_id') == rid:
                    rules.pop(i)
                    removed = True
                    break
            if removed:
                self._write_cfg_locked()
        if removed:
            self.audit('guard_rule_remove', {'rule_id': rid}, 'rule', 'remove')
        return {'ok': True, 'removed': removed}

    def _match_rule(self, op, detail):
        """白名单命中判定（窄规则优先：带 detail_pattern 的先试）。

        返回命中 rule 或 None。仅 op_pattern 命中即适用的松规则排在
        detail 规则之后（Safeguard 原则：窄规则 > 松模式）。
        """
        with self._lock:
            rules = list(self._cfg.get('allow_rules') or [])
        if not rules:
            return None
        detail_text = self._rule_detail_text(op, detail)
        narrow = [r for r in rules if r.get('detail_pattern')]
        loose = [r for r in rules if not r.get('detail_pattern')]
        for r in narrow + loose:
            try:
                if not re.search(r.get('op_pattern') or '', op):
                    continue
            except re.error:
                continue
            d_p = r.get('detail_pattern')
            if d_p:
                try:
                    if detail_text and re.search(d_p, detail_text):
                        return r
                except re.error:
                    continue
                continue        # 窄规则未命中 detail → 不适用
            return r
        return None

    @staticmethod
    def _rule_detail_text(op, detail):
        """detail → 可正则检索文本（与各 op 的 detail 构造同口径）。"""
        d = detail or {}
        if op == 'delete_path':
            return str(d.get('abs_path') or d.get('path') or '')
        if op == 'kill_process':
            return str(d.get('name') or d.get('pid') or '')
        if op in ('run_command', 'run_powershell', 'run_admin_command'):
            return str(d.get('cmd') or '')
        if op == 'open_app':
            return str(d.get('path') or '')
        if op == 'clipboard_write':
            return str(d.get('head') or '')
        if not d:
            return ''
        try:
            return json.dumps(d, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            return ''

    def _note_rule_hit(self, rule_id):
        """规则命中计数（执行点调用；落盘保持重启后可查）。"""
        if not rule_id:
            return
        with self._lock:
            rules = self._cfg.get('allow_rules') or []
            for r in rules:
                if r.get('rule_id') == rule_id:
                    r['hits'] = int(r.get('hits') or 0) + 1
                    try:
                        self._write_cfg_locked()
                    except Exception as e:
                        self._log.debug('规则命中计数落盘失败: %r', e)
                    return

    # ---- 审计日志 ----
    def set_trace_hook(self, hook):
        """W1：trace_id 钩子（Api 装配时注入 lambda: api.current_trace()）。

        注入后每条审计自动带 trace 字段（t_<ts36>_<rand4>）——同一用户请求
        的 guard/plan/tool 全链路可追。hook 异常/无钩子 → trace=None（不影响
        审计写入，向后兼容）。
        """
        self._trace_hook = hook

    def current_trace(self):
        try:
            return self._trace_hook() if self._trace_hook else None
        except Exception:
            return None

    def audit(self, op, detail=None, action='check', decision=None):
        try:
            entry = {
                'ts': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'op': op, 'action': action,
                'detail': {k: str(v)[:200] for k, v in (detail or {}).items()},
            }
            if decision:
                entry['decision'] = decision
            trace = self.current_trace()
            if trace:
                entry['trace'] = trace
            os.makedirs(os.path.dirname(self._audit_path), exist_ok=True)
            # 修复 建议④（二轮）：轮转+追加整体持实例锁——多线程并发回调下
            # 轮转与 append 交错会丢行/写进已被轮转走的旧文件
            with self._lock:
                try:
                    if os.path.exists(self._audit_path) and \
                            os.path.getsize(self._audit_path) > AUDIT_MAX_BYTES:
                        os.replace(self._audit_path, self._audit_path.replace('.jsonl', '.1.jsonl'))
                except Exception:
                    pass
                with open(self._audit_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            return '{"ok":true}'
        except Exception as e:
            self._log.warning('审计日志写入失败: %r', e)
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def read_audit(self, limit=200, offset=0):
        """读取审计日志供查看器展示：倒序（最新在前）返回最多 limit 条。

        纯本地文件读取，无网络。返回 {ok, total, entries:[...]}；
        文件不存在视为空日志（不是错误）。
        修复 W12：流式读 + deque 窗口，不再全量读入内存。
        """
        try:
            limit = max(1, min(int(limit or 200), 1000))
            offset = max(0, int(offset or 0))
            if not os.path.exists(self._audit_path):
                return json.dumps({'ok': True, 'total': 0, 'entries': []}, ensure_ascii=False)
            total = 0
            window = deque(maxlen=offset + limit)   # 只保留末尾 offset+limit 行
            with open(self._audit_path, 'r', encoding='utf-8') as f:
                for ln in f:
                    if ln.strip():
                        total += 1
                        window.append(ln)
            entries = []
            for ln in list(window)[::-1][offset:offset + limit]:
                try:
                    entries.append(json.loads(ln))
                except Exception:
                    continue   # 单行损坏不拖垮整页
            return json.dumps({'ok': True, 'total': total, 'entries': entries}, ensure_ascii=False)
        except Exception as e:
            self._log.warning('审计日志读取失败: %r', e)
            return json.dumps({'error': str(e)}, ensure_ascii=False)
