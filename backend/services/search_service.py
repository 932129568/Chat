# -*- coding: utf-8 -*-
"""v1.8.0 B 域·搜索编排服务（实现 v1.8.0 B2：browser_search / browser_open /
search_cache_stats / search_status / browser_takeover 五 js_api 的后端管线）。

模块职责（架构文档 §2.1 后端模块表「搜索编排 search_service」）：
- 检索式构造与参数校验（联调规范 §3.1 请求字段表：非法值一律 BAD_PARAMS
  回显 hint，不静默回默认——防参数幻觉被吞）；
- 缓存层（C1）：``~/.glm-chat/search_cache/`` 独立目录（config.json 零污染
  铁律），TTL 30min + 归一化键（engine/query/site/filetype/time_range/lang +
  URL 归一：去跟踪参数/小写 scheme+host/去默认端口/去末尾 '/'），命中
  ``source='cache'`` 且 ``fetched_at`` 为原抓取时间；
- 取数双通道（§5.1③）：search_browser 次窗优先，不可达自动降级
  ``channel='urllib'``；解析失败走 engine_retry 换引擎（≤2 次）；
- CAPTCHA 人工接管状态机（ux-flows 流程 2）：检出验证页特征 → 创建
  takeover_id（进程内 pending→rechecking→resolved/aborted/expired，
  TTL 10min，重试 ≤3）→ fail-fast 返回 CAPTCHA_REQUIRED；
  ``browser_takeover`` 复检续跑（evaluate_js 复检在本沙箱不可用——按规范
  §3.1 末注回落「重取页面 + 特征检测」语义，续跑成功返回与 browser_search
  同构的成功载荷）；
- 进程内任务注册表（search_status 进度回报通道，规范 §2.4 方案 A 轮询）；
- 审计：browser_search / browser_open / browser_takeover 落 audit_log.jsonl
  （op=web_search / web_open / search_takeover；search_status 与
  search_cache_stats 为读取类，不落审计——1s 轮询不灌爆审计文件）。

guard 挂点：本批次只留注释标记（A 域 v1.8.5 批次集成三档确认链），
不在 B 域执行护栏判定（联调规范 §3.1 错误码 GUARD_DENIED 的触发点在
guard_check 前置，属 A 域接线面）。
"""
import datetime
import hashlib
import json
import os
import re
import secrets
import threading
import time
from collections import deque

from .. import paths
from ..logging_setup import get_logger
from .search_adapters import (DEFAULT_ENGINE, ENGINES, build_query_url,
                              parse_results)
from .search_browser import SearchBrowser
from .search_extract import DEFAULT_MAX_CHARS, extract_main_content
from .toolcache_service import ToolcacheService

# ---------------- 契约常量（联调规范 §3.1 / §4.4） ----------------
CACHE_TTL_MINUTES = 30                    # C1：缓存 TTL（ttl_minutes 可配口径的默认值）
CACHE_DIR_NAME = 'search_cache'           # 独立目录（config.json 零污染铁律）
TAKEOVER_TTL_SECONDS = 600                # 10min 无操作自动放弃（ux-flows 流程 2）
TAKEOVER_MAX_RETRIES = 3                  # 复检仍验证页的重试上限
DEEP_EXTRACT_TOP_N = 3                    # extract=full 连锁深度提取篇数（Top N）
RESULTS_PAYLOAD_MAX_CHARS = 24000         # results 序列化超限 → toolcache 截断
THIN_CONTENT_CHARS = 200                  # 正文 <200 字 → thin_warning（仍成功返回）
MAX_QUERY_CHARS = 500
MAX_SITE_CHARS = 64
MAX_SELECTOR_CHARS = 200
MAX_RESULTS_CAP = 20
MAX_RESULTS_DEFAULT = 10
MAX_CHARS_MIN, MAX_CHARS_MAX = 500, 50000
_ENGINE_RETRY_MAX = 2                     # engine_retry 换引擎次数上限
_TASK_KEEP = 32                           # 任务注册表保留条数（有界防泄漏）

# 验证页特征（标题强特征 / 正文特征两路；ux-flows 流程 1 步骤 6）
_CAPTCHA_TITLE_RE = re.compile(
    r'captcha|verify|人机验证|安全验证|验证码', re.IGNORECASE)
_CAPTCHA_BODY_RE = re.compile(
    r'人机验证|安全验证|验证码|are you a robot|are you human|'
    r'unusual traffic|robot check|captcha', re.IGNORECASE)
# URL 归一：去跟踪参数（§4.4 归一化 key 口径）
_TRACKING_PARAMS = frozenset({
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'utm_id', 'fbclid', 'gclid', 'msclkid', 'spm', 'share_source', 'vd_source',
})
_HTTP_SCHEME_RE = re.compile(r'^https?://', re.IGNORECASE)
_FILETYPE_RE = re.compile(r'^[a-z0-9]{1,10}$', re.IGNORECASE)
_TIME_RANGES = ('day', 'week', 'month', 'year')
_LANGS = ('zh', 'en')
_EXTRACTS = ('none', 'snippet', 'full')

# 阶段 → 进度百分比（search_status.progress_pct；deep_extract 另按篇数覆盖）
_PHASE_PROGRESS = {
    'understanding': 10, 'cache_check': 20, 'window_loading': 35,
    'urllib_fallback': 35, 'extracting': 55, 'filtering': 65,
    'deep_extract': 70, 'validating': 90, 'reformulate': 60,
    'captcha': 40, 'done': 100, 'failed': 100,
}


def _utc_now():
    """ISO8601 UTC（§4.3：全库统一 'Z' 后缀；秒级精度）。"""
    return datetime.datetime.now(datetime.timezone.utc) \
        .replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _as_dict(params):
    """params 归一：dict 原样 / JSON 字符串解析 / 其他 → {}（防御性，不抛）。"""
    if isinstance(params, dict):
        return params
    if isinstance(params, (str, bytes)):
        try:
            d = json.loads(params)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}
    return {}


def _bad_params(message, hint=None):
    """BAD_PARAMS 错误载荷（契约 §3.1：人话 message + 可操作 hint）。"""
    e = {'code': 'BAD_PARAMS', 'message': message}
    if hint:
        e['hint'] = hint
    return {'ok': False, 'error': e}


def _error(code, message, hint=None, **extra):
    """统一错误载荷（ok=False + error{code,message,hint?}）。"""
    e = {'code': code, 'message': message}
    if hint:
        e['hint'] = hint
    e.update(extra)
    return {'ok': False, 'error': e}


