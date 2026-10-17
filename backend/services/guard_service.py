# -*- coding: utf-8 -*-
"""安全护栏服务（v1.2 R2 + 修复 S4）：破坏性操作确认矩阵 + 保护名单 + 审计日志
+ 进程内 confirm-token / 会话信任态后端强制。

设计（PRD §7.1）：
- 确认矩阵：delete_path / kill_process / clipboard_write / clipboard_read / take_screenshot
  五个操作三档可配；修复 S4 起追加 run_command / run_powershell / run_admin_command
  三个命令执行 op（默认 'off'，用户可在 guard.json 中提档加固）：
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

存储：独立文件 guard.json（不碰 config.json——契约差分测试对 config.json 内容逐字节比对）。
"""
import datetime
import fnmatch
import json
import os
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
             'take_screenshot', 'run_command', 'run_powershell', 'run_admin_command')
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
}

# 无保护名单意义的操作：'list' 档对它们语义等同 off 是误导（W10），后端降级为每次确认
_LISTLESS_OPS = {'clipboard_write', 'clipboard_read', 'take_screenshot',
                 'run_command', 'run_powershell', 'run_admin_command'}

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
    def __init__(self, guard_path=None, audit_path=None):
        self._log = get_logger()
        self._lock = threading.RLock()
        self._path = guard_path or GUARD_FILE
        self._audit_path = audit_path or AUDIT_LOG
        self._cfg = self._load()
        # 修复 S4①：进程内信任态（一次性 token + 会话信任 + 武装标志）
        self._tokens = {}              # token -> (op, detail_digest, expiry_ts)
        self._session_trust = set()    # 本会话已信任的 op（切会话清空，W26 同步语义）
        self._armed = False            # 桌面 UI 会话武装标志（Api._set_window 置位）

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
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                atomic_write_json(self._path, self._cfg, indent=2)   # 修复 S8：原子写
            return '{"ok":true}'
        except Exception as e:
            self._log.exception('护栏配置保存失败')
            return json.dumps({'error': str(e)}, ensure_ascii=False)

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
        """返回 dict：{action: 'allow'|'confirm'|'block', reason, detail}。

        - block：命中保护名单（即使档位是 always/session 也直接阻断）
        - confirm：档位 always；或档位 session（首次，会话信任态后端持有）
        - allow：档位 off / list 未命中 / session（已信任时前端自行放行）
        """
        detail = detail or {}
        if op not in GUARD_OPS:
            return {'action': 'allow'}
        with self._lock:
            tier = self._cfg['tiers'].get(op, DEFAULT_TIERS.get(op, 'always'))

        # 保护名单优先于档位（名单命中 = 无条件阻断）
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

        # 修复 UX-2（v1.4）：持久信任（guard.json trustedOps，op 级）——重启仍生效。
        # 位置在名单 block 之后：保护名单永远优先于任何信任。
        with self._lock:
            if op in self._cfg.get('trustedOps', []):
                return {'action': 'allow'}

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
        - 未武装（无窗口的测试/嵌入环境）：always/session 不强制 token（legacy 兼容）
        - 武装后：always 档要求有效一次性 token；session 档要求 token 或本会话已信任；
          off/list 放行（listless 操作的 list 档按 always 处理，W10）
        返回拒绝原因字符串或 None。
        """
        r = self.check(op, detail)
        if r.get('action') == 'block':
            return r.get('reason')
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

    # ---- 审计日志 ----
    def audit(self, op, detail=None, action='check', decision=None):
        try:
            entry = {
                'ts': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'op': op, 'action': action,
                'detail': {k: str(v)[:200] for k, v in (detail or {}).items()},
            }
            if decision:
                entry['decision'] = decision
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
