/* ================= A7 请求防抖 ================= */
// 修复 建议㊵（二轮）：可 abort 的 sleep——原定时器不响应 signal，用户点停止后
// 重试 sleep 仍要睡满 1-2s 才退出
const sleep = (ms, signal) => new Promise((resolve, reject) => {
  if (signal && signal.aborted) return reject(new DOMException('Aborted', 'AbortError'));
  const t = setTimeout(resolve, ms);
  if (signal) signal.addEventListener('abort', () => {
    clearTimeout(t);
    reject(new DOMException('Aborted', 'AbortError'));
  }, { once: true });
});
async function fetchGLMStream(payload, signal) {
  // 修复 B4（v1.5）：local 模式 503「model is loading」按后端口径指数退避
  // [2,4,8]s（上限 120s 总等待），期间 loading 态由 60-agent-loop 的等待计时器呈现；
  // 非 local 保持原重试策略（429/5xx 一次）。
  const _isLocal = (typeof localState !== 'undefined' && localState.mode);
  const _sleepAbortable = (ms) => sleep(ms, signal);
  let attempt = 0;
  const LOADING_BACKOFF = [2000, 4000, 8000];
  while (true) {
    try {
      const resp = await fetch(resolveApiEndpoint(), {   // v1.2 R6：GLM 默认 / 自定义 OpenAI 兼容端点
        method: 'POST', signal,
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + payload.apiKey },
        body: JSON.stringify(payload.body || payload)
      });
      if (_isLocal && resp.status === 503 && attempt < LOADING_BACKOFF.length) {
        await _sleepAbortable(LOADING_BACKOFF[attempt]); attempt++; continue;   // 模型加载中：退避重试
      }
      if ((resp.status === 429 || resp.status >= 500) && attempt < 1) {
        attempt++; await _sleepAbortable(resp.status === 429 ? 2000 : 1200, signal); continue;
      }
      return resp;
    } catch (e) {
      if (e.name === 'AbortError') throw e;
      if (attempt < 1) { attempt++; await _sleepAbortable(1000, signal); continue; }
      throw e;
    }
  }
}