def _clamp_int(value, default, lo, hi):
    """int 夹逼：None/非数字 → default；NaN/inf → default；否则夹到 [lo, hi]。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    try:
        n = int(value)
    except (ValueError, OverflowError):
        return default
    if n != value:                      # 10.5 等非整数值 → default
        return default
    return min(max(n, lo), hi)


def _is_int_like(value):
    """是否可安全转 int（排除 bool / NaN / inf / 非整数值）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        n = int(value)
    except (ValueError, OverflowError):
        return False
    return n == value


def _norm_domain(value):
    """site 归一：剥协议/userinfo/路径/端口，小写（契约 §3.1 site 边界）。"""
    s = str(value or '').strip().lower()
    if not s:
        return ''
    if '://' in s:
        s = s.split('://', 1)[1]
    s = s.split('/', 1)[0]
    if '@' in s:
        s = s.rsplit('@', 1)[1]
    if ':' in s:
        s = s.split(':', 1)[0]
    return s


def _normalize_url(url):
    """URL 归一（§4.4 缓存键口径）：小写 scheme/host、去默认端口、去末尾 '/'、
    去 fragment 与跟踪参数（utm_*/fbclid/gclid/msclkid/spm…）。

    纯字符串实现（不 import urllib.parse——与 adapters 纯函数口径一致，
    归一只影响缓存键，不影响实际抓取 URL）。
    """
    s = str(url or '').strip()
    if '://' not in s:
        return s.rstrip('/') or '/'
    scheme, rest = s.split('://', 1)
    scheme = scheme.lower()
    host_part, slash, path = rest.partition('/')
    path = '/' + path if slash else '/'
    if '@' in host_part:
        host_part = host_part.rsplit('@', 1)[1]
    if '?' in path:
        path, _, query = path.partition('?')
        pairs = []
        for kv in query.split('&'):
            if not kv:
                continue
            k = kv.split('=', 1)[0].lower()
            if k in _TRACKING_PARAMS:
                continue
            pairs.append(kv)
        query = '&'.join(pairs)
        path = path + ('?' + query if query else '')
    if '#' in path:
        path = path.split('#', 1)[0]
    host = host_part.lower()
    if host.endswith(':80') and scheme == 'http':
        host = host[:-3]
    if host.endswith(':443') and scheme == 'https':
        host = host[:-4]
    if len(path) > 1:
        path = path.rstrip('/') or '/'
    return '%s://%s%s' % (scheme, host, path)


def _extract_title(html):
    """取 ``<title>`` 文本（全树查找首个 title 元素；无标题返回 ''）。"""
    from .search_adapters import build_tree, element_text, iter_elements
    try:
        root = build_tree(html)
        for el in iter_elements(root):
            if el.tag == 'title':
                return element_text(el)
    except Exception:
        pass
    return ''


def _captcha_signal(html):
    """验证页特征检测：返回命中特征串（'title:xxx'/'body:xxx'）或 None。

    标题强特征单独成立；正文特征需结合「解析结果为 0」由调用方判定
    （规范 §3.1：结果数为 0 + 验证特征命中）——防结果页正文提及误判。
    """
    text = str(html or '')
    if not text:
        return None
    title = _extract_title(text)
    m = _CAPTCHA_TITLE_RE.search(title or '')
    if m:
        return 'title:%s' % m.group(0)
    m = _CAPTCHA_BODY_RE.search(text[:20000])
    if m:
        return 'body:%s' % m.group(0)
    return None


