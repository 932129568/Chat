# -*- coding: utf-8 -*-
import webview
import os
import sys
import json
import re
import difflib
import subprocess
import ctypes
import tempfile
import shutil
import datetime
import base64
import io
import time
import collections
import threading

# ===== 会话级工作区 =====
_WS_LOCK = threading.Lock()
_SESSION_WS = {}

_CFG_DIR = os.path.join(os.path.expanduser('~'), '.glm-chat')
_SESSION_WS_FILE = os.path.join(_CFG_DIR, 'session_ws.json')
_RECENT_WS_FILE = os.path.join(_CFG_DIR, 'recent_ws.json')
_WS_ENABLED_FILE = os.path.join(_CFG_DIR, 'ws_enabled.json')

def _load_session_ws():
    try:
        with open(_SESSION_WS_FILE, 'r', encoding='utf-8') as f:
            d = json.load(f)
        for sid, p in (d or {}).items():
            if isinstance(p, str) and os.path.isdir(p):
                _SESSION_WS[sid] = os.path.abspath(p)
    except FileNotFoundError:
        pass
    except Exception:
        try: os.replace(_SESSION_WS_FILE, _SESSION_WS_FILE + '.bad')
        except Exception: pass

def _save_session_ws():
    try:
        os.makedirs(_CFG_DIR, exist_ok=True)
        with _WS_LOCK: snap = dict(_SESSION_WS)
        with open(_SESSION_WS_FILE, 'w', encoding='utf-8') as f:
            json.dump(snap, f, ensure_ascii=False)
    except Exception: pass

def _load_ws_enabled():
    try:
        with open(_WS_ENABLED_FILE, 'r', encoding='utf-8') as f:
            d = json.load(f)
        if isinstance(d, dict):
            for k, v in d.items(): _RT['ws_enabled'][str(k)] = bool(v)
    except Exception: pass

def _save_ws_enabled():
    try:
        os.makedirs(_CFG_DIR, exist_ok=True)
        with open(_WS_ENABLED_FILE, 'w', encoding='utf-8') as f:
            json.dump(dict(_RT['ws_enabled']), f, ensure_ascii=False)
    except Exception: pass

class FileFingerprintCache:
    """文件指纹缓存 v2: 路径 -> (mtime_ns, size)。写后 invalidate 让 AI 重读。"""
    MAX = 512
    def __init__(self):
        self._fp = {}
    def _stat(self, path):
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    def unchanged(self, path):
        old = self._fp.get(path)
        if old is None: return False
        try: return self._stat(path) == old
        except OSError:
            self._fp.pop(path, None); return False
    def mark_read(self, path):
        try:
            self._fp[path] = self._stat(path)
        except OSError:
            self._fp.pop(path, None)
        if len(self._fp) > self.MAX:
            for k in list(self._fp)[: len(self._fp) - self.MAX]:
                self._fp.pop(k, None)
    def mark_written(self, path): self.mark_read(path)
    def invalidate(self, path): self._fp.pop(path, None)
    def clear(self): self._fp.clear()

class RunDeduper:
    """命令去重：只拦与上一条完全相同 + 会话内写操作重复；观察类放行，上限 64。"""
    WRITE_VERBS = {'del', 'erase', 'rmdir', 'rd', 'remove-item', 'ri', 'mkdir', 'md',
                   'new-item', 'ni', 'move', 'move-item', 'copy', 'copy-item', 'cp',
                   'reg', 'regedit', 'regsvr32', 'setx', 'format', 'taskkill',
                   'stop-process', 'start-process', 'iex', 'invoke-expression', 'rm', 'rm-item'}
    def __init__(self, maxlen=64):
        self._last = None
        self._recent = collections.OrderedDict()
        self._max = maxlen
    @staticmethod
    def _unquoted_redirect(s):
        q = None
        for ch in s:
            if q:
                if ch == q: q = None
            elif ch in '"\'': q = ch
            elif ch == '>': return True
        return False
    def check(self, cmd):
        key = ' '.join(str(cmd).split()).lower()
        if '[console]::outputencoding' in key:
            return '后端已强制 UTF-8，命令里不要再设置编码；读文件请用 read_file（自动识别 UTF-8/GBK）。'
        norm = re.sub(r'chcp\s+65001\s*>?\s*nul\s*&?\s*', '', key).strip()
        first = norm.split(' ', 1)[0].strip('"\'').lstrip('./\\') if norm else ''
        is_write = (first in self.WRITE_VERBS) or self._unquoted_redirect(norm)
        if norm == self._last:
            return '与上一条命令完全相同，已拒绝；如需刷新结果请加参数或说明目的。'
        if is_write and norm in self._recent:
            return '该写命令本会话已执行过，已拦截；确需重跑请修改参数。'
        self._last = norm
        if is_write:
            self._recent[norm] = True
            if len(self._recent) > self._max: self._recent.popitem(last=False)
        return None
    def reset(self):
        self._last = None
        self._recent.clear()

# ===== 后端 API 版本标识 =====
API_VERSION = 'v1.0.0'

# 固定 WebView2 用户数据目录
_webview_data = os.path.join(os.path.expanduser('~'), '.glm-chat', 'webview_data')
os.makedirs(_webview_data, exist_ok=True)
os.environ['WEBVIEW2_USER_DATA_FOLDER'] = _webview_data

# 模块级运行时对象袋：绝不挂到 Api 实例上（防 pywebview 遍历 CLR 崩溃）
_RT = {'win': None, 'form': None, 'core': None,
       'last_bounds': None, 'ws_enabled': {}}

_load_session_ws()
_load_ws_enabled()

# ---- A1: 大工具输出落盘 ----
_TOOLCACHE_DIR = os.path.join(_CFG_DIR, 'toolcache')
_TOOLCACHE_MEM = {}
_TOOL_SEQ = [0]
_TOOL_SEQ_LOCK = threading.Lock()   # 修复 建议③：seq 自增非原子（多线程回调可重号撞文件）

def _cache_output(content):
    try:
        os.makedirs(_TOOLCACHE_DIR, exist_ok=True)
        with _TOOL_SEQ_LOCK:
            _TOOL_SEQ[0] += 1
            _seq = _TOOL_SEQ[0]
        cid = 'tc%d_%d' % (_seq, int(time.time()))
        fp = os.path.join(_TOOLCACHE_DIR, cid + '.txt')
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(str(content or ''))
        with _WS_LOCK:
            _TOOLCACHE_MEM[cid] = fp
            if len(_TOOLCACHE_MEM) > 40:
                old = sorted(_TOOLCACHE_MEM)[0]
                _TOOLCACHE_MEM.pop(old, None)
        return cid
    except Exception:
        return ''

