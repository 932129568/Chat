/* ================= 成本透明化（v1.2 R5） =================
 * 1) 会话头部实时「本会话约花费 ¥X」（标准输入/缓存命中/输出三价细分 → 75-token-stat 展示）
 * 2) 发送前预估费用区间（输入框聚焦/输入时刷新 #costEstimate）
 * 3) 1113 等错误码人话映射（humanizeApiError，60-agent-loop 错误路径使用）
 */

const ERROR_HUMANIZE = [
  [/1113|余额不足.*coding|coding plan/i,
    'GLM Coding Plan 仅限官方指定工具使用，API 直连会报 1113。\n可行操作：① 在 bigmodel.cn 充值按量付费并使用平台 API Key；② 或切换到自定义 OpenAI 兼容端点（设置 → 模型服务商）。'],
  [/\b401\b|invalid.*key| unauthorized/i, 'API Key 无效或未授权：请检查设置中的 Key 是否正确、是否属于所选服务商。'],
  [/\b403\b/i, '无权访问该端点（Key 权限不足或 IP 受限）。'],
  [/\b404\b/i, '端点地址不存在：请检查 Base URL（OpenAI 兼容端点通常需要 /v1 后缀）。'],
  [/\b429\b|rate.?limit/i, '请求过于频繁或额度耗尽：稍等片刻重试，或检查账户余额。'],
  [/failed to fetch|networkerror|ENOTFOUND|timeout/i, '网络连接失败：检查网络或代理；GLM 端点在国内直连通常无需代理。'],
];

/* 修复 B4（v1.5）：local 模式错误分类口径（与后端 classify_local_error 同文案）——
 * Ollama 特情（503 loading / 404 模型引导 / 401 免 Key / 400 超窗）。 */
const ERROR_HUMANIZE_LOCAL = [
  [/\b503\b|loading|is loading/i,
    '模型正在加载（本地服务器首次提问需 10-60s），已自动等待重试；反复出现请确认模型名或到「设置 → 本地模型」重新测试连接。'],
  [/\b404\b/i,
    '本地端点返回 404：① 模型名不存在（区分大小写）——请回模型清单重选；② 地址不对——Base URL 通常需要 /v1 后缀（如 http://localhost:11434/v1）。'],
  [/\b401\b/i, '未授权（401）：本地服务器通常无需 Key，请在设置中清空 API Key 重试。'],
  [/\b429\b/i, '本地服务器限流：稍等重试；持续出现请检查并发设置。'],
];

function humanizeApiError(msg, isLocal) {
  const raw = String(msg || '');
  const table = isLocal ? ERROR_HUMANIZE_LOCAL : ERROR_HUMANIZE;
  for (const [pat, text] of table) {
    if (pat.test(raw)) return text + '\n\n（原始错误：' + raw.slice(0, 300) + '）';
  }
  // 修复 B4：local 模式未命中本地表时回落通用表（不丢 1113 等既有映射）
  if (isLocal) {
    for (const [pat, text] of ERROR_HUMANIZE) {
      if (pat.test(raw)) return text + '\n\n（原始错误：' + raw.slice(0, 300) + '）';
    }
  }
  return raw;
}

/** 预估下一次请求费用（粗估：上下文字符数/1.7 ≈ token，加假定输出）。 */
function estimateNextCost(s) {
  let chars = 0;
  (s && s.messages ? s.messages : []).forEach(m => {
    const c = typeof m.content === 'string' ? m.content
      : Array.isArray(m.content) ? m.content.map(p => p.text || '').join('') : '';
    chars += c.length;
    if (m.tool_calls) chars += JSON.stringify(m.tool_calls).length;
  });
  const inputTokens = Math.ceil(chars / 1.7);
  const outputTokens = 1024;   // 假定一轮输出
  const model = providerState.enabled ? (providerState.model || '') : (document.getElementById('modelSelect')?.value || 'glm-5.3-flash');
  const p = providerPriceFor(model);
  const costIn = inputTokens * p.in / 1e6;
  const costOut = outputTokens * p.out / 1e6;
  return { inputTokens, low: costIn * 0.3 + costOut, high: costIn + costOut };
}

function updateCostEstimate() {
  const el = document.getElementById('costEstimate');
  if (!el) return;
  const s = getCurrentSession();
  if (!s || s.messages.length === 0) { el.textContent = ''; return; }
  const est = estimateNextCost(s);
  el.textContent = '下次发送预估 ¥' + est.low.toFixed(3) + '–' + est.high.toFixed(3) +
    '（含上下文 ' + est.inputTokens.toLocaleString() + ' tok，缓存命中取低值）';
}
