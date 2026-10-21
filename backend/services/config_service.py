# -*- coding: utf-8 -*-
"""配置存储服务：config.json / sessions.json / memory.json + 全局工作区。

legacy Api L252-305 / L227-250 / L804-824 原样搬迁；
修复：config.json 读-改-写竞态（save_config/_save_workspace 统一加锁）；
修复：静默吞错改为记录日志后按 legacy 语义降级。
"""
import datetime
import json
import os
import threading

from .. import paths
from ..errors import err, ok
from ..fio import atomic_write_json, atomic_write_text
from ..logging_setup import get_logger


class ConfigService:
    def __init__(self):
        self._log = get_logger()
        self._lock = threading.RLock()
        self.cwd = self._load_workspace()

    # ---- 全局工作区（legacy L227-250）----
    def set_cwd(self, path):
        """修复 建议⑧（二轮）：全局工作区改走的统一入口——锁内赋值+落盘
        （原 set_ws_dir 在锁外直接改 config.cwd 且不持久化，重启即丢）。"""
        with self._lock:
            self.cwd = os.path.abspath(str(path))
            self._save_workspace()
        return self.cwd

    def _load_workspace(self):
        try:
            if os.path.exists(paths.CONFIG_PATH):
                with open(paths.CONFIG_PATH, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                ws = cfg.get('workspace')
                if ws and os.path.isdir(ws):
                    return ws
        except Exception as e:
            self._log.warning('工作区配置加载失败，使用默认目录: %r', e)
        desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
        if not os.path.exists(desktop):
            desktop = os.path.expanduser('~')
        ws = os.path.join(desktop, 'GLM-Workspace')
        try:
            os.makedirs(ws, exist_ok=True)
        except Exception as e:
            self._log.warning('默认工作区创建失败: %r', e)
        return ws

    def _save_workspace(self):
        try:
            with self._lock:
                cfg = {}
                if os.path.exists(paths.CONFIG_PATH):
                    try:
                        with open(paths.CONFIG_PATH, 'r', encoding='utf-8') as f:
                            cfg = json.load(f)
                    except Exception:
                        cfg = {}
                cfg['workspace'] = self.cwd
                atomic_write_json(paths.CONFIG_PATH, cfg)   # 修复 S8：原子写
        except Exception as e:
            self._log.warning('工作区配置保存失败: %r', e)

    # ---- config.json（legacy L253-277）----
    def get_config(self):
        try:
            if os.path.exists(paths.CONFIG_PATH):
                with open(paths.CONFIG_PATH, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception as e:
            self._log.warning('配置读取失败: %r', e)
        return '{}'

    def save_config(self, config_json):
        try:
            with self._lock:
                cfg = {}
                if os.path.exists(paths.CONFIG_PATH):
                    try:
                        with open(paths.CONFIG_PATH, 'r', encoding='utf-8') as f:
                            cfg = json.load(f)
                    except Exception:
                        cfg = {}
                # 修复 建议⑥（二轮）：入参不是合法 JSON 时显式报错（原静默忽略仍返回 ok:true）
                try:
                    incoming = json.loads(config_json)
                except Exception as e:
                    return err('配置 JSON 解析失败，未写入: %s' % e)
                # 修复 建议⑩（二轮）：合法 JSON 但不是对象也显式报错（原静默 ok:true，
                # 用户以为保存成功实际什么都没改）
                if not isinstance(incoming, dict):
                    return err('配置必须是 JSON 对象（{...}），未写入')
                cfg.update(incoming)
                atomic_write_json(paths.CONFIG_PATH, cfg)   # 修复 S8：原子写
            return '{"ok":true}'
        except Exception as e:
            return err(e)

    # ---- sessions.json（legacy L279-295）----
    # v1.8.0 历史自选存放（2026-10-21）：sessions.json 位置由 history.json 的
    # dir 决定（空=默认 ~/.glm-chat/sessions.json）。history.json 独立文件——
    # config.json 零污染铁律。路径经 _sessions_dir() 归一（每次读配置，切换
    # 目录即时生效，无需重启）。
    def _history_cfg(self):
        """读 history.json → {'dir': 绝对路径或''}（损坏/缺失 → 默认空）。"""
        try:
            if os.path.exists(paths.HISTORY_FILE):
                with open(paths.HISTORY_FILE, encoding='utf-8') as f:
                    d = json.load(f)
                if isinstance(d, dict):
                    return {'dir': str(d.get('dir') or '').strip()}
        except Exception as e:
            self._log.warning('history.json 读取失败: %r', e)
        return {'dir': ''}

    def sessions_path(self):
        """当前 sessions.json 绝对路径（自选目录优先；目录失效回落默认）。"""
        d = self._history_cfg()['dir']
        if d and os.path.isdir(d):
            return os.path.join(d, 'sessions.json')
        return paths.SESSIONS_PATH

    def get_sessions(self):
        try:
            p = self.sessions_path()
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception as e:
            self._log.warning('会话列表读取失败: %r', e)
        return '[]'

    def save_sessions(self, data):
        try:
            # 修复 S8：写入前先校验是合法 JSON（前端传入串损坏时不再把 sessions.json 写坏）
            parsed = json.loads(data) if isinstance(data, str) else data
            if not isinstance(parsed, list):
                return err('sessions 必须是 JSON 数组，未写入')
            p = self.sessions_path()
            os.makedirs(os.path.dirname(p), exist_ok=True)
            atomic_write_text(p,
                              data if isinstance(data, str) else json.dumps(data, ensure_ascii=False))
            return '{"ok":true}'
        except Exception as e:
            return err(e)

    def session_purge(self, sid, task_ids_json='[]'):
        """真删一条会话的全部痕迹（2026-10-21 用户需求：删掉就是真删掉）。

        删：sessions.json 条目（后端保底）+ session_ws 绑定 + 关联的 plan
        json + 关联的 checkpoint 目录。task_ids 由前端传入（s.plan.task_id
        ——plan 与 sid 的关联在前端会话对象，后端不冗余存）。
        返回 {ok, removed: {sessions, ws, plans, checkpoints}}。
        """
        import glob
        import shutil
        sid = str(sid or '')
        removed = {'sessions': 0, 'ws': 0, 'plans': 0, 'checkpoints': 0}
        try:
            tasks = json.loads(task_ids_json or '[]')
            if not isinstance(tasks, list):
                tasks = []
        except Exception:
            tasks = []
        # ① sessions.json 条目（保底——前端通常已 filter 过）
        try:
            p = self.sessions_path()
            if os.path.exists(p):
                with open(p, encoding='utf-8') as f:
                    arr = json.load(f)
                if isinstance(arr, list):
                    keep = [s for s in arr if str(s.get('id') or '') != sid]
                    if len(keep) != len(arr):
                        atomic_write_text(p, json.dumps(keep, ensure_ascii=False))
                        removed['sessions'] = len(arr) - len(keep)
        except Exception as e:
            self._log.warning('purge sessions 失败: %r', e)
        # ② session_ws 绑定（直接删 session_ws.json 里的条目——workspace_service
        # 的 delete_session_ws 要 runtime 单例，此处保底路径直接操作文件）
        try:
            if os.path.exists(paths.SESSION_WS_FILE):
                with open(paths.SESSION_WS_FILE, encoding='utf-8') as f:
                    ws_map = json.load(f)
                if isinstance(ws_map, dict) and sid in ws_map:
                    del ws_map[sid]
                    atomic_write_text(paths.SESSION_WS_FILE,
                                      json.dumps(ws_map, ensure_ascii=False))
                    removed['ws'] = 1
        except Exception as e:
            self._log.debug('purge ws 失败（可忽略）: %r', e)
        # ③ plan json + ④ checkpoint 目录（按前端传入 task_ids）
        from . import plan_service as _ps
        for tid in tasks:
            tid = str(tid or '').strip()
            if not tid:
                continue
            try:
                tp = _ps._task_path(tid)
                if os.path.exists(tp):
                    os.remove(tp)
                    removed['plans'] += 1
                cp = _ps._ckpt_path(tid)
                if os.path.isdir(cp):
                    shutil.rmtree(cp, ignore_errors=True)
                    removed['checkpoints'] += 1
            except Exception as e:
                self._log.warning('purge plan/ckpt %s 失败: %r', tid, e)
        return {'ok': True, 'sid': sid, 'removed': removed}

    # ---- 历史存放目录（history.json；独立文件，config.json 零污染）----
    _SENSITIVE_DIRS = ('c:\\windows', 'c:\\program files', 'c:\\program files (x86)',
                       'c:\\programdata', 'c:\\$recycle.bin', 'c:\\system volume information')

    def history_dir_get(self):
        """当前历史存放目录（'' = 默认 ~/.glm-chat/）。"""
        return {'ok': True, 'dir': self._history_cfg()['dir'],
                'default_dir': paths.CONFIG_DIR,
                'sessions_file': self.sessions_path()}

    def history_dir_set(self, dir_path, migrate=False):
        """设置历史存放目录（空串=恢复默认）。

        校验：目录必须已存在且可写；禁系统敏感目录（Windows/Program Files 等）；
        realpath 归一（防 symlink/junction 绕过与重复登记）。
        migrate=True：把旧 sessions.json 搬到新目录（已存在则跳过，不覆盖）。
        返回 {ok, dir, migrated} 或 {error: 人话}。
        """
        d = str(dir_path or '').strip()
        if not d:
            # 恢复默认
            self._save_history_cfg('')
            return {'ok': True, 'dir': '', 'migrated': False}
        norm = os.path.realpath(os.path.abspath(os.path.expanduser(d)))
        if not os.path.isdir(norm):
            return {'error': '目录不存在：%s（请先创建）' % d}
        if not os.access(norm, os.W_OK):
            return {'error': '目录不可写：%s' % norm}
        low = norm.lower().rstrip('\\/')
        for s in self._SENSITIVE_DIRS:
            if low == s or low.startswith(s + '\\'):
                return {'error': '不能使用系统目录：%s' % norm}
        migrated = False
        old_default = paths.SESSIONS_PATH
        if migrate and os.path.isfile(old_default) and \
                os.path.realpath(os.path.dirname(old_default)) != norm:
            dst = os.path.join(norm, 'sessions.json')
            if not os.path.exists(dst):
                try:
                    import shutil
                    shutil.copy2(old_default, dst)
                    migrated = True
                except Exception as e:
                    return {'error': '迁移失败: %s' % e}
        self._save_history_cfg(norm)
        return {'ok': True, 'dir': norm, 'migrated': migrated}

    def _save_history_cfg(self, dir_abs):
        """history.json 原子写（dir 绝对路径；''=默认）。"""
        try:
            atomic_write_text(paths.HISTORY_FILE,
                              json.dumps({'dir': dir_abs}, ensure_ascii=False))
            return True
        except Exception as e:
            self._log.warning('history.json 写入失败: %r', e)
            return False

    # ---- memory.json（legacy L804-824 → W11 结构化三类 2026-10-21）----
    def _memory(self):
        """MemoryService 懒单例（结构化三类/检索/注入）。"""
        if getattr(self, '_mem_svc', None) is None:
            from .memory_service import MemoryService
            self._mem_svc = MemoryService(paths.MEMORY_PATH, self._log)
        return self._mem_svc

    def get_memory(self):
        """读取（结构化输出：每条带 kind；旧数据懒迁移不落盘）。"""
        try:
            return json.dumps(self._memory().list(), ensure_ascii=False)
        except Exception as e:
            self._log.warning('记忆读取失败: %r', e)
        return '[]'

    def memory_retrieve(self, query, limit=5):
        """W11：关键词检索（bigram 重叠 + rule 加成 + 时间衰减）。"""
        try:
            items = self._memory().retrieve(str(query or ''), int(limit or 5))
            return {'ok': True, 'items': items}
        except Exception as e:
            return {'error': str(e)}

    def append_memory(self, entry_json):
        """W11 结构化追加：自动分类（fact/preference/rule）+ rule/preference
        文本去重 + 上限淘汰最旧 fact（指令类不淘汰）。旧签名（JSON 串/对象/
        裸字符串）全兼容；返回 {ok, kind, total}。"""
        try:
            with self._lock:
                e = entry_json
                if isinstance(e, str):
                    try:
                        e = json.loads(e)
                    except Exception:
                        e = {'text': e}      # 裸字符串兜底（非 JSON）
                if not isinstance(e, dict):
                    e = {'text': '' if e is None else str(e)}
                r = self._memory().append(e)
                if 'error' in r:
                    return err(r['error'])
                return json.dumps(r, ensure_ascii=False)
        except Exception as e:
            return err(e)

    def delete_memory(self, index):
        """实现 v1.8.0 W11：删除 memory.json 数组第 index 条（0 起；原子写）。

        边界校验不静默夹逼：bool/None/float 等非整数形态与越界下标一律
        {'error': {'code': 'BAD_PARAMS', ...}}（数字字符串按 int 解析）；
        memory.json 损坏（非数组）→ BAD_PARAMS 结构异常人话。
        成功返回 {'ok': True, 'index': idx, 'remaining': N}。"""
        try:
            idx = self._coerce_index(index)
        except (TypeError, ValueError) as e:
            return {'error': {'code': 'BAD_PARAMS', 'message': str(e),
                              'hint': '传入要删除的记忆序号（从 0 开始）'}}
        try:
            with self._lock:
                items = json.loads(self.get_memory())
                if not isinstance(items, list):
                    return {'error': {'code': 'BAD_PARAMS',
                                      'message': '记忆文件结构异常（不是数组），暂不能删除',
                                      'hint': '可手工编辑 ~/.glm-chat/memory.json 修复'}}
                if idx < 0 or idx >= len(items):
                    return {'error': {'code': 'BAD_PARAMS',
                                      'message': '序号越界：当前共 %d 条记忆' % len(items),
                                      'hint': '刷新列表后重试；序号从 0 开始'}}
                items.pop(idx)
                atomic_write_json(paths.MEMORY_PATH, items)
                return {'ok': True, 'index': idx, 'remaining': len(items)}
        except Exception as e:
            self._log.warning('记忆删除失败: %r', e)
            return {'error': {'code': 'INTERNAL', 'message': str(e)}}

    @staticmethod
    def _coerce_index(index):
        """下标归一：bool 是 int 子类须显式排除；float 一律拒绝（不静默截断）；
        字符串按 int 解析（解析失败给人话，不漏 Python 内部异常串）。"""
        if index is None or isinstance(index, bool):
            raise ValueError('序号需要是整数')
        if isinstance(index, int):
            return index
        if isinstance(index, str):
            s = index.strip()
            try:
                return int(s)
            except ValueError:
                raise ValueError('序号需要是整数（收到 %r）' % s[:32])
        raise ValueError('序号需要是整数')
