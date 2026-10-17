# -*- coding: utf-8 -*-
"""进程级可变Runtime state（legacy _RT 对象袋 L138 + _SESSION_WS 使能开关）。

收敛原则：可变状态集中本类，内部持锁；Api 门面与服务不再直接摸全局 dict。
"""
import json
import os
import threading

from . import paths
from .fio import atomic_write_json


class RuntimeState:
    """win/ws_enabled/current_sid 的唯一所有者。

    修复 建议①：form/core/last_bounds 只写不读（死状态）已删除；
    win 保留——js_api 桌面会话武装（guard arm）与窗口操作需要。"""

    def __init__(self, ws_enabled_path=None):
        self._lock = threading.RLock()
        self.win = None
        self._ws_enabled_path = ws_enabled_path or paths.WS_ENABLED_FILE
        self._ws_enabled = {}
        self._current_sid = None

    # ---- current_sid ----
    def get_current_sid(self):
        with self._lock:
            return self._current_sid

    def set_current_sid(self, sid):
        with self._lock:
            self._current_sid = sid or None
        return self._current_sid

    # ---- ws_enabled（per-sid 开关，带持久化）----
    def load_ws_enabled(self, logger=None):
        try:
            with open(self._ws_enabled_path, 'r', encoding='utf-8') as f:
                d = json.load(f)
            if isinstance(d, dict):
                with self._lock:
                    for k, v in d.items():
                        self._ws_enabled[str(k)] = bool(v)
        except FileNotFoundError:
            pass
        except json.JSONDecodeError:
            # 修复 建议⑨（二轮）：仅 JSON 损坏才留证改名；瞬时 IO 错误不毁好文件
            try:
                _mark_bad(self._ws_enabled_path)
            except Exception:
                pass
        except Exception as e:
            if logger:
                logger.warning('ws_enabled 状态加载失败，按默认全开处理: %r', e)

    def save_ws_enabled(self, logger=None):
        try:
            with self._lock:
                snap = dict(self._ws_enabled)
            os.makedirs(paths.CONFIG_DIR, exist_ok=True)
            # 修复 S8：原子写（tmp+fsync+replace），崩溃不留半截 JSON
            atomic_write_json(self._ws_enabled_path, snap)
        except Exception as e:
            if logger:
                logger.warning('ws_enabled 状态保存失败: %r', e)

    def ws_enabled_for(self, sid, default=True):
        with self._lock:
            return self._ws_enabled.get(sid or '', default)

    def set_ws_enabled(self, sid, enabled):
        with self._lock:
            self._ws_enabled[sid or ''] = bool(enabled)

    def pop_ws_enabled(self, sid):
        with self._lock:
            self._ws_enabled.pop(sid or '', None)


def _mark_bad(path):
    os.replace(path, path + '.bad')
