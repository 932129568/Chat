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
    def get_sessions(self):
        try:
            if os.path.exists(paths.SESSIONS_PATH):
                with open(paths.SESSIONS_PATH, 'r', encoding='utf-8') as f:
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
            atomic_write_text(paths.SESSIONS_PATH,
                              data if isinstance(data, str) else json.dumps(data, ensure_ascii=False))
            return '{"ok":true}'
        except Exception as e:
            return err(e)

    # ---- memory.json（legacy L804-824）----
    def get_memory(self):
        try:
            if os.path.exists(paths.MEMORY_PATH):
                with open(paths.MEMORY_PATH, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception as e:
            self._log.warning('记忆读取失败: %r', e)
        return '[]'

    def append_memory(self, entry_json):
        try:
            with self._lock:
                items = json.loads(self.get_memory())
                e = json.loads(entry_json) if isinstance(entry_json, str) else entry_json
                # 修复 ⑤（三轮）：非对象入参（字符串/数字/null）原直接 e['ts'] 抛
                # TypeError 回裸异常串——归一为 {text: ...} 对象
                if not isinstance(e, dict):
                    e = {'text': '' if e is None else str(e)}
                e['ts'] = datetime.datetime.now().strftime('%m-%d %H:%M')
                items.append(e)
                atomic_write_json(paths.MEMORY_PATH, items[-200:])   # 修复 S8：原子写
            return '{"ok":true}'
        except Exception as e:
            return err(e)
