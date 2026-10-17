# -*- coding: utf-8 -*-
"""MCP Streamable HTTP 传输（v1.3 R1）：urllib POST + MCP-Protocol-Version 头 + SSE 解析。

设计口径（架构 §3.3 / 规范 lifecycle）：
- urllib（禁 httpx/requests——零第三方依赖铁律）。
- 请求头：Content-Type / Accept(json+sse) / MCP-Protocol-Version: 2025-06-18 / 用户 headers。
  修复 ⑫：协议头强制覆盖用户 headers（用户 headers 不再能覆盖协议头）；HTTPError 也回收
  Mcp-Session-Id。
- Mcp-Session-Id 会话头：响应返回则后续请求携带；404 → 由 client 层清 session 重连一次；
  close() 时 best-effort 发 HTTP DELETE 释放服务端会话（修复 ⑪）。
- 修复 S15：禁用自动重定向（自定义 handler，302 不再跨域转发 Authorization/会话头）；
  宿主替换过 urllib.request.urlopen（测试桩/嵌入方）时尊重宿主实现。
- 响应双解析：application/json → 单帧；text/event-stream → 增量读（修复 S14：
  原 resp.read() 阻塞到 EOF，keepalive 可让 60s 超时名存实亡；现按事件流式解析，
  拿到响应帧即返回，整体有 watchdog 超时）。SSE 事件按空行切分、聚合多行 data、剥 BOM
  （修复 W16）；流中通知/服务器请求帧经 on_frame 回调上交 client（修复 W15）。
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from ..logging_setup import get_logger
from .mcp_client import MCP_PROTOCOL_VERSION
from .mcp_pool import HttpConnectionPool

_NOTIFY_TIMEOUT = 10          # 通知/DELETE 等 fire-and-forget 请求的超时
_SSE_CHUNK = 64 * 1024
_MAX_RESP_BYTES = 32 * 1024 * 1024   # 修复 S1（v1.5.1）：池化路径响应体防 OMM 上限
# （不采用 provider 的 64KB——MCP 工具结果帧天然可达数百 KB，
#   64KB 会砍断 read_file 等大结果；SSE 路径另由 watchdog deadline 保护）

# import 时捕获的 stdlib urlopen 引用（DI 接缝：宿主替换后走宿主实现）
_STDLIB_URLOPEN = urllib.request.urlopen


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """修复 S15：不跟随任何重定向——urllib 默认会把 Authorization 等敏感头
    原样复制到重定向目标（含跨主机），恶意端点 302 即窃凭证。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_safe_opener = None


def urlopen_no_redirect(req, timeout=None):
    """不跟随重定向的 urlopen；宿主替换过 urllib.request.urlopen 时用宿主的。"""
    fn = urllib.request.urlopen
    if fn is not _STDLIB_URLOPEN:
        return fn(req, timeout=timeout)
    global _safe_opener
    if _safe_opener is None:
        _safe_opener = urllib.request.build_opener(_NoRedirectHandler())
    return _safe_opener.open(req, timeout=timeout)


class HttpTransportError(Exception):
    """HTTP 传输层错误（携带 HTTP 状态码，供上层区分 404 会话过期）。"""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