class Api:
    def __init__(self):
        self.config_dir = _CFG_DIR
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_path = os.path.join(self.config_dir, 'config.json')
        self.cwd = self._load_workspace()
        self.file_fp = FileFingerprintCache()
        self.cmd_deduper = RunDeduper()
        self._append_hist = {}
        self._current_sid = None

    def clear_caches(self):
        self.file_fp.clear()
        self.cmd_deduper.reset()
        return 'ok'

    def _effective_root(self):
        if self._current_sid:
            with _WS_LOCK:
                return _SESSION_WS.get(self._current_sid, self.cwd)
        return self.cwd

    def _resolve_ws(self, path):
        if not _RT['ws_enabled'].get(self._current_sid or '', True):
            return None, json.dumps(
                {'error': '本会话已关闭"使用文件夹"，文件工具不可用。请直接回答用户问题，不要再尝试文件操作。'},
                ensure_ascii=False)
        root = os.path.abspath(self._effective_root())
        p = str(path if path is not None else '').strip().strip('"')
        if not p:
            return None, json.dumps({'error': '缺少 path 参数'}, ensure_ascii=False)
        if not p.startswith('\\\\') and p[0] in '\\/' and not (len(p) > 1 and p[1] == ':'):
            p = p.lstrip('\\/')
        if not os.path.isabs(p):
            p = os.path.join(root, p)
        abs_p = os.path.normcase(os.path.realpath(p))
        abs_root = os.path.normcase(os.path.realpath(root))
        if abs_p != abs_root and not abs_p.startswith(abs_root + os.sep):
            return None, json.dumps(
                {'error': f'路径越界：仅限工作区 {root} 内操作，请勿换路径重试；需要外部文件请让用户移入工作区。'},
                ensure_ascii=False)
        return abs_p, None

    def _short_path(self, abs_p):
        try:
            rel = os.path.relpath(abs_p, self._effective_root())
            if not rel.startswith('..'):
                return rel.replace('\\', '/')
        except Exception:
            pass
        return abs_p

    def save_workspace_file(self, name, text):
        d = os.path.join(self._effective_root(), 'attachments')
        os.makedirs(d, exist_ok=True)
        safe = re.sub(r'[\\/:*?<>|]', '_', str(name or 'attachment'))
        p = os.path.join(d, datetime.datetime.now().strftime('%Y%m%d_%H%M%S_') + safe)
        with open(p, 'w', encoding='utf-8', errors='replace') as f:
            f.write(str(text))
        return p

    def _load_workspace(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                ws = cfg.get('workspace')
                if ws and os.path.isdir(ws): return ws
        except Exception: pass
        desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
        if not os.path.exists(desktop): desktop = os.path.expanduser('~')
        ws = os.path.join(desktop, 'GLM-Workspace')
        os.makedirs(ws, exist_ok=True)
        return ws

    def _save_workspace(self):
        try:
            cfg = {}
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
            cfg['workspace'] = self.cwd
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False)
        except Exception: pass

    # ============ 配置 ============
    def get_config(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception: pass
        return '{}'

    def save_config(self, config_json):
        try:
            cfg = {}
            if os.path.exists(self.config_path):
                try:
                    with open(self.config_path, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)
                except Exception: cfg = {}
            try:
                incoming = json.loads(config_json)
                if isinstance(incoming, dict): cfg.update(incoming)
            except Exception: pass
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False)
            return '{"ok":true}'
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def get_sessions(self):
        path = os.path.join(self.config_dir, 'sessions.json')
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception: pass
        return '[]'

    def save_sessions(self, data):
        path = os.path.join(self.config_dir, 'sessions.json')
        try:
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(data)
            return '{"ok":true}'
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def set_workspace(self, path):
        try:
            if os.path.isdir(path):
                self.cwd = path
                self._save_workspace()
                return json.dumps({'ok': True, 'path': self.cwd}, ensure_ascii=False)
            return json.dumps({'error': f'目录不存在: {path}'}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def get_cwd(self):
        return self.cwd

    def get_api_info(self):
        try:
            exe_path = sys.executable if getattr(sys, 'frozen', False) else 'python(main.py)'
        except Exception:
            exe_path = 'unknown'
        methods = sorted(n for n in dir(self) if not n.startswith('_') and callable(getattr(self, n)))
        return json.dumps({'version': API_VERSION, 'exe': exe_path, 'methods': methods}, ensure_ascii=False)

    def rpc(self, name, payload_json='{}'):
        try: args = json.loads(payload_json or '{}')
        except Exception: args = {}
        if not isinstance(args, dict): args = {}
        name = str(name)
        func = getattr(self, name, None)
        if name == 'rpc' or name.startswith('_') or not callable(func):
            return json.dumps({'error': '未知方法: %s' % name}, ensure_ascii=False)
        try: return func(**args)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    # ============ 文件操作 ============
    @staticmethod
    def _decode_bytes(raw):
        if raw.startswith(b'\xef\xbb\xbf'):
            return raw.decode('utf-8-sig'), 'utf-8-sig'
        for enc in ('utf-8', 'gbk'):
            try: return raw.decode(enc), enc
            except UnicodeDecodeError: pass
        return raw.decode('utf-8', errors='replace'), 'utf-8'

    def list_dir(self, path=None):
        target, err = self._resolve_ws(path)
        if err: return err
        try:
            entries = []
            for item in os.listdir(target):
                full = os.path.join(target, item)
                is_dir = os.path.isdir(full)
                try: size = os.path.getsize(full)
                except OSError: size = -1
                entries.append({'name': item + ('/' if is_dir else ''), 'size': (None if is_dir else size)})
            entries.sort(key=lambda e: (not e['name'].endswith('/'), e['name'].lower()))
            if len(entries) > 200:
                return json.dumps({'path': target, 'entries': entries[:200], 'truncated': True,
                                   'total': len(entries),
                                   'hint': f'目录过大仅返回前 200 项（共 {len(entries)} 项，目录优先），请改用更精确的子路径',
                                   }, ensure_ascii=False)
            return json.dumps({'path': target, 'entries': entries}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def read_file(self, path, offset=0, limit=800, force=False):
        """读文本文件：带行号、兼容 GBK、二进制短路、路径猜错兜底"""
        try:
            path, err = self._resolve_ws(path)
            if err: return err
            try: offset = max(0, int(offset or 0))
            except Exception: offset = 0
            try: limit = max(50, min(int(limit or 800), 20000))          # 行上限 2000→20000
            except Exception: limit = 800
            if not force and offset == 0 and self.file_fp.unchanged(path):
                return json.dumps({'ok': True, 'path': self._short_path(path), 'unchanged': True,
                                   'note': '文件自上次读取后未变化，此前已完整读过，原文应仍在上文中；仅当上文中确实看不到原文时才带 force=true。'},
                                  ensure_ascii=False)
            if not os.path.exists(path):
                base = os.path.basename(path).lower()
                cand = []
                depth0 = self._effective_root().rstrip(os.sep).count(os.sep)
                for root, dirs, files in os.walk(self._effective_root()):
                    if root.count(os.sep) - depth0 >= 2:
                        dirs[:] = []; continue
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    cand.extend(files)
                    if len(cand) > 2000: break
                near = difflib.get_close_matches(base, [c.lower() for c in cand], n=1, cutoff=0.6)
                hint = ''
                if near:
                    for c in cand:
                        if c.lower() == near[0]:
                            hint = f'（最接近的文件: {c}，可用相对路径直接读取）'; break
                return json.dumps({'error': f'文件不存在: {path}{hint}'}, ensure_ascii=False)
            if os.path.isdir(path):
                return json.dumps({'error': f'路径是目录不是文件: {path}，列目录请用 list_dir'},
                                  ensure_ascii=False)
            raw = open(path, 'rb').read()
            if b'\x00' in raw[:8192]:
                return json.dumps({'path': path, 'binary': True,
                                   'info': '二进制文件，read_file 不适用；如需分析请用 run_powershell'},
                                  ensure_ascii=False)
            text, _enc = Api._decode_bytes(raw)
            lines = text.splitlines(keepends=True)
            total = len(lines)
            if offset >= total:
                return json.dumps({'ok': True, 'path': self._short_path(path), 'total_lines': total,
                                   'note': f'offset={offset} 已超出文件末尾（共 {total} 行）'}, ensure_ascii=False)
            seg = lines[offset: offset + limit]
            parts, used, shown = [], 0, 0
            BUDGET = 240000                                               # 字符预算 20000→240000
            for i, t in enumerate(seg):
                part = f'{offset + i + 1}\t{t}'
                if used + len(part) > BUDGET: break
                parts.append(part); used += len(part); shown += 1
            numbered = ''.join(parts)
            if shown < len(seg):
                numbered += '\n…(超大文件截断，可传 offset 继续读)'
            info = {'ok': True, 'path': self._short_path(path), 'total_lines': total, 'content': numbered}
            next_off = offset + shown                                     # 关键:按实际读到的行算,不再跳行
            if next_off < total:
                info['hint'] = f'还有 {total - next_off} 行未读，可传 offset={next_off} 继续读'
            if offset == 0 or next_off >= total:
                self.file_fp.mark_read(path)
            return json.dumps(info, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def write_file(self, path, content):
        try:
            path, err = self._resolve_ws(path)
            if err: return err
            if os.path.exists(path) and os.path.getsize(path) > 20000:
                return json.dumps(
                    {'error': '目标文件已存在且 >20KB。请改用 search_replace 局部修改；'
                              '确需整体重写，先 delete_path 删掉它再 write_file。'},
                    ensure_ascii=False)
            os.makedirs(os.path.dirname(path) or self.cwd, exist_ok=True)
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(content)
            self.file_fp.mark_written(path)
            self._append_hist.pop(path, None)
            return json.dumps({'ok': True, 'path': self._short_path(path),
                               'bytes': len(content.encode('utf-8'))}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def append_file(self, path, content):
        try:
            path, err = self._resolve_ws(path)
            if err: return err
            now = time.time()
            hist = [t for t in self._append_hist.get(path, []) if now - t < 600]
            hist.append(now)
            self._append_hist[path] = hist
            if len(hist) > 6:
                self._append_hist[path] = []
                return json.dumps(
                    {'error': 'append_file 已达频次上限（10 分钟 6 次），本次未写入，计数已重置。'
                              '请改用 write_file 一次性重写，或稍后再追加。'},
                    ensure_ascii=False)
            os.makedirs(os.path.dirname(path) or self.cwd, exist_ok=True)
            with open(path, 'a', encoding='utf-8', newline='') as f:
                f.write(content)
            self.file_fp.invalidate(path)
            return json.dumps({'ok': True, 'path': self._short_path(path),
                               'bytes': len(content.encode('utf-8'))}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def search_replace(self, path, old, new, replace_all=False):
        try:
            path, err = self._resolve_ws(path)
            if err: return err
            if os.path.isdir(path):
                return json.dumps({'error': f'路径是目录: {path}'}, ensure_ascii=False)
            if not os.path.exists(path):
                return json.dumps({'error': f'文件不存在: {path}，新建内容请用 write_file'},
                                  ensure_ascii=False)
            raw = open(path, 'rb').read()
            text, enc = Api._decode_bytes(raw)
            if old not in text:
                lines = text.splitlines()
                probe = (old.strip().splitlines() or [''])[0][:80]
                best_no, best_ratio, best_line = -1, 0.0, ''
                for i, l in enumerate(lines):
                    r = difflib.SequenceMatcher(None, probe, l.strip()[:80]).ratio()
                    if r > best_ratio:
                        best_ratio, best_no, best_line = r, i, l
                hint = f'；最相似内容在第 {best_no+1} 行: {best_line.strip()[:80]}' if best_ratio > 0.6 else ''
                return json.dumps({'error': f'未找到匹配内容: old 必须与文件原文逐字符一致{hint}'}, ensure_ascii=False)
            count = text.count(old)
            if count > 1 and not replace_all:
                return json.dumps({'error': f'匹配到 {count} 处，请提供更长上下文或传 replace_all=true'}, ensure_ascii=False)
            new_text = text.replace(old, new) if replace_all else text.replace(old, new, 1)
            with open(path, 'w', encoding=enc, errors='replace') as f:
                f.write(new_text)
            self.file_fp.invalidate(path)
            return json.dumps({'ok': True, 'path': self._short_path(path), 'replaced': count if replace_all else 1},
                              ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def make_dir(self, path):
        try:
            path, err = self._resolve_ws(path)
            if err: return err
            os.makedirs(path, exist_ok=True)
            return json.dumps({'ok': True, 'path': path}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def delete_path(self, path, recycle=True):
        try:
            path, err = self._resolve_ws(path)
            if err: return err
            p = path
            if p == os.path.abspath(self.cwd) or os.path.dirname(p) == p:
                return json.dumps({'error': '拒绝删除：工作目录本身或驱动器根目录'}, ensure_ascii=False)
            if not os.path.exists(p):
                return json.dumps({'error': f'路径不存在: {p}'}, ensure_ascii=False)
            send2trash_unavailable = False
            trash_broken = False
            if recycle:
                try:
                    from send2trash import send2trash
                    send2trash(p)
                    self.file_fp.invalidate(p)
                    return json.dumps({'ok': True, 'path': p, 'mode': '回收站'}, ensure_ascii=False)
                except ImportError:
                    send2trash_unavailable = True
                except Exception:
                    # 环境性回收站故障（send2trash 实现缺陷 / 8.3 短名被禁用 /
                    # 回收站被禁用 / pywin32 缺失的回退路径等）：该库存在
                    # 「先移动成功、后抛错」的实现——以文件是否仍在磁盘为准，
                    # 已消失即回收成功；确在磁盘的才回落永久删除。
                    if not os.path.exists(p):
                        self.file_fp.invalidate(p)
                        return json.dumps({'ok': True, 'path': p, 'mode': '回收站'}, ensure_ascii=False)
                    trash_broken = True
            if os.path.isdir(p): shutil.rmtree(p)
            else: os.remove(p)
            self.file_fp.invalidate(p)
            if send2trash_unavailable:
                mode = '永久删除(未装 send2trash，未进回收站)'
            elif trash_broken:
                mode = '永久删除(回收站暂不可用，未进回收站)'
            else:
                mode = '永久删除'
            return json.dumps({'ok': True, 'path': p, 'mode': mode}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def move_path(self, path, new_path):
        try:
            src, err = self._resolve_ws(path)
            if err: return err
            dst, err = self._resolve_ws(new_path)
            if err: return err
            if not os.path.exists(src):
                return json.dumps({'error': f'源不存在: {src}'}, ensure_ascii=False)
            if os.path.exists(dst):
                return json.dumps({'error': f'目标已存在: {dst}'}, ensure_ascii=False)
            os.makedirs(os.path.dirname(dst) or self.cwd, exist_ok=True)
            shutil.move(src, dst)
            self.file_fp.invalidate(src); self.file_fp.invalidate(dst)
            return json.dumps({'ok': True, 'src': src, 'dst': dst}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def copy_path(self, path, new_path):
        try:
            src, err = self._resolve_ws(path)
            if err: return err
            dst, err = self._resolve_ws(new_path)
            if err: return err
            if not os.path.exists(src):
                return json.dumps({'error': f'源不存在: {src}'}, ensure_ascii=False)
            if os.path.exists(dst):
                return json.dumps({'error': f'目标已存在: {dst}'}, ensure_ascii=False)
            if os.path.isdir(src): shutil.copytree(src, dst)
            else:
                os.makedirs(os.path.dirname(dst) or self.cwd, exist_ok=True)
                shutil.copy2(src, dst)
            return json.dumps({'ok': True, 'src': src, 'dst': dst}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def get_file_info(self, path):
        try:
            path, err = self._resolve_ws(path)
            if err: return err
            st = os.stat(path)
            return json.dumps({'path': path, 'is_dir': os.path.isdir(path), 'size': st.st_size,
                               'mtime': datetime.datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S')},
                              ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    # ============ 命令执行 ============
    def run_command(self, cmd, timeout=60):
        try:
            try: timeout = max(5, min(int(timeout or 60), 600))
            except Exception: timeout = 60
            result = subprocess.run('chcp 65001 >nul & ' + str(cmd), capture_output=True,
                                    shell=True, timeout=timeout, cwd=self._effective_root(),
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            def _dec(b):
                if not b: return ''
                s = b.decode('utf-8', 'replace')
                bad = s.count('\ufffd')
                if bad > max(3, len(s) // 200):
                    try:
                        s2 = b.decode('gbk', 'replace')
                        if s2.count('\ufffd') < bad: s = s2
                    except Exception: pass
                return s.replace('\r\r\n', '\r\n')   # 归一双换行 bug
            output = _dec(result.stdout)
            errtxt = _dec(result.stderr).strip()
            if errtxt: output += '\n[stderr] ' + errtxt
            if len(output) > 6000:
                cid = _cache_output(output)
                tip = ('id=%s, 用 read_more 分段获取' % cid) if cid else '全文未保留'
                output = output[:1500] + ('\n…[输出共 %d 字已截断;%s]…\n' % (len(output), tip)) + output[-800:]
            info = {'exit_code': result.returncode, 'output': output}
            if not output.strip(): info['note'] = '命令执行完毕，无任何输出'
            return json.dumps(info, ensure_ascii=False)
        except subprocess.TimeoutExpired:
            return json.dumps({'error': f'命令执行超时({timeout}s)'}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def run_powershell(self, cmd, timeout=60):
        try:
            try: timeout = max(5, min(int(timeout or 60), 600))
            except Exception: timeout = 60
            enc = ('[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;'
                   '$OutputEncoding=[System.Text.Encoding]::UTF8;')
            result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', enc + cmd],
                                    capture_output=True, timeout=timeout, cwd=self._effective_root(),
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            out = result.stdout.decode('utf-8', errors='replace').lstrip('\ufeff')
            err = result.stderr.decode('utf-8', errors='replace').strip()
            output = out + (('\n[stderr] ' + err) if err else '')
            if len(output) > 6000:
                cid = _cache_output(output)
                tip = ('id=%s, 用 read_more 分段获取' % cid) if cid else '全文未保留'
                output = output[:1500] + ('\n…[输出共 %d 字已截断;%s]…\n' % (len(output), tip)) + output[-800:]
            info = {'exit_code': result.returncode, 'output': output}
            if not output.strip(): info['note'] = '命令执行完毕，无任何输出'
            return json.dumps(info, ensure_ascii=False)
        except subprocess.TimeoutExpired:
            return json.dumps({'error': f'命令执行超时({timeout}s)'}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def run_admin_command(self, cmd):
        """管理员权限执行，括号包裹重定向，pid 临时文件防并发"""
        try:
            tip = self.cmd_deduper.check('[admin] ' + cmd)
            if tip:
                return json.dumps({'info': tip, 'skipped': True}, ensure_ascii=False)
            r = ctypes.windll.user32.MessageBoxW(
                0, f'AI 请求以管理员权限执行：\n\n{cmd}\n\n允许执行吗？',
                'GLM-Chat · 管理员确认', 0x04 | 0x30)
            if r != 6:
                return json.dumps({'info': '用户拒绝了本次管理员命令，请改用无需提权的方案。', 'skipped': True},
                                  ensure_ascii=False)
            # 修复 W4：临时文件仅按 pid 命名同进程并发必撞 → NamedTemporaryFile 唯一名；
            # 恒 exit 0 → .bat 包装透传真实退出码（%errorlevel% 在 cmd /c 单行是解析期展开）
            tmp_out = tmp_exit = tmp_bat = None
            try:
                fd, tmp_out = tempfile.mkstemp(prefix='glm_admin_out_', suffix='.txt'); os.close(fd)
                fd, tmp_exit = tempfile.mkstemp(prefix='glm_admin_exit_', suffix='.txt'); os.close(fd)
                fd, tmp_bat = tempfile.mkstemp(prefix='glm_admin_', suffix='.bat'); os.close(fd)
                os.remove(tmp_out); os.remove(tmp_exit)   # 让提权进程自己创建，避免旧内容误判
                with open(tmp_bat, 'w', encoding='mbcs', errors='replace', newline='') as _bf:
                    # newline=''：串内已内嵌 CRLF，默认文本翻译会二次翻译成 \r\r\n
                    _bf.write(f'{cmd} > "{tmp_out}" 2>&1\r\necho %errorlevel% > "{tmp_exit}"\r\n')
                ret = ctypes.windll.shell32.ShellExecuteW(None, 'runas', 'cmd', f'/c "{tmp_bat}"', None, 0)
                if ret <= 32:
                    return json.dumps({'error': f'授权失败，错误码 {ret}（可能用户拒绝了 UAC）'}, ensure_ascii=False)
                exit_code = None
                for _ in range(120):
                    # 完成信号：tmp_exit 出现且可解析为 int（原“大小不变即完成”会读半截输出）
                    try:
                        if os.path.exists(tmp_exit):
                            with open(tmp_exit, 'r', encoding='utf-8', errors='replace') as _ef:
                                exit_code = int(_ef.read().strip())
                            break
                    except Exception:
                        pass
                    time.sleep(0.5)
                raw = b''
                if os.path.exists(tmp_out):
                    with open(tmp_out, 'rb') as _of:
                        raw = _of.read()
                try: out = raw.decode('utf-8')
                except UnicodeDecodeError: out = raw.decode('gbk', errors='replace')
                out = out[:60000]
                if exit_code is None:
                    return json.dumps({'exit_code': None, 'output': out or '（命令已执行，输出读取超时，退出码未知）',
                                       'note': '已通过管理员权限执行'}, ensure_ascii=False)
                return json.dumps({'exit_code': exit_code, 'output': out, 'note': '已通过管理员权限执行'},
                                  ensure_ascii=False)
            finally:
                for _f in (tmp_out, tmp_exit, tmp_bat):
                    if _f and os.path.exists(_f):
                        try: os.remove(_f)
                        except Exception: pass
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    # ============ 剪贴板（v10.1-fix2: 写入回读校验 + 占用自动重试） ============
    def _clipboard_read(self):
        """内部读取, 返回 (str, None) 或 (None, 'busy')"""
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        if not u32.IsClipboardFormatAvailable(13):
            return '', None
        if not u32.OpenClipboard(0):
            return None, 'busy'
        try:
            h = u32.GetClipboardData(13)
            if not h:
                return '', None
            p = k32.GlobalLock(h)
            try:
                return (ctypes.c_wchar_p(p).value or ''), None
            finally:
                k32.GlobalUnlock(h)
        finally:
            u32.CloseClipboard()

    def get_clipboard(self):
        """读取系统剪贴板文本(占用时自动重试, 不再让调用方稍后再试)"""
        import time as _t
        try:
            for attempt in range(8):
                text, busy = self._clipboard_read()
                if text is not None:
                    return json.dumps({'ok': True, 'text': text[:30000],
                                       'len': len(text)}, ensure_ascii=False)
                _t.sleep(0.06)
            return json.dumps({'error': '剪贴板被持续占用, 请稍后再试'},
                              ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def set_clipboard(self, text):
        """写入系统剪贴板文本(写入后回读校验, 不一致自动重写, 保证 set→get 一致)"""
        import time as _t
        try:
            u32 = ctypes.windll.user32
            k32 = ctypes.windll.kernel32
            data = str(text if text is not None else '')
            size = (len(data) + 1) * 2
            head = data[:64]
            for attempt in range(6):
                h = k32.GlobalAlloc(0x0002, size)
                if not h:
                    return json.dumps({'error': '内存分配失败'}, ensure_ascii=False)
                p = k32.GlobalLock(h)
                try:
                    ctypes.memmove(p, ctypes.create_unicode_buffer(data), size)
                finally:
                    k32.GlobalUnlock(h)
                if not u32.OpenClipboard(0):
                    k32.GlobalFree(h)
                    _t.sleep(0.06)
                    continue
                try:
                    u32.EmptyClipboard()
                    u32.SetClipboardData(13, h)  # 所有权移交系统, 勿再 GlobalFree
                except Exception:
                    u32.CloseClipboard()
                    k32.GlobalFree(h)
                    _t.sleep(0.06)
                    continue
                u32.CloseClipboard()
                # ---- 回读校验: 等待剪贴板系统完成更新 ----
                for _ in range(6):
                    _t.sleep(0.03)
                    got, _busy = self._clipboard_read()
                    if got is not None and len(got) == len(data) and got[:64] == head:
                        return json.dumps({'ok': True, 'len': len(data),
                                           'verified': True}, ensure_ascii=False)
            return json.dumps({'ok': True, 'len': len(data), 'verified': False,
                               'note': '已写入但回读校验未通过, 可能被其他程序立即覆盖'},
                              ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    # ============ 进程（新增） ============
    def list_processes(self, keyword=None):
        """列出进程(按内存降序, 可选关键字过滤)，供 kill_process 使用"""
        try:
            r = subprocess.run(['tasklist', '/fo', 'csv', '/nh'],
                               capture_output=True, timeout=20,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            raw = r.stdout.decode('utf-8', 'replace')
            if '\ufffd' in raw:
                raw = r.stdout.decode('gbk', 'replace')
            procs = []
            for line in raw.splitlines():
                parts = [x.strip('"') for x in line.split('","')]
                if len(parts) < 5: continue
                name, pid, mem = parts[0], parts[1], parts[4]
                if keyword and keyword.lower() not in name.lower():
                    continue
                try: memv = int(mem.replace(',', '').replace('K', '').strip())
                except Exception: memv = 0
                procs.append((memv, name, pid))
            procs.sort(reverse=True)
            procs = procs[:120]
            lines = [f'{name}  pid={pid}  mem={memv // 1024}MB' for memv, name, pid in procs]
            return json.dumps({'ok': True, 'count': len(lines), 'processes': lines,
                               'note': '按内存占用降序，最多 120 条；结束进程用 kill_process'},
                              ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def kill_process(self, pid=None, name=None):
        try:
            if pid is not None:
                r = subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                                   capture_output=True, timeout=20,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
            elif name:
                r = subprocess.run(['taskkill', '/IM', str(name), '/T', '/F'],
                                   capture_output=True, timeout=20,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                return json.dumps({'error': '需要 pid 或 name 参数'}, ensure_ascii=False)
            out = r.stdout.decode('gbk', 'replace').strip() or r.stderr.decode('gbk', 'replace').strip()
            return json.dumps({'ok': r.returncode == 0, 'exit_code': r.returncode, 'output': out[:2000]},
                              ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    # ============ 其他 ============
    def get_memory(self):
        path = os.path.join(self.config_dir, 'memory.json')
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception: pass
        return '[]'

    def append_memory(self, entry_json):
        path = os.path.join(self.config_dir, 'memory.json')
        try:
            items = json.loads(self.get_memory())
            e = json.loads(entry_json) if isinstance(entry_json, str) else entry_json
            e['ts'] = datetime.datetime.now().strftime('%m-%d %H:%M')
            items.append(e)
            with open(path, 'w', encoding='utf-8', newline='') as f:
                json.dump(items[-200:], f, ensure_ascii=False)
            return '{"ok":true}'
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def set_current_sid(self, sid):
        self._current_sid = sid or None
        return '{"ok":true}'

    def set_session_ws(self, sid, path, enabled=True):
        if not sid:
            return json.dumps({'ok': False, 'error': '缺少 sid'}, ensure_ascii=False)
        with _WS_LOCK:
            if (not path) or (not enabled):
                _SESSION_WS.pop(sid, None)
            else:
                if not os.path.isdir(path):
                    return json.dumps({'ok': False, 'error': f'目录不存在: {path}'}, ensure_ascii=False)
                _SESSION_WS[sid] = os.path.abspath(path)
        _save_session_ws()
        try: self._touch_recent_ws(path or self.cwd)
        except Exception: pass
        ws = _SESSION_WS.get(sid, self.cwd)
        return json.dumps({'ok': True, 'sid': sid, 'ws': ws,
                           'bound': bool(_SESSION_WS.get(sid))}, ensure_ascii=False)

    def _touch_recent_ws(self, path):
        try:
            rec = []
            if os.path.exists(_RECENT_WS_FILE):
                with open(_RECENT_WS_FILE, 'r', encoding='utf-8') as f:
                    rec = json.load(f)
            rec = [r for r in rec if r.get('path') != path]
            rec.insert(0, {'path': path, 'name': os.path.basename(path) or path, 'ts': time.time()})
            with open(_RECENT_WS_FILE, 'w', encoding='utf-8') as f:
                json.dump(rec[:12], f, ensure_ascii=False, indent=1)
        except Exception: pass

    def list_recent_ws(self):
        try:
            with open(_RECENT_WS_FILE, 'r', encoding='utf-8') as f:
                return json.dumps(json.load(f), ensure_ascii=False)
        except Exception:
            return '[]'

    def get_session_ws(self, sid):
        with _WS_LOCK:
            ws = _SESSION_WS.get(sid or '', None)
        return json.dumps({'ws': ws or self.cwd, 'bound': bool(ws)}, ensure_ascii=False)

    def get_effective_ws(self):
        ws = self.cwd
        src = 'global'
        if self._current_sid:
            with _WS_LOCK:
                bound = _SESSION_WS.get(self._current_sid)
                if bound:
                    ws = bound; src = 'session'
        return json.dumps({'sid': self._current_sid, 'ws': ws, 'source': src,
                           'exists': bool(ws and os.path.isdir(ws))}, ensure_ascii=False)

    def set_ws_enabled(self, sid, enabled):
        _RT['ws_enabled'][sid or ''] = bool(enabled)
        _save_ws_enabled()
        return json.dumps({'ok': True, 'enabled': bool(enabled)}, ensure_ascii=False)

    def get_ws_enabled(self, sid):
        v = _RT['ws_enabled'].get(sid or '', True)
        return json.dumps({'enabled': bool(v)}, ensure_ascii=False)

    def get_ws_state(self, sid):
        with _WS_LOCK:
            ws = _SESSION_WS.get(sid or '', None)
        recent = []
        try:
            with open(_RECENT_WS_FILE, 'r', encoding='utf-8') as f:
                recent = json.load(f)
            if not isinstance(recent, list): recent = []
        except Exception:
            recent = []
        return json.dumps({'ws': ws or self.cwd, 'bound': bool(ws),
                           'enabled': bool(_RT['ws_enabled'].get(sid or '', True)),
                           'recent': recent[:8]}, ensure_ascii=False)

    def set_ws_dir(self, path):
        """全局目录切换：用户操作，不走 _resolve_ws 守卫"""
        if not path or not os.path.isdir(path):
            return json.dumps({'ok': False, 'error': '目录不存在'}, ensure_ascii=False)
        self.cwd = os.path.abspath(path)
        try: self._touch_recent_ws(self.cwd)
        except Exception: pass
        return json.dumps({'ok': True, 'ws': self.cwd}, ensure_ascii=False)

    def delete_session_ws(self, sid):
        sid = sid or ''
        with _WS_LOCK:
            _SESSION_WS.pop(sid, None)
        _RT['ws_enabled'].pop(sid, None)
        _save_session_ws()
        _save_ws_enabled()
        return '{"ok":true}'

    def pick_folder(self, sid=None):
        """pywebview 原生 create_file_dialog 选目录（比 tkinter 更可靠）"""
        try:
            wins = webview.windows
            if not wins:
                return json.dumps({'ok': False, 'err': 'no window'}, ensure_ascii=False)
            picked = wins[0].create_file_dialog(webview.FOLDER_DIALOG)
            if not picked:
                return json.dumps({'ok': False, 'err': 'cancelled'}, ensure_ascii=False)
            path = picked if isinstance(picked, str) else picked[0]
            return json.dumps({'ok': True, 'path': path}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'ok': False, 'err': f'{type(e).__name__}: {e}'}, ensure_ascii=False)

    def copy_into_ws(self, src, name):
        try:
            if not src or not os.path.isfile(src):
                return json.dumps({'error': f'文件不存在: {src}'}, ensure_ascii=False)
            root = self._effective_root()
            adir = os.path.join(root, 'attachments')
            os.makedirs(adir, exist_ok=True)
            base = datetime.datetime.now().strftime('%H%M%S_') + (name or os.path.basename(src))
            dst = os.path.join(adir, base)
            shutil.copyfile(src, dst)
            return json.dumps({'ok': True, 'path': dst}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def _worklog_path(self):
        sid = getattr(self, '_current_sid', None)
        root = self.cwd
        if sid:
            with _WS_LOCK:
                root = _SESSION_WS.get(sid, self.cwd)
        return os.path.join(root, '_glm_worklog.md')

    def get_worklog(self):
        try:
            p = self._worklog_path()
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8', errors='replace') as f:
                    return f.read()
        except Exception: pass
        return ''

    def append_worklog(self, text):
        try:
            p = self._worklog_path()
            ts = datetime.datetime.now().strftime('%m-%d %H:%M')
            line = f'- [{ts}] {str(text)[:500]}\n'
            with open(p, 'a', encoding='utf-8') as f:
                f.write(line)
            return '{"ok":true}'
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def open_billing(self):
        import webbrowser
        webbrowser.open('https://bigmodel.cn/usercenter/billing')
        return '{"ok":true}'

    def open_app(self, path):
        try:
            path = str(path or '').strip()
            import re as _re
            if _re.match(r'^https?://', path):
                import webbrowser
                webbrowser.open(path)
                return json.dumps({'ok': True, 'path': path}, ensure_ascii=False)
            if not os.path.isabs(path):
                found = shutil.which(path)
                if found: path = found
                else: path = os.path.join(self._effective_root(), path)
            os.startfile(path)
            return json.dumps({'ok': True, 'path': path}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def open_url(self, url):
        """用默认浏览器打开网页"""
        try:
            import webbrowser
            import re as _re
            u = str(url or '').strip()
            if not u:
                return json.dumps({'error': '缺少 url 参数'}, ensure_ascii=False)
            if not _re.match(r'^https?://', u):
                u = 'https://' + u
            webbrowser.open(u)
            return json.dumps({'ok': True, 'url': u}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    def take_screenshot(self, left=None, top=None, width=None, height=None):
        """截屏；可传区域 left/top/width/height；存配置目录（不污染工作区）+ 返回 base64 给前端"""
        try:
            from PIL import ImageGrab
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
            shots_dir = os.path.join(_CFG_DIR, 'screenshots')
            os.makedirs(shots_dir, exist_ok=True)
            path = os.path.join(shots_dir, f'screenshot_{ts}.png')
            try:
                if None not in (left, top, width, height):
                    img = ImageGrab.grab(bbox=(int(left), int(top),
                                               int(left) + int(width), int(top) + int(height)),
                                         all_screens=True)
                else:
                    img = ImageGrab.grab(all_screens=True)
            except TypeError:
                img = ImageGrab.grab()
            img.save(path)
            buf = io.BytesIO()
            img.convert('RGB').save(buf, format='JPEG', quality=85)
            b64 = base64.b64encode(buf.getvalue()).decode()
            return json.dumps({'ok': True, 'path': path, 'size': img.size,
                               'dataUrl': 'data:image/jpeg;base64,' + b64}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e) + '（需要 Pillow）'}, ensure_ascii=False)

    # ---- A1: 大工具输出落盘 ----
    def cache_tool_output(self, content):
        cid = _cache_output(content)
        if not cid:
            return json.dumps({'ok': False, 'error': '落盘失败'}, ensure_ascii=False)
        return json.dumps({'ok': True, 'id': cid}, ensure_ascii=False)

    def read_more(self, cache_id, offset=0, limit=400):
        try:
            fp = _TOOLCACHE_MEM.get(str(cache_id or ''))
            if not fp or not os.path.exists(fp):
                return json.dumps({'error': '缓存不存在或已清理，请重新执行原命令获取'}, ensure_ascii=False)
            with open(fp, 'r', encoding='utf-8') as f:
                lines = f.read().splitlines()
            off = max(0, int(offset or 0))
            lim = max(20, min(int(limit or 400), 2000))
            part = lines[off:off + lim]
            if not part:
                return json.dumps({'error': f'offset 超出范围，共 {len(lines)} 行'}, ensure_ascii=False)
            body = '\n'.join(part)
            if off + lim < len(lines):
                body += ('\n…[第 %d-%d 行 / 共 %d 行；续读 read_more(cache_id="%s", offset=%d)]'
                         % (off + 1, off + len(part), len(lines), cache_id, off + len(part)))
            return json.dumps({'ok': True, 'total_lines': len(lines), 'content': body}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    # ---- A3: 精简 System Prompt ----
    def build_system_prompt(self):
        root = self._effective_root()
        return json.dumps(
            '你是 GLM-Chat 内置编程助手。当前工作区: ' + root + '\n'
            '硬规则:\n'
            '1. 文件操作只用工具, 禁止用 Get-Content/Set-Content(后端已强制 UTF-8)。\n'
            '2. 写文件串行: 一次一个 write_file/append_file/search_replace, 等返回成功再写下一个。\n'
            '3. 超长命令输出会截断并给缓存 id, 需要全文用 read_more 分段取。\n'
            '4. 系统能力: 截屏 take_screenshot(可传 left/top/width/height 区域), '
            '剪贴板 get_clipboard/set_clipboard, 进程 list_processes→kill_process(杀前先确认), 打开网页 open_url。',
            ensure_ascii=False)

    # ---- A4: 工具 schema 按权限档动态构建（补全全部 17 个） ----
    _S_READ_MORE = {'type': 'function', 'function': {'name': 'read_more',
        'description': '分页读取之前被截断的工具输出全文',
        'parameters': {'type': 'object', 'properties': {
            'cache_id': {'type': 'string'}, 'offset': {'type': 'integer'},
            'limit': {'type': 'integer'}}, 'required': ['cache_id']}}}

    def build_tools(self, role='full'):
        ws_on = _RT['ws_enabled'].get(self._current_sid or '', True)
        if role == 'chat':
            return json.dumps([], ensure_ascii=False)
        tools = [dict(self._S_READ_MORE)]
        if role == 'full':
            if ws_on:
                tools += [
                    {'type': 'function', 'function': {'name': 'read_file',
                        'description': '读文件(带行号,一次可读2万行,常规文件一次读全;同版本重复读被拦截,需原文传force=true)',
                        'parameters': {'type': 'object', 'properties': {
                            'path': {'type': 'string'}, 'offset': {'type': 'integer'},
                            'limit': {'type': 'integer'}, 'force': {'type': 'boolean'}},
                            'required': ['path']}}},
                    {'type': 'function', 'function': {'name': 'write_file',
                        'description': '整文件写入(UTF-8)。已存在且>20KB 会被拒,改用 search_replace',
                        'parameters': {'type': 'object', 'properties': {
                            'path': {'type': 'string'}, 'content': {'type': 'string'}},
                            'required': ['path', 'content']}}},
                    {'type': 'function', 'function': {'name': 'append_file',
                        'description': '追加到文件末尾。10 分钟内同文件限 6 次',
                        'parameters': {'type': 'object', 'properties': {
                            'path': {'type': 'string'}, 'content': {'type': 'string'}},
                            'required': ['path', 'content']}}},
                    {'type': 'function', 'function': {'name': 'search_replace',
                        'description': '精确原文局部替换,优先于整文件重写',
                        'parameters': {'type': 'object', 'properties': {
                            'path': {'type': 'string'}, 'old': {'type': 'string'},
                            'new': {'type': 'string'}, 'replace_all': {'type': 'boolean'}},
                            'required': ['path', 'old', 'new']}}},
                    {'type': 'function', 'function': {'name': 'list_dir',
                        'description': '列目录,超过 200 项只回前 200+总数',
                        'parameters': {'type': 'object', 'properties': {
                            'path': {'type': 'string'}}, 'required': ['path']}}},
                    {'type': 'function', 'function': {'name': 'make_dir',
                        'description': '创建文件夹',
                        'parameters': {'type': 'object', 'properties': {
                            'path': {'type': 'string'}}, 'required': ['path']}}},
                    {'type': 'function', 'function': {'name': 'delete_path',
                        'description': '删除文件/目录(进回收站)',
                        'parameters': {'type': 'object', 'properties': {
                            'path': {'type': 'string'}}, 'required': ['path']}}},
                    {'type': 'function', 'function': {'name': 'move_path',
                        'description': '移动/重命名',
                        'parameters': {'type': 'object', 'properties': {
                            'path': {'type': 'string'}, 'new_path': {'type': 'string'}},
                            'required': ['path', 'new_path']}}},
                    {'type': 'function', 'function': {'name': 'copy_path',
                        'description': '复制文件/目录',
                        'parameters': {'type': 'object', 'properties': {
                            'path': {'type': 'string'}, 'new_path': {'type': 'string'}},
                            'required': ['path', 'new_path']}}},
                    {'type': 'function', 'function': {'name': 'get_file_info',
                        'description': '文件大小/修改时间',
                        'parameters': {'type': 'object', 'properties': {
                            'path': {'type': 'string'}}, 'required': ['path']}}},
                ]
            tools += [
                {'type': 'function', 'function': {'name': 'run_command',
                    'description': '执行 cmd 命令,输出超长自动截断落盘',
                    'parameters': {'type': 'object', 'properties': {
                        'cmd': {'type': 'string'}, 'timeout': {'type': 'integer'}},
                        'required': ['cmd']}}},
                {'type': 'function', 'function': {'name': 'run_powershell',
                    'description': '执行 PowerShell 命令,输出超长自动截断落盘',
                    'parameters': {'type': 'object', 'properties': {
                        'cmd': {'type': 'string'}, 'timeout': {'type': 'integer'}},
                        'required': ['cmd']}}},
                {'type': 'function', 'function': {'name': 'run_admin_command',
                    'description': '管理员权限命令,会弹原生确认框',
                    'parameters': {'type': 'object', 'properties': {
                        'cmd': {'type': 'string'}}, 'required': ['cmd']}}},
                {'type': 'function', 'function': {'name': 'open_app',
                    'description': '打开软件/文件/文件夹',
                    'parameters': {'type': 'object', 'properties': {
                        'path': {'type': 'string'}}, 'required': ['path']}}},
                {'type': 'function', 'function': {'name': 'open_url',
                    'description': '用默认浏览器打开网页',
                    'parameters': {'type': 'object', 'properties': {
                        'url': {'type': 'string'}}, 'required': ['url']}}},
                {'type': 'function', 'function': {'name': 'take_screenshot',
                    'description': '截取当前屏幕; 可选区域参数 left/top/width/height',
                    'parameters': {'type': 'object', 'properties': {
                        'left': {'type': 'integer'}, 'top': {'type': 'integer'},
                        'width': {'type': 'integer'}, 'height': {'type': 'integer'}}}}},
                {'type': 'function', 'function': {'name': 'clipboard_read',
                    'description': '读取系统剪贴板文本',
                    'parameters': {'type': 'object', 'properties': {}}}},
                {'type': 'function', 'function': {'name': 'clipboard_write',
                    'description': '写入系统剪贴板文本',
                    'parameters': {'type': 'object', 'properties': {
                        'text': {'type': 'string'}}, 'required': ['text']}}},
                {'type': 'function', 'function': {'name': 'list_processes',
                    'description': '列出进程(按内存降序, 可关键字过滤), 配合 kill_process',
                    'parameters': {'type': 'object', 'properties': {
                        'keyword': {'type': 'string'}}, 'required': []}}},
                {'type': 'function', 'function': {'name': 'kill_process',
                    'description': '结束进程(按 pid 或进程名), 请先 list_processes 确认再杀',
                    'parameters': {'type': 'object', 'properties': {
                        'pid': {'type': 'integer'}, 'name': {'type': 'string'}},
                        'required': []}}},
                {'type': 'function', 'function': {'name': 'append_memory',
                    'description': '写入跨会话长期记忆',
                    'parameters': {'type': 'object', 'properties': {
                        'content': {'type': 'string'}}, 'required': ['content']}}},
            ]
        elif role == 'ro':
            if ws_on:
                tools += [
                    {'type': 'function', 'function': {'name': 'read_file',
                        'description': '读文件片段(带行号)',
                        'parameters': {'type': 'object', 'properties': {
                            'path': {'type': 'string'}, 'offset': {'type': 'integer'},
                            'limit': {'type': 'integer'}, 'force': {'type': 'boolean'}},
                            'required': ['path']}}},
                    {'type': 'function', 'function': {'name': 'list_dir',
                        'description': '列目录',
                        'parameters': {'type': 'object', 'properties': {
                            'path': {'type': 'string'}}, 'required': ['path']}}},
                    {'type': 'function', 'function': {'name': 'get_file_info',
                        'description': '文件大小/修改时间',
                        'parameters': {'type': 'object', 'properties': {
                            'path': {'type': 'string'}}, 'required': ['path']}}},
                ]
            tools += [
                {'type': 'function', 'function': {'name': 'run_powershell',
                    'description': '执行 PowerShell 命令',
                    'parameters': {'type': 'object', 'properties': {
                        'cmd': {'type': 'string'}}, 'required': ['cmd']}}},
                {'type': 'function', 'function': {'name': 'open_app',
                    'description': '打开软件/文件',
                    'parameters': {'type': 'object', 'properties': {
                        'path': {'type': 'string'}}, 'required': ['path']}}},
                {'type': 'function', 'function': {'name': 'take_screenshot',
                    'description': '截取当前屏幕',
                    'parameters': {'type': 'object', 'properties': {}}}},
                {'type': 'function', 'function': {'name': 'clipboard_read',
                    'description': '读取系统剪贴板文本',
                    'parameters': {'type': 'object', 'properties': {}}}},
                {'type': 'function', 'function': {'name': 'list_processes',
                    'description': '列出进程(按内存降序)',
                    'parameters': {'type': 'object', 'properties': {
                        'keyword': {'type': 'string'}}, 'required': []}}},
                {'type': 'function', 'function': {'name': 'append_memory',
                    'description': '写入跨会话长期记忆',
                    'parameters': {'type': 'object', 'properties': {
                        'content': {'type': 'string'}}, 'required': ['content']}}},
            ]
        return json.dumps(tools, ensure_ascii=False)

def get_html_path():
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'glm-chat.html')

# 修复 W5：模块级副作用（import 即建窗并 webview.start() 阻塞/弹窗）收进 main()，
# 仅 __main__ 执行；测试/工具链 import 本模块（如契约差分测试）不再触发窗口。
def _write_api_log(api):
    try:
        try:
            src = os.path.abspath(__file__)
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(src)).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            src, mtime = 'unknown', 'unknown'
        try:
            exe_path = sys.executable if getattr(sys, 'frozen', False) else 'python(main.py)'
        except Exception:
            exe_path = 'unknown'
        methods = sorted(n for n in dir(api) if not n.startswith('_') and callable(getattr(api, n)))
        with open(os.path.join(api.config_dir, 'api_methods.log'), 'w', encoding='utf-8') as f:
            f.write('api_version : %s\n' % API_VERSION)
            f.write('exe_path    : %s\n' % exe_path)
            f.write('main_src    : %s (%s)\n' % (src, mtime))
            f.write('started_at  : %s\n' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            f.write('methods     : %s\n' % ', '.join(methods))
    except Exception:
        pass

def main():
    html_path = get_html_path()
    api = Api()
    _write_api_log(api)

    window = webview.create_window(
        'GLM Chat [' + API_VERSION + ']',
        url=html_path,
        js_api=api,
        width=1180,
        height=800,
        min_size=(860, 620),
    )
    _RT['win'] = window  # U1 修复：Window 引用放对象袋，不挂 Api 实例
    window.events.loaded += _enable_context_menu
    webview.start()

def _enable_context_menu():
    """强制开启 WebView2 右键菜单（pywebview 非 debug 模式默认关闭）。
    CoreWebView2 只能在 UI 线程访问；loaded 回调在后台线程，
    必须 BeginInvoke 切回 UI 线程，否则报
    'CoreWebView2 can only be accessed from the UI thread' / E_NOINTERFACE。"""
    try:
        form = _RT['win'].native
        if form is None:
            print('[ctxmenu] 窗口未就绪，前端自定义右键菜单兜底')
            return

        def _find_ctrl():
            # 只能在 UI 线程里找控件、读属性
            for name in ('web_view', 'webview', 'webView'):
                ctrl = getattr(form, name, None)
                if ctrl is not None:
                    return ctrl
            try:
                for c in form.Controls:
                    if 'WebView2' in c.GetType().FullName:
                        return c
            except Exception:
                pass
            return None

        def _ui_work():
            try:
                ctrl = _find_ctrl()
                core = getattr(ctrl, 'CoreWebView2', None) if ctrl is not None else None
                if core is None:
                    print('[ctxmenu] CoreWebView2 暂不可用，前端自定义右键菜单兜底')
                    return
                core.Settings.AreDefaultContextMenusEnabled = True
                core.Settings.AreDevToolsEnabled = True
                print('[ctxmenu] 原生右键菜单已开启')
            except Exception as e:
                print('[ctxmenu] UI 线程内开启失败，前端自定义右键菜单兜底:', e)

        from System import Action
        form.BeginInvoke(Action(_ui_work))
    except Exception as e:
        print('[ctxmenu] 开启失败，前端自定义右键菜单兜底:', e)

if __name__ == '__main__':
    main()