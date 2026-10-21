# -*- coding: utf-8 -*-
"""v1.8.0 B 域·搜索窗口通道（实现 v1.8.0 B2：pywebview 次窗 + urllib 兜底双通道）。

模块职责（架构文档 §2.1 后端模块表「窗口通道 search_browser」）：
- 次窗口生命周期：680×520 隐藏备用、``load_url`` 加载、``events.loaded``
  加载事件、8s 看门狗、独立 UserDataFolder（``~/.glm-chat/search_webview``）、
  禁 file:// 等非 http(s) 导航、空闲 60s 回收；
- 注入模式：``set_window(win)``（installer_gui InstallerBridge 同款）——由
  main.py 装配入口注入预先创建的次窗；未注入时按需惰性创建（嵌入/测试环境）；
- ``open_url(url)`` 双通道取数（联调规范 §5.1③ 降级链）：
  次窗路径（load_url → loaded 事件 → evaluate_js 读 DOM）优先，窗口不可用 /
  超时 / evaluate_js 无法泵送（本沙箱环境两次实证的已知限制）时自动回落
  urllib 抓 HTML 兜底（复用 ``mcp_transport_http.urlopen_no_redirect``，
  禁自动重定向），响应以 ``channel`` 标注实际通道（'window'|'urllib'）。

纯 IO 边界：本模块是搜索栈唯一直接触网的模块（urllib），窗口操作经 pywebview；
``import`` 无副作用（webview 延迟导入），可在无 GUI 环境导入与单测。
"""
import ipaddress
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .. import paths
from ..logging_setup import get_logger
from .mcp_transport_http import urlopen_no_redirect

# 次窗形态（架构 §2.1：680×520 次窗）
WINDOW_WIDTH = 680
WINDOW_HEIGHT = 520
# 加载看门狗（ux-flows 流程 1 步骤 4：≤8s 轮询等待）
LOAD_TIMEOUT_SECONDS = 8.0
# evaluate_js 读 DOM 的线程 join 上限（沙箱无法泵送时不能挂死调用方）
READ_DOM_TIMEOUT_SECONDS = 5.0
# 空闲回收（架构 §2.1：空闲 60s 回收）
IDLE_RECYCLE_SECONDS = 60.0
_RECYCLE_TICK_SECONDS = 5.0
# urllib 兜底：响应体防 OOM 上限（结果页/文章页 HTML 2MB 足够）
MAX_HTML_BYTES = 2 * 1024 * 1024
# 浏览器 UA（引擎反爬对抗的基础形态，非伪装——Harbor 自报家门）
USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
              'Harbor/1.8.0 (SearchBrowser; +https://harbor.local)')

# 独立 WebView2 用户数据目录（架构 §2.1：独立 profile，与主窗 webview_data 隔离）
USER_DATA_DIR_NAME = 'search_webview'

# 禁导航协议（R2 纪律：仅 http/https；file:// / javascript: / about: 等一律拒绝）
_ALLOWED_SCHEME = re.compile(r'^https?://', re.IGNORECASE)


def _is_public_host(host):
    """host 是否解析到公网地址（SSRF 防护；ipaddress + getaddrinfo）。

    拒绝 private / loopback / link_local / reserved / multicast / unspecified
    （含 127/8、10/8、192.168/16、169.254/16、::1、fe80::/10、fc00::/7 等）——
    防搜索窗口/直连被抓包成本内网探测代理（browser_open 可被诱导访问
    元数据端点 169.254.169.254 或内网管理口）。

    口径（2026-10-21 修订）：字面 IP 直接判定；域名解析成功且全部落私网段
    → 拒绝；**解析失败放行**——本机 DNS 瞬时不可用时若 fail-closed 会误杀
    全部正常搜索（fetch 会经同一解析器自然失败，拦截无增益），且令调用方
    依赖实时 DNS 产生抖动。已知边界：DNS rebinding（检查时公网、抓取时
    私网）不在此威胁模型内。
    """
    h = str(host or '').strip().lower().rstrip('.')
    if not h:
        return False
    # 字面 IP（v4/v6，可带 zone id）：不触 DNS，直接判定
    try:
        ip = ipaddress.ip_address(h.split('%', 1)[0])
        return not (ip.is_private or ip.is_loopback or ip.is_link_local or
                    ip.is_reserved or ip.is_multicast or ip.is_unspecified)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(h, None)
    except Exception:
        return True        # DNS 失败：放行（fetch 经同一解析器自然失败）
    saw_addr = False
    for info in infos:
        addr = str(info[4][0]).split('%', 1)[0]   # 去 zone id（fe80::1%eth0）
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        saw_addr = True
        if ip.is_private or ip.is_loopback or ip.is_link_local or \
                ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return saw_addr


