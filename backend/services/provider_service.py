# -*- coding: utf-8 -*-
"""模型服务商服务（v1.2 R6）：OpenAI 兼容端点连通性测试。

provider 抽象原则（PRD R6）：
- GLM 保持默认，自定义端点是 opt-in；
- 端点配置（Base URL / Key / 模型名 / 价格）存 config.json 新增键
  （save_config 合并逻辑已支持，契约差分只比对测试写入的键，不受影响）；
- token 统计与计费按服务商返回的 usage 字段适配（usage 结构 OpenAI 兼容端点一致，
  价格差异由前端价格表按模型名/自定义配置解析）；
- 测试连接走后端 urllib（避免 WebView 前端跨域限制）。
"""
import json

from ..logging_setup import get_logger
from .mcp_transport_http import urlopen_no_redirect   # 修复 S15：禁自动重定向，防凭证跨域泄漏


def normalize_base_url(url):
    """归一化 Base URL：去首尾空白与斜杠；空返回 ''。不猜测 /v1（由用户/预设负责）。"""
    u = str(url or '').strip().rstrip('/')
    return u


def chat_completions_url(base_url):
    base = normalize_base_url(base_url)
    if not base:
        return ''
    if base.endswith('/chat/completions'):
        return base
    return base + '/chat/completions'


class ProviderService:
    def __init__(self):
        self._log = get_logger()

    def test_endpoint(self, base_url, api_key, model, timeout=15):
        """向 OpenAI 兼容端点发一次最小 chat 请求，返回连通性结果。

        返回 {ok: true, model, reply} 或 {ok: false, error, status}。
        """
        url = chat_completions_url(base_url)
        if not url:
            return json.dumps({'ok': False, 'error': '缺少 Base URL'}, ensure_ascii=False)
        if not str(api_key or '').strip():
            return json.dumps({'ok': False, 'error': '缺少 API Key'}, ensure_ascii=False)
        if not str(model or '').strip():
            return json.dumps({'ok': False, 'error': '缺少模型名'}, ensure_ascii=False)
        body = json.dumps({
            'model': str(model).strip(),
            'messages': [{'role': 'user', 'content': 'ping'}],
            'max_tokens': 5,
            'stream': False,
        }).encode('utf-8')
        # 修复 S15：http:// 明文端点显式警告（API Key 明文出网）
        insecure_warn = None
        if url.lower().startswith('http://'):
            insecure_warn = ('当前端点是 http:// 明文传输，API Key 会暴露给网络中间人，'
                             '强烈建议改用 https://')
            self._log.warning('provider 测试端点为 http 明文: %s', url)
        try:
            import urllib.request
            import urllib.error
            req = urllib.request.Request(url, data=body, method='POST', headers={
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + str(api_key).strip(),
            })
            try:
                with urlopen_no_redirect(req, timeout=timeout) as resp:
                    # 修复 建议㉒（二轮）：读全量无上限 → 64KB 上限（病态端点回吐 GB 级会 OOM）
                    raw = resp.read(64 * 1024)
                    try:
                        data = json.loads(raw.decode('utf-8', 'replace'))
                    except Exception as je:
                        return json.dumps({'ok': False, 'status': resp.status,
                                           'error': '响应不是合法 JSON: %s' % je},
                                          ensure_ascii=False)
                    # 修复 建议㉔：HTTP 200 但结构异常不再静默吞错
                    if not isinstance(data, dict) or 'choices' not in data:
                        return json.dumps({'ok': False,
                                           'error': 'HTTP 200 但响应结构异常（非 OpenAI 兼容格式）: '
                                                    + json.dumps(data, ensure_ascii=False)[:120]},
                                          ensure_ascii=False)
                    reply = ''
                    try:
                        reply = data['choices'][0]['message'].get('content', '') or ''
                    except Exception:
                        pass
                    out = {'ok': True, 'url': url, 'model': model,
                           'reply': str(reply)[:80]}
                    if insecure_warn:
                        out['warning'] = insecure_warn
                    return json.dumps(out, ensure_ascii=False)
            except urllib.error.HTTPError as e:
                snippet = ''
                try:
                    snippet = e.read().decode('utf-8', 'replace')[:300]
                except Exception:
                    pass
                hint = humanize_http_error(e.code, snippet)
                return json.dumps({'ok': False, 'error': 'HTTP %d: %s' % (e.code, hint or snippet),
                                   'status': e.code}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'ok': False, 'error': '连接失败: %s' % e}, ensure_ascii=False)


def humanize_http_error(status, body=''):
    """常见 HTTP 错误码人话映射（与前端 humanizeApiError 保持一致口径）。"""
    if status == 401:
        return 'API Key 无效或未授权'
    if status == 403:
        return '无权访问该端点（Key 权限不足或 IP 限制）'
    if status == 404:
        return '端点地址不存在（请检查 Base URL 是否需要 /v1 后缀）'
    if status == 429:
        return '请求过于频繁或余额不足'
    # 修复 建议㉒（二轮）：307/308 重定向人话（禁重定向下端点配置了跳转时用户看得懂）
    if status in (307, 308):
        return '端点返回 %d 重定向（已禁跟随以防凭证跨域泄漏）；请在 Base URL 中直接填写最终地址' % status
    if '1113' in body:
        return 'GLM Coding Plan 仅限官方工具调用，API 直连请使用按量付费 Key'
    return ''