class HttpTransport:
    """Streamable HTTP 传输：post(obj, timeout) → 响应 dict；无状态、无长连接。

    修复 S1（v1.5.1）：连接池化——per host:port 复用 http.client 连接
    （keep-alive / 空闲 60s 回收 / 错误连接不污染池）。安全口径逐条保留：
    no-redirect（http.client 本就不跟随 3xx，显式拒绝并带 code）、协议头强制
    覆盖（_build_headers 不变）、Mcp-Session-Id 回收（含错误响应）、SSE 增量读
    （watchdog 不变）。宿主替换过 urlopen（测试桩/嵌入方）时自动回落原 urllib
    路径（DI 接缝保留，既有用例零修改）。
    """

    def __init__(self, url: str, headers: dict = None, logger=None, pool=None):
        self._log = logger or get_logger()
        self._url = str(url or '')
        self._headers = {str(k): str(v) for k, v in (headers or {}).items()}
        self._session_id = None
        self._closed = False
        self.on_frame = None     # client 注入：SSE 流中通知/服务器请求帧的处理器（W15）
        # 修复 S1：每传输一个池（同 transport 同 URL 同 host:port，复用最大化）
        self._pool = pool if pool is not None else HttpConnectionPool()

    @property
    def session_id(self):
        return self._session_id

    def reset_session(self):
        """清会话 id（client 层 404 重连驱动）。"""
        self._session_id = None

    def _build_headers(self):
        headers = dict(self._headers)          # 用户 headers 垫底
        # 修复 ⑫：协议头强制覆盖，用户 headers 不再能覆盖协议头
        headers['Content-Type'] = 'application/json'
        headers['Accept'] = 'application/json, text/event-stream'
        headers['MCP-Protocol-Version'] = MCP_PROTOCOL_VERSION
        if self._session_id:
            headers['Mcp-Session-Id'] = self._session_id
        return headers

    def post(self, obj: dict, timeout: float):
        """POST 一个 JSON-RPC 消息并返回响应 dict。异常抛 HttpTransportError。

        修复 S1（v1.5.1）：宿主未替换 urlopen → 连接池路径（复用连接）；
        宿主替换过（测试桩/嵌入方）→ 回落原 urllib 路径（DI 接缝）。"""
        if self._closed:
            raise HttpTransportError('HTTP 传输已关闭')
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        headers = self._build_headers()
        if urllib.request.urlopen is not _STDLIB_URLOPEN:
            return self._post_urllib(body, headers, timeout, obj)
        return self._post_pooled(body, headers, timeout, obj)

    def _post_urllib(self, body, headers, timeout, obj):
        """原 urllib 路径（测试桩/嵌入方回落；行为与 v1.3.2 一致）。"""
        req = urllib.request.Request(self._url, data=body, headers=headers, method='POST')
        try:
            resp = urlopen_no_redirect(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            # 修复 ⑫：错误响应也可能携带新的 Mcp-Session-Id，照常回收
            try:
                sid = e.headers.get('Mcp-Session-Id') if e.headers else None
                if sid:
                    self._session_id = sid
            except Exception:
                pass
            try:
                detail = e.read().decode('utf-8', 'replace')[:200]
            except Exception:
                detail = ''
            raise HttpTransportError('HTTP %s: %s' % (e.code, detail or e.reason), code=e.code)
        except urllib.error.URLError as e:
            raise HttpTransportError('连接失败: %s' % getattr(e, 'reason', e))
        except Exception as e:
            raise HttpTransportError('请求失败: %s' % e)
        return self._consume_response(resp, timeout, obj)

    def _post_pooled(self, body, headers, timeout, obj):
        """修复 S1（v1.5.1）：http.client 连接池路径。

        安全口径：no-redirect（3xx 显式拒绝带 code，http.client 本就不跟随）；
        协议头走 _build_headers（用户 headers 垫底+协议头覆盖，⑫ 不变）；
        Mcp-Session-Id 回收（成功+错误双路径）；响应体 32MB 防 OOM 上限；
        SSE 增量读与 watchdog 原样复用（S14/W16）。"""
        u = urllib.parse.urlsplit(self._url)
        path = u.path or '/'
        if u.query:
            path += '?' + u.query
        conn = self._pool.acquire(self._url)
        try:
            conn.timeout = float(timeout)     # 请求级超时覆盖连接默认 30s
        except Exception:
            pass
        healthy = False
        try:
            conn.request('POST', path, body=body, headers=headers)
            resp = conn.getresponse()
            # no-redirect：3xx 不当成功处理（防跨域泄露 Authorization/会话头）
            if 300 <= resp.status < 400:
                healthy = False
                raise HttpTransportError('重定向响应已拒绝（no-redirect 安全口径）',
                                         code=resp.status)
            if resp.status >= 400:
                # 修复 ⑫：错误响应也回收 Mcp-Session-Id；错误连接不还池（服务端可能已关）
                try:
                    sid = resp.getheader('Mcp-Session-Id')
                    if sid:
                        self._session_id = sid
                except Exception:
                    pass
                try:
                    detail = resp.read(4096).decode('utf-8', 'replace')[:200]
                except Exception:
                    detail = ''
                raise HttpTransportError('HTTP %s: %s' % (resp.status, detail),
                                         code=resp.status)
            healthy = True
            try:
                sid = resp.getheader('Mcp-Session-Id')
                if sid:
                    self._session_id = sid
            except Exception:
                pass
            return self._consume_response(resp, timeout, obj, from_pool=True)
        except HttpTransportError:
            raise
        except Exception as e:
            healthy = False
            raise HttpTransportError('请求失败: %s' % e)
        finally:
            self._pool.release(conn, healthy=healthy)
    def _consume_response(self, resp, timeout, obj, from_pool=False):
        """响应消费（池化/urllib 双路径共用）：SSE 增量读 / JSON 解析 / 空体处理。

        urllib addinfourl 与 http.client.HTTPResponse 均有 .headers，读取口径统一。
        Mcp-Session-Id 回收在此共用（成功路径；错误路径在各 post_* 内回收）。"""
        try:
            sid = resp.headers.get('Mcp-Session-Id') if resp.headers else None
            if sid:
                self._session_id = sid
        except Exception:
            pass
        try:
            ctype = (resp.headers.get('Content-Type', '') or '') if resp.headers else ''
        except Exception:
            ctype = ''
        if 'text/event-stream' in ctype.lower():
            return self._read_sse(resp, timeout, obj)   # 修复 S14：流式增量读
        try:
            if from_pool:
                raw = resp.read(_MAX_RESP_BYTES + 1)    # 修复 S1：防 OMM 上限
                if len(raw) > _MAX_RESP_BYTES:
                    raise HttpTransportError('响应体超过 32MB 上限')
            else:
                raw = resp.read()
        finally:
            try:
                resp.close()
            except Exception:
                pass
        if not raw or not raw.strip():
            # 修复 建议㉓（二轮）：请求类 POST 收到 202/204 空体时显式报错——原静默
            # 返回 {}，调用方 _unwrap 得到无意义的「id 不匹配」而非真实原因；
            # 通知类（无 id）保持静默容忍（规范允许 202 空响应）。
            if isinstance(obj, dict) and obj.get('id') is not None:
                raise HttpTransportError('服务器返回 202/204 空响应（请求未被处理）')
            return {}                          # 通知类 202 空响应
        try:
            return json.loads(raw.decode('utf-8'))
        except Exception as e:
            raise HttpTransportError('响应不是合法 JSON: %s' % e)

    # ---- SSE（S14/W16）----
    def _read_sse(self, resp, timeout, req_obj):
        """增量读 SSE 流：拿到本次请求的响应帧即返回；通知/服务器请求帧上交 on_frame。

        watchdog：整体时限 = timeout（keepalive 注释帧不能续命——修复 S14）。
        """
        deadline = time.monotonic() + max(1.0, float(timeout or 30))
        buf = b''
        # 无增量读接口的响应对象（如测试桩）退化为一次性读全量
        reader = getattr(resp, 'read1', None)
        if reader is None:
            raw = resp.read()
            return self._parse_sse(raw, req_obj)
        while True:
            if time.monotonic() > deadline:
                raise HttpTransportError('SSE 响应整体超时（watchdog）')
            try:
                chunk = reader(_SSE_CHUNK)
            except Exception as e:
                raise HttpTransportError('SSE 读取失败: %s' % e)
            if not chunk:
                break                            # EOF
            buf += chunk
            # 按空行切事件（兼容 \n\n 与 \r\n\r\n）
            while True:
                ev, buf = self._pop_event(buf)
                if ev is None:
                    break
                # 修复 W15（二轮）：增量路径单个坏 data 帧不应杀死整个请求
                #（与一次性路径 skip 坏帧行为对齐）
                try:
                    frame = self._frame_from_event(ev)
                except HttpTransportError as e:
                    self._log.warning('SSE 坏帧已跳过（增量路径）: %r', e)
                    continue
                if frame is None:
                    continue                     # 注释帧/缺 data 帧跳过
                if self._is_response_frame(frame, req_obj):
                    return frame
                self._dispatch_frame(frame)      # 通知/服务器请求（W15）
        # EOF 兜底：缓冲区里可能还有末帧
        if buf.strip():
            try:
                frame = self._frame_from_event(buf)
            except HttpTransportError:
                frame = None
            if frame is not None:
                if self._is_response_frame(frame, req_obj):
                    return frame
                self._dispatch_frame(frame)
        raise HttpTransportError('SSE 响应无匹配 data 帧')

    @staticmethod
    def _pop_event(buf):
        """从缓冲区弹出一个完整 SSE 事件（空行分隔）。返回 (event_bytes, rest) 或 (None, buf)。

        修复 W14（二轮）：取两个分隔符中位置更靠前者——原优先级固定 \r\n\r\n > \n\n，
        混合 EOL 流（\n\n 先出现）会被跨事件合并导致解析失败。"""
        best_i, best_sep = -1, None
        for sep in (b'\r\n\r\n', b'\n\n'):
            i = buf.find(sep)
            if i >= 0 and (best_i < 0 or i < best_i):
                best_i, best_sep = i, sep
        if best_i >= 0:
            return buf[:best_i], buf[best_i + len(best_sep):]
        return None, buf

    def _frame_from_event(self, ev):
        """修复 W16：聚合同一事件的多行 data（规范：多 data 行以 \n 拼接）；剥 BOM。"""
        text = ev.decode('utf-8', 'replace')
        if text.startswith('\ufeff'):
            text = text.lstrip('\ufeff')
        data_lines = []
        for line in text.splitlines():
            if line.startswith('\ufeff'):
                line = line.lstrip('\ufeff')
            if line.startswith('data:'):
                data_lines.append(line[5:].lstrip(' '))
        if not data_lines:
            return None
        payload = '\n'.join(data_lines).strip()
        if not payload:
            return None
        try:
            return json.loads(payload)
        except Exception as e:
            raise HttpTransportError('SSE data 帧解析失败: %s' % e)

    @staticmethod
    def _is_response_frame(frame, req_obj):
        """响应帧判定：无 method 字段的 dict；有 id 时须匹配请求 id。

        修复 W16（二轮）：原不匹配 id，陈旧/乱序帧会误杀请求——现严格匹配；
        规范允许错误帧 id=null；无 id 的 result 帧视为本请求响应（单请求读语境）。"""
        if not isinstance(frame, dict) or 'method' in frame:
            return False
        if req_obj is None:
            return True
        fid = frame.get('id')
        if fid is None:
            return True          # 无 id 的响应帧（测试/宽松服务器）——单请求语境下即本请求响应
        return str(fid) == str(req_obj.get('id'))

    def _dispatch_frame(self, frame):
        """流内通知/服务器请求帧上交 client（W15）；服务器请求由 client 回 -32601。"""
        cb = self.on_frame
        if cb is None:
            return
        try:
            cb(frame)
        except Exception as e:
            self._log.warning('SSE 流内帧处理异常: %r', e)

    def _parse_sse(self, raw: bytes, req_obj=None) -> dict:
        """一次性解析完整 SSE 字节串：取首个响应帧；通知帧上交（修复 W15/W16）。"""
        text = raw.decode('utf-8', 'replace')
        if text.startswith('\ufeff'):
            text = text.lstrip('\ufeff')
        # 按空行切事件，逐个聚合 data 行
        events = []
        for chunk in text.replace('\r\n', '\n').split('\n\n'):
            if chunk.strip():
                events.append(chunk.encode('utf-8'))
        if not events:
            events = [raw]
        first_error = None
        for ev in events:
            try:
                frame = self._frame_from_event(ev)
            except HttpTransportError as e:
                if first_error is None:
                    first_error = e
                continue
            if frame is None:
                continue
            if req_obj is None or self._is_response_frame(frame, req_obj):
                return frame
            self._dispatch_frame(frame)
        if first_error is not None:
            raise first_error
        raise HttpTransportError('SSE 响应无 data 帧')

    def send(self, obj: dict):
        """fire-and-forget POST（服务器发起请求的 -32601 回复等；W15 配套）。"""
        try:
            self.post(obj, _NOTIFY_TIMEOUT)
        except Exception as e:
            self._log.debug('HTTP 回帧发送失败: %r', e)

    def close(self) -> None:
        """修复 ⑪：关闭时 best-effort 发 HTTP DELETE 释放服务端会话（原会话泄漏）。
        修复 S1（v1.5.1）：DELETE 走池化路径（复用连接发完再释放），并关闭整个池。"""
        if self._closed:
            return
        self._closed = True
        sid = self._session_id
        self._session_id = None
        if sid:
            try:
                headers = dict(self._headers)
                headers['MCP-Protocol-Version'] = MCP_PROTOCOL_VERSION
                headers['Mcp-Session-Id'] = sid
                u = urllib.parse.urlsplit(self._url)
                path = u.path or '/'
                if u.query:
                    path += '?' + u.query
                if urllib.request.urlopen is not _STDLIB_URLOPEN:
                    req = urllib.request.Request(self._url, headers=headers, method='DELETE')
                    try:
                        resp = urlopen_no_redirect(req, timeout=5)
                        try:
                            resp.close()
                        except Exception:
                            pass
                    except Exception as e:
                        self._log.debug('HTTP 会话 DELETE 失败（忽略）: %r', e)
                else:
                    conn = None
                    try:
                        conn = self._pool.acquire(self._url)
                        conn.request('DELETE', path, headers=headers)
                        resp = conn.getresponse()
                        if 300 <= resp.status < 400:
                            pass                     # no-redirect：忽略即可
                        else:
                            try:
                                resp.read(4096)
                            except Exception:
                                pass
                    except Exception as e:
                        self._log.debug('HTTP 会话 DELETE 失败（忽略）: %r', e)
                    finally:
                        if conn is not None:
                            self._pool.release(conn, healthy=False)   # DELETE 后不还池
            except Exception:
                pass
        try:
            self._pool.close()
        except Exception:
            pass