class SearchBrowser:
    """搜索次窗通道：``open_url(url)`` → ``{ok, html, channel, error?}``。

    双通道语义（联调规范 §5.1③）：
    - ``channel='window'``：次窗 load_url + loaded 事件 + evaluate_js 读 DOM；
    - ``channel='urllib'``：窗口不可用 / 超时 / 读 DOM 失败时的兜底直连抓取；
    - 双失败 → ``{ok: False, error: 'ENGINE_UNREACHABLE'|'TIMEOUT'|'NAV_BLOCKED'}``。

    Attributes:
        window: 当前次窗引用（注入或惰性创建；空闲回收后为 None）。
    """

    def __init__(self, user_data_dir=None, idle_recycle=True):
        """Args:
            user_data_dir: 独立 WebView2 profile 目录（缺省 ``~/.glm-chat/search_webview``）。
            idle_recycle: 是否启用空闲 60s 回收（测试可关，避免回收线程干扰）。
        """
        self._log = get_logger()
        self._win = None
        self._user_data_dir = (user_data_dir
                               or os.path.join(paths.CONFIG_DIR, USER_DATA_DIR_NAME))
        self._last_used = 0.0
        self._lock = threading.RLock()
        self._recycler = None
        self._stop_evt = threading.Event()
        self._idle_recycle = bool(idle_recycle)
        # evaluate_js 可泵送性（首次 join 超时即置 False：后续 open_url 跳过
        # 窗口路径直接走 urllib，不再养僵尸线程——沙箱实证限制）
        self._dom_pumpable = True

    # ---------------- 窗口装配（注入模式，installer_gui InstallerBridge 同款） ----------------

    def set_window(self, win):
        """注入次窗引用（main.py 装配入口调用；替换既有引用并刷新活跃时间）。"""
        with self._lock:
            self._win = win
            self._last_used = time.monotonic()

    @property
    def window(self):
        with self._lock:
            return self._win

    def _ensure_window(self):
        """取当前次窗；无注入时惰性创建（隐藏备用，pywebview 延迟导入）。

        Returns:
            窗口对象或 None（webview 不可用/创建失败——调用方据此走 urllib）。
        """
        with self._lock:
            win = self._win
            if win is not None:
                return win
        try:
            import webview   # 延迟导入：无 webview 环境（测试/嵌入）不炸
        except Exception as e:
            self._log.debug('webview 不可用，搜索走 urllib 兜底: %r', e)
            return None
        try:
            os.makedirs(self._user_data_dir, exist_ok=True)
        except Exception as e:
            self._log.debug('搜索 profile 目录创建失败（回落进程级目录）: %r', e)
        win = None
        # 创建参数阶梯：完整参数（含 hidden/user_data_folder）→ 去 user_data_folder
        # → 最小参数。pywebview 各版本 create_window 签名有差异，全部 try 兜底。
        attempts = (
            {'title': 'Harbor 搜索', 'url': 'about:blank', 'js_api': None,
             'width': WINDOW_WIDTH, 'height': WINDOW_HEIGHT, 'hidden': True,
             'user_data_folder': self._user_data_dir},
            {'title': 'Harbor 搜索', 'url': 'about:blank', 'js_api': None,
             'width': WINDOW_WIDTH, 'height': WINDOW_HEIGHT, 'hidden': True},
            {'title': 'Harbor 搜索', 'url': 'about:blank',
             'width': WINDOW_WIDTH, 'height': WINDOW_HEIGHT},
        )
        for kw in attempts:
            try:
                win = webview.create_window(**kw)
                break
            except TypeError:
                continue   # 该版本不支持此参数组合，降级重试
            except Exception as e:
                self._log.warning('搜索次窗创建失败（回落 urllib 兜底）: %r', e)
                return None
        if win is None:
            self._log.warning('搜索次窗创建失败（参数均不被接受，回落 urllib 兜底）')
            return None
        with self._lock:
            self._win = win
            self._last_used = time.monotonic()
        return win

    # ---------------- 取数主入口 ----------------

    def open_url(self, url):
        """打开 URL 取 HTML（双通道：次窗优先，urllib 自动兜底）。

        Args:
            url: 目标 URL（仅 http/https；其他协议直接 NAV_BLOCKED，不导航）。

        Returns:
            dict: 成功 ``{ok: True, html: str, channel: 'window'|'urllib'}``；
            失败 ``{ok: False, error: 错误码, message: 人话, hint?}``。
            错误码：``BAD_PARAMS`` / ``NAV_BLOCKED`` / ``TIMEOUT`` /
            ``ENGINE_UNREACHABLE`` / ``WINDOW_UNAVAILABLE``（内部码，回落前用）。
        """
        u = str(url or '').strip()
        if not u:
            return {'ok': False, 'error': 'BAD_PARAMS', 'message': 'url 不能为空'}
        if not _ALLOWED_SCHEME.match(u):
            # R2 纪律：禁导航在通道层硬拦（窗口与 urllib 之前），file:// 等无机会触达
            return {'ok': False, 'error': 'NAV_BLOCKED',
                    'message': '已阻止非 http(s) 导航: %s' % u[:80],
                    'hint': '浏览器搜索/打开仅支持 http/https 链接'}
        # 内网防护（SSRF）：解析目标 host，私网/环回/链路本地等一律拒绝
        #（DNS 解析失败按拒绝——fail-closed；helper 与 search_service.browser_open 共用）
        host = urllib.parse.urlsplit(u).hostname
        if not _is_public_host(host):
            return {'ok': False, 'error': 'NAV_BLOCKED',
                    'message': '已阻止访问内网/环回地址: %s' % u[:80],
                    'hint': '禁止访问内网/环回地址'}
        self._touch()
        self._start_recycler()
        if self._dom_pumpable:
            win = self._ensure_window()
            if win is not None:
                r = self._load_via_window(win, u)
                if r.get('ok'):
                    r['channel'] = 'window'
                    return r
                # 降级链（规范 §5.1③）：窗口超时/不可用/读 DOM 失败 → urllib 兜底。
                # 机制静默（不阻塞主流程），降级事实由响应 channel='urllib' 标注。
                self._log.info('搜索次窗路径失败（%s），回落 urllib: %s',
                               r.get('error'), u[:80])
        r = self._fetch_via_urllib(u)
        r['channel'] = 'urllib'
        return r

    # ---------------- 次窗路径 ----------------

    def _load_via_window(self, win, url):
        """次窗 load_url → 等 loaded 事件（8s 看门狗）→ evaluate_js 读 DOM。

        evaluate_js 经工作线程 join 调用（本沙箱会话无法被消息循环泵送——
        两次实证的已知限制）：join 超时/异常/空结果一律视为窗口路径失败，
        由 open_url 回落 urllib（回落路径必须真跑通）。
        """
        loaded = threading.Event()

        def _on_loaded():
            loaded.set()

        # 先订阅再导航：load_url 之后 loaded 可能同步/极快触发（缓存页/
        # about:blank 跳转），后订阅会漏事件 → 白等 8s 看门狗超时
        events = getattr(win, 'events', None)
        subscribed = False
        if events is not None and getattr(events, 'loaded', None) is not None:
            try:
                events.loaded += _on_loaded
                subscribed = True
            except Exception:
                subscribed = False
        try:
            win.load_url(url)
        except Exception as e:
            return {'ok': False, 'error': 'WINDOW_UNAVAILABLE',
                    'message': '搜索窗口加载失败: %r' % e}
        try:
            if not loaded.wait(LOAD_TIMEOUT_SECONDS):
                return {'ok': False, 'error': 'TIMEOUT',
                        'message': '搜索窗口加载超时（%ds 看门狗），已切换直连抓取'
                                   % int(LOAD_TIMEOUT_SECONDS),
                        'hint': '可在面板重试或更换搜索引擎'}
            html = self._read_dom(win)
            if html is None or not str(html).strip():
                return {'ok': False, 'error': 'WINDOW_UNAVAILABLE',
                        'message': '无法读取页面内容（evaluate_js 不可用），'
                                   '已切换直连抓取'}
            return {'ok': True, 'html': str(html)}
        finally:
            if subscribed:
                try:
                    events.loaded -= _on_loaded
                except Exception:
                    pass   # 事件槽不支持退订（如测试桩）——忽略，防泄漏由窗口回收兜底

    def _read_dom(self, win):
        """evaluate_js 读 ``document.documentElement.outerHTML``（带 join 上限）。

        Returns:
            str | None：HTML 字符串；None = 不可用（异常/超时/空）。

        首次 join 超时即置 ``_dom_pumpable=False``（本沙箱会话消息循环无法
        泵送 evaluate_js——两次实证的已知限制）：超时的工作线程已成为僵尸
        （join 不回来，daemon 线程只能等进程退出），后续 open_url 跳过窗口
        路径直接走 urllib，不再每请求养一个僵尸线程。
        """
        box = {}

        def _work():
            try:
                box['html'] = win.evaluate_js('document.documentElement.outerHTML')
            except Exception as e:
                box['error'] = e

        t = threading.Thread(target=_work, daemon=True)
        t.start()
        t.join(READ_DOM_TIMEOUT_SECONDS)
        if t.is_alive():
            self._dom_pumpable = False    # 僵尸线程已养成：窗口路径整体退役
            return None
        if 'error' in box:
            self._log.debug('evaluate_js 读取失败: %r', box['error'])
            return None
        return box.get('html')

    # ---------------- urllib 兜底路径 ----------------

    def _fetch_via_urllib(self, url):
        """urllib 直连抓 HTML（禁自动重定向；HTTP 码按规范 §4.1 映射）。

        非 JS 渲染引擎（Bing/DDG/Baidu 的 HTML 端点）可用；JS 渲染引擎
        （Google）可能只得空壳——由调用方结合解析结果数判定（service 层）。
        """
        req = urllib.request.Request(url, headers={
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        try:
            resp = urlopen_no_redirect(req, timeout=LOAD_TIMEOUT_SECONDS)
        except urllib.error.HTTPError as e:
            hint = '引擎限流，可稍后重试或切换引擎' if e.code == 429 else \
                   '稍后重试或更换搜索引擎' if e.code >= 500 else \
                   '该地址暂时无法访问，可稍后重试'
            return {'ok': False, 'error': 'ENGINE_UNREACHABLE',
                    'http_status': e.code,
                    'message': '目标返回 HTTP %s' % e.code, 'hint': hint}
        except urllib.error.URLError as e:
            reason = getattr(e, 'reason', e)
            if isinstance(reason, (socket.timeout, TimeoutError)) or \
                    'timed out' in str(reason).lower():
                return {'ok': False, 'error': 'TIMEOUT',
                        'message': '连接目标站点超时（%ds）' % int(LOAD_TIMEOUT_SECONDS),
                        'hint': '可重试或更换搜索引擎'}
            return {'ok': False, 'error': 'ENGINE_UNREACHABLE',
                    'message': '无法连接目标站点: %s' % reason,
                    'hint': '请检查网络或稍后重试'}
        except Exception as e:
            return {'ok': False, 'error': 'ENGINE_UNREACHABLE',
                    'message': '抓取失败: %s' % e}
        try:
            raw = resp.read(MAX_HTML_BYTES + 1)
            if len(raw) > MAX_HTML_BYTES:
                raw = raw[:MAX_HTML_BYTES]        # 防 OOM 截断（结果页不可能超）
            try:
                ctype = (resp.headers.get('Content-Type') or '') if resp.headers else ''
            except Exception:
                ctype = ''
        finally:
            try:
                resp.close()
            except Exception:
                pass
        return {'ok': True, 'html': _decode_html(raw, ctype)}

    # ---------------- 窗口可见性（CAPTCHA 接管）与回收 ----------------

    def focus_window(self):
        """CAPTCHA 接管：次窗置顶获焦点（主窗口让位；best-effort 不抛）。

        ux-flows 流程 2 步骤 2：``show()`` + ``focus()``。pywebview Window 无
        跨平台 focus API——Windows 经 ``native.Form.Activate()``（BeginInvoke
        回 UI 线程，main.py 开启右键菜单同款口径）；其余平台 best-effort。
        """
        with self._lock:
            win = self._win
        if win is None:
            return False
        shown = False
        for name in ('show', 'restore'):
            fn = getattr(win, name, None)
            if callable(fn):
                try:
                    fn()
                    shown = True
                except Exception:
                    pass
                break
        try:
            form = getattr(win, 'native', None)
            if form is not None and hasattr(form, 'BeginInvoke'):
                from System import Action

                def _activate():
                    try:
                        form.Activate()
                    except Exception:
                        pass

                form.BeginInvoke(Action(_activate))
                shown = True
        except Exception:
            pass   # 非 Windows / pythonnet 不可用——show 已尽力
        return shown

    def _touch(self):
        with self._lock:
            self._last_used = time.monotonic()

    def _start_recycler(self):
        """启动空闲回收看护线程（daemon，幂等；测试可 idle_recycle=False 关闭）。"""
        if not self._idle_recycle:
            return
        with self._lock:
            if self._recycler is not None:
                return
            t = threading.Thread(target=self._recycle_loop, daemon=True,
                                 name='search-browser-recycler')
            self._recycler = t
        t.start()

    def _recycle_loop(self):
        """空闲 60s 回收：无引用窗口或超空闲 → destroy 并清引用（防常驻内存）。"""
        while not self._stop_evt.wait(_RECYCLE_TICK_SECONDS):
            try:
                with self._lock:
                    win = self._win
                    idle = time.monotonic() - self._last_used
                if win is None:
                    continue
                if idle < IDLE_RECYCLE_SECONDS:
                    continue
                self._log.info('搜索次窗空闲 %ds，回收', int(idle))
                self._destroy_window(win)
            except Exception as e:
                self._log.debug('次窗回收异常（忽略）: %r', e)

    def _destroy_window(self, win):
        """销毁窗口并清引用（destroy 异常不抛——回收尽力而为）。"""
        with self._lock:
            if self._win is win:
                self._win = None
        try:
            destroy = getattr(win, 'destroy', None)
            if callable(destroy):
                destroy()
        except Exception as e:
            self._log.debug('次窗销毁失败（忽略）: %r', e)

    def shutdown(self):
        """进程退出：停回收线程 + 销毁次窗（main.py atexit 注册）。"""
        self._stop_evt.set()
        with self._lock:
            win = self._win
        if win is not None:
            self._destroy_window(win)


def _decode_html(raw, content_type=''):
    """响应体解码：先按 Content-Type charset，失败回落 utf-8（replace 不抛）。

    Args:
        raw: bytes 响应体。
        content_type: 响应 Content-Type 头（可含 ``charset=xxx``）。

    Returns:
        str: 解码文本（坏字节替换为 U+FFFD，与 adapters 侧解码口径一致）。
    """
    if isinstance(raw, str):
        return raw
    m = re.search(r'charset=([\w-]+)', str(content_type or ''), re.IGNORECASE)
    if m:
        enc = m.group(1)
        try:
            return bytes(raw).decode(enc, 'replace')
        except (LookupError, TypeError):
            pass
    return bytes(raw).decode('utf-8', 'replace')