class SearchService:
    """搜索编排服务（进程内单例，由 Api 装配；测试可注入 FakeBrowser）。

    五方法契约（联调规范 §3.1 B 组）：
    - ``browser_search(params)`` → 成功载荷 / CAPTCHA_REQUIRED / 错误码；
    - ``browser_takeover(takeover_id, action)`` → resumed 同构载荷 /
      CAPTCHA_REQUIRED 重试 / CAPTCHA_ABORTED；
    - ``search_status(task_id=None)`` → 进度回报（读取类不落审计）；
    - ``browser_open(params)`` → 正文提取（截断走 toolcache full_ref）；
    - ``search_cache_stats()`` → 缓存统计（读取类不落审计）。
    """

    def __init__(self, browser=None, toolcache=None, guard=None,
                 cache_dir=None, ttl_minutes=CACHE_TTL_MINUTES,
                 clock=None):
        """Args:
            browser: 取数通道（缺省 SearchBrowser()；测试注入 FakeBrowser）。
            toolcache: 截断落盘服务（缺省 ToolcacheService(do_cleanup=False)——
                搜索缓存目录独立，不触发 toolcache 启动清理）。
            guard: 审计写入者（缺省 GuardService()；Api 注入同一实例保持
                audit_log.jsonl 单一口径与 10MB 轮转）。
            cache_dir: 搜索缓存目录（缺省 ``~/.glm-chat/search_cache/``）。
            ttl_minutes: 缓存 TTL（分钟）。
            clock: 单调时钟（测试注入假时钟；缺省 time.monotonic）。
        """
        self._log = get_logger()
        self._browser = browser if browser is not None else SearchBrowser()
        self._toolcache = toolcache if toolcache is not None \
            else ToolcacheService(do_cleanup=False)
        self._ttl = int(ttl_minutes)
        self._clock = clock or time.monotonic
        if guard is None:
            from .guard_service import GuardService
            guard = GuardService()
        self._guard = guard
        self._cache_dir = cache_dir or os.path.join(paths.CONFIG_DIR,
                                                    CACHE_DIR_NAME)
        try:
            os.makedirs(self._cache_dir, exist_ok=True)
        except Exception as e:
            self._log.warning('搜索缓存目录创建失败: %r', e)
        # 缓存命中/未命中计数（进程内；search_cache_stats 数据源）
        self._hits = 0
        self._misses = 0
        # 任务注册表（search_status 数据源；有界）
        self._tasks = {}
        self._task_order = deque(maxlen=_TASK_KEEP)
        self._active_task_id = None
        # takeover 注册表（CAPTCHA 人工接管状态机）
        self._takeovers = {}
        self._lock = threading.RLock()

    # ---- 次窗装配代理（main.py 接线用；转发 self._browser）----
    # 修复（2026-10-20 启动 warning）：main.py 调 api._search.set_window/
    # shutdown，但方法在 SearchBrowser 上——Service 缺代理导致
    # 'SearchService' object has no attribute 'set_window'（次窗静默失效）。
    def set_window(self, win):
        """注入 pywebview 次窗引用（转发 SearchBrowser.set_window）。"""
        self._browser.set_window(win)

    def shutdown(self):
        """停回收线程 + 销毁次窗（转发 SearchBrowser.shutdown；幂等）。"""
        self._browser.shutdown()

    # ================================================== 浏览器搜索（B1）
    def browser_search(self, params):
        """实现 v1.8.0 B2：联调规范 §3.1 browser_search 全链。

        管线：参数校验 → 任务注册 → 检索式构造 → 缓存层（TTL 30min + 归一键）
        → 取数（次窗优先 / urllib 兜底）→ 验证页检测（CAPTCHA fail-fast）→
        解析（失败换引擎 ≤2）→ 过滤去重 → extract（none/snippet/full）→
        校验 → 缓存写入 → 响应组装（source/fetched_at/results/cached/
        truncated/full_ref/elapsed_ms/channel/deep_extract）。

        Args:
            params: dict，字段见契约 §3.1（query 必填；engine/site/filetype/
                time_range/lang/max_results/extract 可选）。

        Returns:
            dict: 成功载荷（ok=True）或错误载荷（BAD_PARAMS / ENGINE_UNREACHABLE
                / TIMEOUT / NAV_BLOCKED / CAPTCHA_REQUIRED）。
        """
        p = _as_dict(params)
        bad = self._validate_search_params(p)
        if bad is not None:
            self._audit('web_search', {'query': str(p.get('query') or '')[:200]},
                        'search', 'block')
            return bad
        # guard 挂点（A 域 v1.8.5 批次集成）：三档确认链前置判定位——
        #   reason = self._guard.enforce_exec('web_search', {'query': ...}, token)
        #   if reason: audit(..., 'block'); return _error('GUARD_DENIED', reason)
        # B 域批次只留挂点不接线（联调规范 §3.1：GUARD_DENIED 触发点在
        # guard_check 前置，属 A 域接线面；browser_search 无本地副作用，
        # 默认 off 档行为 = 现行为）。
        query = str(p['query'])
        engine = str(p.get('engine') or DEFAULT_ENGINE).strip().lower()
        site = str(p.get('site') or '').strip()
        filetype = str(p.get('filetype') or '').strip().lower()
        time_range = str(p.get('time_range') or '').strip().lower()
        lang = str(p.get('lang') or '').strip().lower()
        max_results = _clamp_int(p.get('max_results'), MAX_RESULTS_DEFAULT,
                                 1, MAX_RESULTS_CAP)
        extract = str(p.get('extract') or 'snippet').strip().lower()
        # 检索式回显（含 site:/filetype: 操作符；与 adapters 内部构造同口径）
        terms = [query]
        if site:
            terms.append('site:%s' % _norm_domain(site))
        if filetype:
            terms.append('filetype:%s' % filetype)
        q_echo = ' '.join(terms)

        task_id = self._begin_task(query, engine)
        t0 = self._clock()
        try:
            url = build_query_url(engine, {
                'query': query, 'site': site, 'filetype': filetype,
                'time_range': time_range, 'lang': lang,
                'max_results': max_results})
        except ValueError as e:
            self._end_task(task_id, 'failed', str(e))
            self._audit('web_search', {'query': q_echo, 'engine': engine},
                        'search', 'error')
            return _bad_params(str(e))

        # ---- 缓存层（C1：TTL + 归一化键）----
        self._set_phase(task_id, 'cache_check', '正在检查缓存…')
        key = self._cache_key(engine, q_echo, site, filetype,
                              time_range, lang)
        entry = self._cache_get(key)
        if entry is not None:
            with self._lock:
                self._hits += 1
            self._set_phase(task_id, 'done', '搜索完成（缓存命中）',
                            cache_hit=True)
            payload = self._assemble(entry['query'], engine, 'cache',
                                     entry['fetched_at'], entry['results'],
                                     entry.get('deep'), extract, max_results,
                                     int((self._clock() - t0) * 1000),
                                     channel=None)
            self._end_task(task_id, 'done', '搜索完成（缓存命中）', cache_hit=True)
            self._audit('web_search', {'query': q_echo, 'engine': engine,
                                       'source': 'cache'}, 'search', 'ok')
            return payload
        with self._lock:
            self._misses += 1

        # ---- 取数 + 解析（次窗优先，urllib 兜底；验证页 fail-fast）----
        return self._fetch_and_parse(task_id, p, engine, url, q_echo,
                                     max_results, extract, t0,
                                     retries_left=_ENGINE_RETRY_MAX)

    def _validate_search_params(self, p):
        """browser_search 参数校验（契约 §3.1 请求字段表）。

        Returns:
            None（通过）或 BAD_PARAMS 错误载荷（人话 + hint 列合法值，
            Agent 可自校正——不静默回默认）。
        """
        query = p.get('query')
        if not isinstance(query, str) or not query.strip():
            return _bad_params('query 不能为空（1-500 字符的检索词）',
                               '例如 {"query": "python 教程"}')
        if len(query.strip()) > MAX_QUERY_CHARS:
            return _bad_params('query 超长（最多 %d 字符）' % MAX_QUERY_CHARS,
                               '请精简检索词')
        engine = p.get('engine')
        if engine is not None:
            if not isinstance(engine, str) or \
                    engine.strip().lower() not in ENGINES:
                legal = '/'.join(ENGINES)
                if isinstance(engine, str) and engine.strip().lower() == 'custom':
                    return _bad_params(
                        'custom 引擎模板注册将在 v1.8.1 提供，当前不可用',
                        '合法值: %s' % legal)
                return _bad_params('不支持的搜索引擎: %r' % engine,
                                   '合法值: %s' % legal)
        site = p.get('site')
        if site is not None:
            if not isinstance(site, str) or len(site.strip()) > MAX_SITE_CHARS \
                    or not _norm_domain(site):
                return _bad_params('site 需为裸域名（如 github.com），且不超过 %d 字符'
                                   % MAX_SITE_CHARS)
        filetype = p.get('filetype')
        if filetype is not None:
            if not isinstance(filetype, str) or \
                    not _FILETYPE_RE.match(filetype.strip()):
                return _bad_params('filetype 需为 1-10 位字母数字（如 pdf/docx/md）')
        time_range = p.get('time_range')
        if time_range is not None:
            if not isinstance(time_range, str) or \
                    time_range.strip().lower() not in _TIME_RANGES:
                return _bad_params('time_range 仅支持 %s' % '/'.join(_TIME_RANGES))
        lang = p.get('lang')
        if lang is not None:
            if not isinstance(lang, str) or lang.strip().lower() not in _LANGS:
                return _bad_params('lang 仅支持 zh/en')
        max_results = p.get('max_results')
        if max_results is not None:
            if not _is_int_like(max_results):
                return _bad_params('max_results 需为整数（1-20，默认 10）',
                                   '超界值将夹逼到合法区间并回显实际值')
        extract = p.get('extract')
        if extract is not None:
            if not isinstance(extract, str) or \
                    extract.strip().lower() not in _EXTRACTS:
                return _bad_params('extract 仅支持 none/snippet/full（默认 snippet）')
        return None

    # ================================================== 取数 + 解析主管线
    def _fetch_and_parse(self, task_id, params, engine, url, q_echo,
                         max_results, extract, t0, retries_left,
                         takeover=None, html=None, channel=None,
                         orig_engine=None):
        """取数 → 验证页检测 → 解析 → 过滤 → 深度提取 → 校验 → 缓存 → 组装。

        Args:
            takeover: CAPTCHA 续跑时传入的 takeover 注册项（首次搜索为 None）——
                续跑中再次检出验证页时走重试计数而非新建接管。
            html/channel: 续跑时复用已抓取的页面（避免双次取数）。
            orig_engine: 用户请求的原始引擎（engine_retry 换引擎后仍保留——
                用于 JS 渲染引擎空壳判定，规范 §5.1③）。
        """
        orig_engine = orig_engine or engine
        if html is None:
            self._set_phase(task_id, 'window_loading', '正在打开 %s…' % engine)
            fetch = self._browser.open_url(url)
            if not fetch.get('ok'):
                code = fetch.get('error') or 'ENGINE_UNREACHABLE'
                if code == 'WINDOW_UNAVAILABLE':
                    code = 'ENGINE_UNREACHABLE'
                msg = fetch.get('message') or '取数失败'
                self._set_phase(task_id, 'failed', msg)
                if takeover is not None:
                    # 续跑取数失败：回到 prompting 让用户可重试，不新建接管
                    takeover['state'] = 'prompting'
                self._audit('web_search', {'query': q_echo, 'engine': engine,
                                           'error': code}, 'search', 'error')
                return _error(code, msg, fetch.get('hint'))
            html = fetch.get('html') or ''
            channel = fetch.get('channel')
            self._set_phase(task_id, 'window_loading', None, channel=channel)
            if channel == 'urllib':
                self._set_phase(task_id, 'urllib_fallback',
                                '已切换轻量抓取（降级）…', channel=channel)

        # ---- 验证页特征检测（fail-fast：CAPTCHA_REQUIRED + takeover_id）----
        sig = _captcha_signal(html)
        results = parse_results(engine, html)
        if sig and not results:
            return self._enter_captcha(task_id, params, engine, url, q_echo,
                                       sig, takeover)

        self._set_phase(task_id, 'extracting', '正在提取搜索结果…', channel=channel)
        if not results:
            # 解析为空：换引擎重试（ux-flows 流程 1 engine_retry ≤2 次）
            if retries_left > 0:
                nxt = self._next_engine(engine)
                if nxt is not None:
                    self._set_phase(
                        task_id, 'reformulate',
                        '%s 解析失败，正在切换 %s 重试（%d/2）'
                        % (engine, nxt, _ENGINE_RETRY_MAX - retries_left + 1))
                    retry_url = build_query_url(nxt, {
                        'query': str(params.get('query') or ''),
                        'site': params.get('site'), 'filetype': params.get('filetype'),
                        'time_range': params.get('time_range'),
                        'lang': params.get('lang'),
                        'max_results': params.get('max_results')})
                    return self._fetch_and_parse(
                        task_id, params, nxt, retry_url, q_echo,
                        max_results, extract, t0, retries_left - 1,
                        takeover=takeover, orig_engine=orig_engine)
            # 重试耗尽：JS 渲染引擎的空壳明确归 ENGINE_UNREACHABLE（规范 §5.1③）
            if orig_engine == 'google' and channel == 'urllib':
                msg = '该引擎依赖 JS 渲染，直连抓取未获得有效结果'
                self._set_phase(task_id, 'failed', msg)
                self._audit('web_search', {'query': q_echo, 'engine': engine},
                            'search', 'error')
                return _error('ENGINE_UNREACHABLE', msg,
                              '建议切换 Bing/DuckDuckGo')
            # 其余：成功形状 + 空结果（UI 提示「未找到相关内容」）
            self._end_task(task_id, 'done', '未找到相关内容')
            self._audit('web_search', {'query': q_echo, 'engine': engine,
                                       'source': 'live', 'n': 0}, 'search', 'ok')
            return self._assemble(q_echo, engine, 'live', _utc_now(), [],
                                  None, extract, max_results,
                                  int((self._clock() - t0) * 1000),
                                  channel=channel)

        # ---- 过滤/去重（URL 归一）/排序/截断到 max_results ----
        self._set_phase(task_id, 'filtering', '正在整理结果…')
        results = self._dedupe_and_rank(results)[:max_results]

        # ---- extract=full：Top N 连锁深度提取（ux-flows 流程 3；单篇失败不中断）----
        deep = None
        if extract == 'full':
            self._set_phase(task_id, 'deep_extract', '正在读取正文…')
            deep = self._deep_extract(results)

        # ---- V1 校验（结果非空 + 字段完整；不通过且可换引擎才 reformulate）----
        self._set_phase(task_id, 'validating', '正在校验结果…')
        valid = [r for r in results if r.get('title') and r.get('url')]
        if not valid and retries_left > 0:
            nxt = self._next_engine(engine)
            if nxt is not None:
                self._set_phase(task_id, 'reformulate',
                                '校验未过，正在切换 %s 重试（%d/2）'
                                % (nxt, _ENGINE_RETRY_MAX - retries_left + 1))
                retry_url = build_query_url(nxt, {
                    'query': str(params.get('query') or ''),
                    'site': params.get('site'), 'filetype': params.get('filetype'),
                    'time_range': params.get('time_range'),
                    'lang': params.get('lang'),
                    'max_results': params.get('max_results')})
                return self._fetch_and_parse(
                    task_id, params, nxt, retry_url, q_echo,
                    max_results, extract, t0, retries_left - 1,
                    takeover=takeover, orig_engine=orig_engine)
        results = valid or results

        # ---- 缓存写入 + 组装 ----
        fetched_at = _utc_now()
        self._cache_put(self._cache_key(
            engine, q_echo, str(params.get('site') or ''),
            str(params.get('filetype') or '').lower(),
            str(params.get('time_range') or '').lower(),
            str(params.get('lang') or '').lower()),
            {'query': q_echo, 'engine': engine, 'fetched_at': fetched_at,
             'fetched_ts': self._clock(), 'results': results, 'deep': deep})
        if takeover is not None:
            takeover['state'] = 'resolved'
        self._end_task(task_id, 'done', '搜索完成')
        self._audit('web_search', {'query': q_echo, 'engine': engine,
                                   'source': 'live', 'n': len(results),
                                   'channel': channel or ''}, 'search', 'ok')
        payload = self._assemble(q_echo, engine, 'live', fetched_at, results,
                                 deep, extract, max_results,
                                 int((self._clock() - t0) * 1000),
                                 channel=channel)
        if takeover is not None:
            # 续跑成功：与 browser_search 同构 + resumed 标记（规范 §3.1 B5）
            payload['resumed'] = True
        return payload

    @staticmethod
    def _next_engine(engine):
        """engine_retry 顺序：ENGINES 注册序（Bing 居首，§7 R1）轮转下一个。"""
        try:
            i = ENGINES.index(engine)
        except ValueError:
            return ENGINES[0] if engine not in ENGINES else None
        nxt = ENGINES[(i + 1) % len(ENGINES)]
        return None if nxt == engine else nxt

    @staticmethod
    def _dedupe_and_rank(results):
        """URL 归一去重（保首条）+ position 重排（契约 §4.3：position 从 1 连续）。"""
        seen = set()
        out = []
        for r in results:
            u = _normalize_url(r.get('url') or '')
            if not u or u in seen:
                continue
            seen.add(u)
            item = dict(r)
            item['position'] = len(out) + 1
            out.append(item)
        return out

    def _deep_extract(self, results):
        """extract=full：对 Top N 结果逐个取正文（单篇失败不中断整批）。

        Returns:
            dict: ``{done, total, failed}``；每篇正文挂结果项 ``extra.content``。
        """
        top = results[:DEEP_EXTRACT_TOP_N]
        done = failed = 0
        for r in top:
            try:
                fetch = self._browser.open_url(r.get('url') or '')
                if not fetch.get('ok'):
                    failed += 1
                    continue
                ex = extract_main_content(fetch.get('html') or '', None, 0)
                content = ex.get('content') or ''
                if not content.strip():
                    failed += 1
                    continue
                r.setdefault('extra', {})['content'] = content
                r['extra']['full_chars'] = ex.get('full_chars') or len(content)
                done += 1
            except Exception as e:
                self._log.debug('深度提取单篇失败（不中断整批）: %r', e)
                failed += 1
        return {'done': done, 'total': len(top), 'failed': failed}

    def _assemble(self, q_echo, engine, source, fetched_at, results, deep,
                  extract, max_results, elapsed_ms, channel=None):
        """响应组装（契约 §3.1 成功响应 + 联调观测字段）。

        - 按 max_results 截断回显（缓存命中时请求数小于写入数亦可收缩——
          归一化键不含 max_results，§4.4）；
        - extract='none' 时剥离 snippet（缓存内仍存全量，不影响后续 snippet 请求）；
        - results 序列化超限 → toolcache 落全量 + full_ref，回包裁减；
        - deep_extract 进度回显（extract=full 时）。
        """
        items = [dict(r) for r in results][:max_results]
        if extract == 'none':
            for it in items:
                it['snippet'] = ''
        fitted, truncated, full_ref = self._fit_results(items)
        payload = {
            'ok': True,
            'query': q_echo,
            'engine': engine,
            'source': source,
            'fetched_at': fetched_at,
            'results': fitted,
            'cached': source == 'cache',
            'truncated': truncated,
            'elapsed_ms': int(elapsed_ms),
        }
        if full_ref:
            payload['full_ref'] = full_ref
        if channel:
            payload['channel'] = channel
        if deep is not None:
            payload['deep_extract'] = deep
        return payload

    def _fit_results(self, items):
        """results 载荷超限 → toolcache 截断（契约 §4.3：截断处追加尾注由
        序列化层补；此处只落全量 + 给 full_ref，回包裁减到限内）。"""
        try:
            raw = json.dumps(items, ensure_ascii=False)
        except (TypeError, ValueError):
            return items, False, None
        if len(raw) <= RESULTS_PAYLOAD_MAX_CHARS:
            return items, False, None
        cid = self._toolcache.cache(raw)
        trimmed = list(items)
        while len(trimmed) > 1 and \
                len(json.dumps(trimmed, ensure_ascii=False)) > RESULTS_PAYLOAD_MAX_CHARS:
            trimmed.pop()
        if len(trimmed) == 1 and \
                len(json.dumps(trimmed, ensure_ascii=False)) > RESULTS_PAYLOAD_MAX_CHARS:
            one = dict(trimmed[0])
            one['snippet'] = str(one.get('snippet') or '')[:500]
            trimmed = [one]
        return trimmed, True, ('toolcache:%s' % cid if cid else None)

    # ================================================== CAPTCHA 人工接管（B5 支撑）
    def _enter_captcha(self, task_id, params, engine, url, q_echo, sig,
                       takeover=None):
        """检出验证页 → 创建/续用 takeover → fail-fast CAPTCHA_REQUIRED。

        takeover 生命周期（架构 §3.1 + ux-flows 流程 2）：
        pending(prompting) → rechecking → resolved / aborted / expired(10min)。
        """
        if takeover is not None:
            # 续跑中再次检出验证页：走重试计数，不新建接管
            takeover['retries'] += 1
            if takeover['retries'] >= takeover['max_retries']:
                takeover['state'] = 'aborted'
                self._set_phase(task_id, 'failed', '人工验证重试次数已用完')
                self._audit('web_search', {'query': q_echo, 'engine': engine},
                            'search', 'aborted')
                return _error('CAPTCHA_ABORTED',
                              '人工验证重试次数已用完（%d 次），本次搜索已放弃'
                              % takeover['max_retries'],
                              '可更换搜索引擎后重试')
            takeover['state'] = 'prompting'
            self._set_phase(task_id, 'captcha', '需要人工验证', takeover=takeover)
            self._audit('search_takeover',
                        {'takeover_id': takeover['takeover_id'],
                         'retry': takeover['retries']}, 'takeover', 'retry')
            return self._captcha_payload(takeover)
        tk_id = 'tk_%s' % secrets.token_hex(8)
        takeover = {
            'takeover_id': tk_id, 'state': 'prompting', 'query': q_echo,
            'engine': engine, 'url': url, 'params': dict(params),
            'created_at': time.time(), 'retries': 0,
            'max_retries': TAKEOVER_MAX_RETRIES, 'task_id': task_id,
            'result': None,
        }
        with self._lock:
            self._takeovers[tk_id] = takeover
        self._set_phase(task_id, 'captcha', '需要人工验证', takeover=takeover)
        # 次窗置顶获焦点（主窗口让位；best-effort——窗口缺失不阻塞接管流程）
        try:
            self._browser.focus_window()
        except Exception as e:
            self._log.debug('次窗置顶失败（忽略，用户可手动切窗口）: %r', e)
        self._audit('web_search', {'query': q_echo, 'engine': engine,
                                   'signal': sig}, 'search', 'captcha')
        return self._captcha_payload(takeover)

    @staticmethod
    def _captcha_payload(takeover):
        """CAPTCHA_REQUIRED fail-fast 载荷（架构 §3.1 响应形状，权威）。

        首次检出（retries=0）保持规范最小形状 {code,message,hint,takeover_id}；
        接管重试（retries>0，规范 §3.1 B5）附 retry/max_retries 回显。
        """
        e = _error('CAPTCHA_REQUIRED', '搜索引擎要求人机验证',
                   '请在面板中手动完成后点击继续',
                   takeover_id=takeover['takeover_id'])
        if takeover.get('retries'):
            e['error']['retry'] = takeover['retries']
            e['error']['max_retries'] = takeover['max_retries']
        return e

    def browser_takeover(self, takeover_id, action):
        """实现 v1.8.0 B2：人工接管续跑/放弃（联调规范 §3.1 B5 + §8.2）。

        Args:
            takeover_id: ``browser_search``  fail-fast 返回的接管会话 id。
            action: ``continue``（复检续跑）/ ``abort``（放弃）。

        Returns:
            dict: continue 通过 → ``{ok: True, resumed: True, ...browser_search
            同构成功字段}``；仍验证页 → CAPTCHA_REQUIRED（retry ≤3）；
            abort → CAPTCHA_ABORTED；未知/过期 → TAKEOVER_NOT_FOUND /
            TAKEOVER_EXPIRED；action 非法 → BAD_PARAMS。
        """
        tk = str(takeover_id or '').strip()
        act = str(action or '').strip().lower()
        if not tk:
            return _bad_params('takeover_id 不能为空')
        if act not in ('continue', 'abort'):
            return _bad_params('action 仅支持 continue/abort')
        with self._lock:
            entry = self._takeovers.get(tk)
        if entry is None:
            return _error('TAKEOVER_NOT_FOUND', '接管会话不存在或已被清理',
                          '请重新发起搜索')
        if time.time() - entry['created_at'] > TAKEOVER_TTL_SECONDS and \
                entry['state'] not in ('resolved', 'aborted'):
            entry['state'] = 'expired'
            self._forget_takeover(tk)
            return _error('TAKEOVER_EXPIRED',
                          '人工验证已超时（%d 分钟无操作），本次搜索已放弃'
                          % (TAKEOVER_TTL_SECONDS // 60),
                          '请重新发起搜索')
        if act == 'abort':
            entry['state'] = 'aborted'
            self._forget_takeover(tk)
            task_id = entry.get('task_id')
            if task_id:
                self._end_task(task_id, 'failed', '已放弃人工验证')
            self._audit('search_takeover', {'takeover_id': tk}, 'takeover', 'abort')
            return _error('CAPTCHA_ABORTED', '用户已放弃人工验证',
                          'Agent 可更换搜索引擎或告知用户')
        # continue：幂等（防连点竞态——规范 §2.2 接管行）
        if entry['state'] == 'resolved':
            return entry.get('result') or _error(
                'TAKEOVER_NOT_FOUND', '接管会话结果已清理，请重新发起搜索')
        if entry['state'] in ('aborted', 'expired'):
            return _error('CAPTCHA_ABORTED', '本次人工验证已放弃',
                          '请重新发起搜索')
        if entry['state'] == 'rechecking':
            return self._captcha_payload(entry)   # 在途复检：返回当前态
        # ---- 复检（规范 §3.1 末注：evaluate_js 复检在本环境不可用——
        # 回落「重取页面 + 特征检测」；通过即原管线续跑）----
        entry['state'] = 'rechecking'
        entry['retries'] += 1
        task_id = entry.get('task_id')
        self._set_phase(task_id, 'captcha', '正在检查验证结果…', takeover=entry)
        self._audit('search_takeover', {'takeover_id': tk,
                                        'retry': entry['retries']},
                    'takeover', 'continue')
        fetch = self._browser.open_url(entry['url'])
        if not fetch.get('ok'):
            # 复检取数失败：回 prompting 让用户重试（不消耗 retry 语义）
            entry['state'] = 'prompting'
            self._set_phase(task_id, 'captcha', '需要人工验证', takeover=entry)
            return _error(fetch.get('error') or 'ENGINE_UNREACHABLE',
                          fetch.get('message') or '复检取数失败',
                          fetch.get('hint') or '请稍后再次点击继续')
        html = fetch.get('html') or ''
        sig = _captcha_signal(html)
        results = parse_results(entry['engine'], html)
        if sig and not results:
            # 仍验证页：重试 ≤3，耗尽自动放弃（ux-flows 流程 2 步骤 5）
            if entry['retries'] >= entry['max_retries']:
                entry['state'] = 'aborted'
                self._forget_takeover(tk)
                self._end_task(task_id, 'failed', '人工验证重试次数已用完')
                self._audit('search_takeover', {'takeover_id': tk},
                            'takeover', 'abort')
                return _error('CAPTCHA_ABORTED',
                              '人工验证重试次数已用完（%d 次），本次搜索已放弃'
                              % entry['max_retries'],
                              '可更换搜索引擎后重试')
            entry['state'] = 'prompting'
            self._set_phase(task_id, 'captcha', '需要人工验证', takeover=entry)
            self._audit('search_takeover', {'takeover_id': tk,
                                            'retry': entry['retries']},
                        'takeover', 'retry')
            return self._captcha_payload(entry)
        # ---- 复检通过：原管线续跑（复用已取页面，不再二次取数）----
        params = entry['params']
        max_results = _clamp_int(params.get('max_results'), MAX_RESULTS_DEFAULT,
                                 1, MAX_RESULTS_CAP)
        extract = str(params.get('extract') or 'snippet').strip().lower()
        t0 = self._clock()
        payload = self._fetch_and_parse(
            task_id, params, entry['engine'], entry['url'], entry['query'],
            max_results, extract, t0, retries_left=_ENGINE_RETRY_MAX,
            takeover=entry, html=html, channel=fetch.get('channel'))
        if payload.get('ok'):
            # 仅成功载荷落接管结果并清理注册；失败载荷（重试/放弃分支）
            # 保持 entry 存活，用户可再次 continue（幂等当前态）。
            entry['result'] = payload
            self._forget_takeover(tk)
        return payload

    def _forget_takeover(self, tk_id):
        """清理 takeover 注册（终态后；有界防泄漏）。"""
        with self._lock:
            self._takeovers.pop(tk_id, None)
            if len(self._takeovers) > _TASK_KEEP:
                for k in list(self._takeovers)[:-_TASK_KEEP]:
                    self._takeovers.pop(k, None)

    # ================================================== 任务注册表（B4 支撑）
    def _begin_task(self, query, engine):
        """注册搜索任务（进程内；search_status 数据源）。"""
        task_id = 'st_%s' % secrets.token_hex(6)
        now = time.time()
        with self._lock:
            self._tasks[task_id] = {
                'task_id': task_id, 'phase': 'understanding',
                'progress_pct': _PHASE_PROGRESS['understanding'],
                'message': '正在理解检索意图…', 'channel': None,
                'query': query, 'engine': engine, 'started_at': now,
                'elapsed_ms': 0, 'cache_hit': None, 'takeover': None,
                'deep_extract': None, 'active': True,
            }
            self._task_order.append(task_id)
            self._active_task_id = task_id
        return task_id

    def _set_phase(self, task_id, phase, message=None, **extra):
        """更新任务阶段（message=None 表示保持原消息；extra 覆盖字段）。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task['phase'] = phase
            task['progress_pct'] = extra.pop('progress_pct',
                                             _PHASE_PROGRESS.get(phase))
            if message is not None:
                task['message'] = message
            task['elapsed_ms'] = int(
                (time.time() - task['started_at']) * 1000)
            takeover = extra.pop('takeover', None)
            if takeover is not None:
                task['takeover'] = {
                    'takeover_id': takeover['takeover_id'],
                    'state': takeover['state'],
                    'elapsed_s': int(time.time() - takeover['created_at']),
                    'retries': takeover['retries'],
                    'max_retries': takeover['max_retries'],
                }
                task['message'] = task['message'] or '需要人工验证'
            for k, v in extra.items():
                if v is not None:
                    task[k] = v

    def _end_task(self, task_id, phase, message=None, **extra):
        """任务终态（done/failed；active=False，前端停轮询）。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task['phase'] = phase
            task['active'] = False
            task['progress_pct'] = _PHASE_PROGRESS.get(phase, 100)
            if message:
                task['message'] = message
            task['elapsed_ms'] = int(
                (time.time() - task['started_at']) * 1000)
            for k, v in extra.items():
                if v is not None:
                    task[k] = v
            if self._active_task_id == task_id:
                self._active_task_id = None

    def search_status(self, task_id=None):
        """实现 v1.8.0 B2：进度回报通道（联调规范 §3.1 B4 + §2.4 方案 A）。

        Args:
            task_id: 任务 id 或 takeover_id（缺省 = 当前活跃搜索；传入时
                校验归属——任务表优先，takeover 表回退）。

        Returns:
            dict: ``{ok, active, phase, progress_pct?, message, channel?,
            query?, engine?, elapsed_ms, takeover?, deep_extract?, cache_hit?}``；
            无活跃搜索 → ``{ok: True, active: False}``（前端停轮询）。
            读取类不落审计（1s 轮询不灌爆审计文件，规范 §3.1 B4）。
        """
        with self._lock:
            task = None
            if task_id:
                task = self._tasks.get(str(task_id))
                if task is None:
                    tk = self._takeovers.get(str(task_id))
                    if tk is not None:
                        # 传入 takeover_id：归属校验通过 → captcha 态状态
                        # （规范 §3.1 B4：phase=captcha 时 takeover 出现）
                        return {'ok': True, 'active': True, 'phase': 'captcha',
                                'takeover': self._takeover_status(tk)}
            if task is None and not task_id:
                # 最近一个任务（终态也返回——前端拿到 done/failed 后停轮询）
                for tid in reversed(self._task_order):
                    t = self._tasks.get(tid)
                    if t is not None:
                        task = t
                        break
            if task is None:
                return {'ok': True, 'active': False}
            snap = dict(task)
            if snap.get('takeover'):
                tk = self._takeovers.get(snap['takeover']['takeover_id'])
                if tk is not None:
                    snap['takeover'] = self._takeover_status(tk)
            # 在途任务实时重算 elapsed_ms（阶段更新之间秒表继续走，§2.3 秒表数据源）
            if snap.get('active') and snap.get('started_at'):
                snap['elapsed_ms'] = int((time.time() - snap['started_at']) * 1000)
        snap.pop('task_id', None)
        snap.pop('started_at', None)
        snap['ok'] = True
        return snap

    @staticmethod
    def _takeover_status(tk):
        """takeover 状态对象（规范 §3.1 B4：{takeover_id, state, elapsed_s,
        retries, max_retries}）。"""
        return {
            'takeover_id': tk['takeover_id'], 'state': tk['state'],
            'elapsed_s': int(time.time() - tk['created_at']),
            'retries': tk['retries'], 'max_retries': tk['max_retries'],
        }

    # ================================================== 原文打开（B2）
    def browser_open(self, params):
        """实现 v1.8.0 B2：联调规范 §3.1 browser_open（ux-flows 流程 3）。

        管线：参数校验（url 仅 http/https，selector ≤200 字符，max_chars
        500-50000 夹逼回显）→ 取数（次窗/urllib 双通道）→ 标题提取 →
        extract_main_content（selector 覆盖 / 密度法）→ 超长截断落 toolcache
        （full_ref='toolcache:tc_xxx'，read_more 续读）→ thin_warning
        （正文 <200 字仍成功 + thin:true）。

        Returns:
            dict: 成功 ``{ok, url, title, content, truncated, full_ref?,
            extractor, fetched_at, elapsed_ms, channel, thin?, max_chars}``；
            错误 NAV_BLOCKED / TIMEOUT / ENGINE_UNREACHABLE /
            EMPTY_CONTENT / SELECTOR_NOT_FOUND / BAD_PARAMS。
        """
        p = _as_dict(params)
        url = str(p.get('url') or '').strip()
        if not url:
            self._audit('web_open', {'url': ''}, 'open', 'block')
            return _bad_params('url 不能为空')
        # guard 挂点（A 域 v1.8.5 批次集成）：browser_open 会真实访问外网，
        # A 域接线时在此前置 enforce_exec('web_open', {'url': ...}, token)，
        # GUARD_DENIED 分支同 browser_search 口径（本批只留挂点）。
        if not _HTTP_SCHEME_RE.match(url):
            self._audit('web_open', {'url': url[:200]}, 'open', 'block')
            return _error('NAV_BLOCKED', '仅支持 http/https 链接',
                          '其他协议（file:// 等）已被禁止导航', url=url[:200])
        selector = p.get('selector')
        if selector is not None:
            selector = str(selector).strip()
            if len(selector) > MAX_SELECTOR_CHARS:
                return _bad_params('selector 超长（最多 %d 字符）'
                                   % MAX_SELECTOR_CHARS)
        else:
            selector = ''
        raw_max = p.get('max_chars')
        max_chars = DEFAULT_MAX_CHARS
        if raw_max is not None:
            if not _is_int_like(raw_max):
                return _bad_params('max_chars 需为整数（500-50000，默认 8000）',
                                   '超界值将夹逼到合法区间并回显实际值')
            max_chars = min(max(int(raw_max), MAX_CHARS_MIN), MAX_CHARS_MAX)

        t0 = self._clock()
        fetch = self._browser.open_url(url)
        if not fetch.get('ok'):
            code = fetch.get('error') or 'ENGINE_UNREACHABLE'
            if code == 'WINDOW_UNAVAILABLE':
                code = 'ENGINE_UNREACHABLE'
            self._audit('web_open', {'url': url[:200], 'error': code},
                        'open', 'error')
            return _error(code, fetch.get('message') or '页面打开失败',
                          fetch.get('hint'))
        html = fetch.get('html') or ''
        channel = fetch.get('channel')
        title = _extract_title(html)
        # 先取全量（max_chars=0 不截断）再自行截断——toolcache 需落完整正文
        ex = extract_main_content(html, selector or None, 0)
        if ex.get('extractor') == 'selector_miss':
            self._audit('web_open', {'url': url[:200]}, 'open', 'error')
            return _error('SELECTOR_NOT_FOUND',
                          '选择器未命中页面元素: %s' % (selector or '')[:80],
                          '可更换 selector 或省略该参数用自动提取')
        full_content = ex.get('content') or ''
        if not full_content.strip():
            self._audit('web_open', {'url': url[:200]}, 'open', 'error')
            return _error('EMPTY_CONTENT', '未能从页面提取到正文内容',
                          '该页可能是登录墙或动态渲染页，可在主窗口打开链接查看')
        truncated = len(full_content) > max_chars
        content = full_content[:max_chars] if truncated else full_content
        full_ref = None
        if truncated:
            cid = self._toolcache.cache(full_content)
            if cid:
                full_ref = 'toolcache:%s' % cid
        payload = {
            'ok': True, 'url': url, 'title': title, 'content': content,
            'truncated': truncated,
            'extractor': ex.get('extractor') or 'readability',
            'fetched_at': _utc_now(),
            'elapsed_ms': int((self._clock() - t0) * 1000),
            'max_chars': max_chars,
        }
        if full_ref:
            payload['full_ref'] = full_ref
        if channel:
            payload['channel'] = channel
        if len(full_content) < THIN_CONTENT_CHARS:
            payload['thin'] = True      # thin_warning：仍成功，面板提示可能需登录
        self._audit('web_open', {'url': url[:200], 'chars': len(content),
                                 'truncated': bool(truncated)}, 'open', 'ok')
        return payload

    # ================================================== 缓存统计（B3）
    def search_cache_stats(self):
        """实现 v1.8.0 B2：缓存统计（联调规范 §3.1 B3）。

        Returns:
            dict: ``{ok, entries, hits, misses, ttl_minutes, size_kb}``——
            entries/size_kb 按 ``~/.glm-chat/search_cache/`` 落盘文件实时统计；
            hits/misses 为进程内计数。读取类不落审计。
        """
        entries = 0
        size = 0
        try:
            for fn in os.listdir(self._cache_dir):
                if not fn.endswith('.json'):
                    continue
                fp = os.path.join(self._cache_dir, fn)
                try:
                    size += os.path.getsize(fp)
                    entries += 1
                except OSError:
                    continue
        except FileNotFoundError:
            pass
        except Exception as e:
            self._log.debug('缓存统计失败: %r', e)
        with self._lock:
            hits, misses = self._hits, self._misses
        return {'ok': True, 'entries': entries, 'hits': hits,
                'misses': misses, 'ttl_minutes': self._ttl,
                'size_kb': int(size / 1024)}

    # ================================================== 缓存层内部（C1）
    def _cache_key(self, engine, q_echo, site, filetype, time_range, lang):
        """归一化缓存键：engine + 检索式 + site/filetype/time_range/lang +
        URL 归一化后的检索 URL（§4.4 归一化 key 口径）→ sha1 十六进制。"""
        try:
            norm = _normalize_url(build_query_url(engine, {
                'query': q_echo, 'filetype': filetype,
                'time_range': time_range, 'lang': lang}))
        except ValueError:
            norm = q_echo
        material = '\x00'.join([
            str(engine or '').lower(), str(q_echo or ''),
            _norm_domain(site), str(filetype or '').lower(),
            str(time_range or '').lower(), str(lang or '').lower(), norm])
        return hashlib.sha1(material.encode('utf-8')).hexdigest()

    def _cache_get(self, key):
        """读缓存条目；TTL 外/损坏 → None（并顺手清过期文件，自清理）。"""
        fp = os.path.join(self._cache_dir, str(key) + '.json')
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return None
        except Exception as e:
            self._log.debug('缓存条目损坏，按未命中处理: %r', e)
            return None
        if not isinstance(data, dict) or 'results' not in data:
            return None
        fetched_ts = data.get('fetched_ts')
        try:
            fetched_ts = float(fetched_ts)
        except (TypeError, ValueError):
            return None
        if self._clock() - fetched_ts > self._ttl * 60:
            try:
                os.remove(fp)      # 过期自清理（陈旧边界 R6：TTL 外信息可能已变）
            except OSError:
                pass
            return None
        return data

    def _cache_put(self, key, entry):
        """写缓存条目（原子写；失败只 warning 不阻断搜索主流程）。"""
        fp = os.path.join(self._cache_dir, str(key) + '.json')
        try:
            from ..fio import atomic_write_json
            atomic_write_json(fp, entry)
        except Exception as e:
            self._log.warning('搜索缓存写入失败（不影响本次结果）: %r', e)

    # ================================================== 审计
    def _audit(self, op, detail, action, decision):
        """落 audit_log.jsonl（经 GuardService 单一口径 + 10MB 轮转）。

        op：web_search / web_open / search_takeover；search_status 与
        search_cache_stats 为读取类，不落审计（规范 §3.1 B3/B4）。
        """
        try:
            self._guard.audit(op, detail, action, decision)
        except Exception as e:
            self._log.warning('搜索审计写入失败: %r', e)
