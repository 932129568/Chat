/* ================= 成本透明化（v1.2 R5） =================
 * 1) 会话头部实时「本会话约花费 ¥X」（标准输入/缓存命中/输出三价细分 → 75-token-stat 展示）
 * 2) 发送前预估费用区间（输入框聚焦/输入时刷新 #costEstimate）
 * 3) 1113 等错误码人话映射（humanizeApiError，60-agent-loop 错误路径使用）
 */

const ERROR_HUMANIZE = [
  [/1113|余额不足.*coding|coding plan/i,
    'GLM Coding Plan 仅限官方指定工具使用，API 直连会报 1113。\n可行操作：① 在 bigmodel.cn 充值按量付费并使用平台 API Key；② 或切换到自定义 OpenAI 兼容端点（设置 → 模型服务商）。'],
  [/\b401\b|invalid.*key|unauthorized/i, 'API Key 无效或未授权：请检查设置中的 Key 是否正确、是否属于所选服务商。'],
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

/* 实现 v1.6 T3：GitHub Models 免费层 429 人话映射（外部核实 2026-10，方案 §9：
 * GitHub 用响应头区分「请求频率(RPM)」与「每日配额(RPD)」）。从响应头解析
 * （x-ratelimit-remaining / retry-after 等，键名容忍大小写与别名）；
 * 解析失败返回 null → 调用方回落通用 429 文案（T14 验收两分支 100% 覆盖）。 */
const GITHUB_429_RPM_TEXT =
  '请求频率超限（GitHub 免费层约 15 RPM）：已到每分钟请求上限。\n可行操作：① 等待约 1 分钟窗口重置后重试；' +
  '② 合并工具调用轮次、读类并行发起，减少请求数；③ 高频使用请切换 DeepSeek/GLM 付费层。';
const GITHUB_429_RPD_TEXT =
  '每日配额耗尽（GitHub 免费层约 150 RPD）：今日免费额度已用完。\n可行操作：① 等待次日（UTC 0 点）额度重置；' +
  '② 切换 DeepSeek/GLM 付费层继续。';

/** 429 响应头 → RPM/RPD 人话（无法区分时返回 null，走通用文案）。 */
function humanizeGithub429(headers) {
  if (!headers || typeof headers !== 'object') return null;
  const flat = {};
  try {
    Object.keys(headers).forEach(k => { flat[String(k).toLowerCase()] = String(headers[k]); });
  } catch (e) { return null; }
  let rpmHit = false, rpdHit = false, retryAfter = 0;
  Object.keys(flat).forEach(k => {
    const v = parseInt(flat[k], 10);
    if (/retry-after/.test(k) && v > 0) { retryAfter = v; return; }
    if (!/remaining/.test(k)) return;
    // 语义判据（按外部源描述实现 + 容错）：键名含 day/daily/rpd → 日额度；
    // 含 min/request/rpm 或裸 remaining → 每分钟频率；仅 remaining==0 判超限。
    if (!(v === 0)) return;
    if (/day|daily|rpd/.test(k)) rpdHit = true;
    else if (/min|request|rpm/.test(k) || k === 'x-ratelimit-remaining') rpmHit = true;
  });
  const wait = retryAfter > 0 ? '\n（服务端 retry-after: ' + retryAfter + ' 秒）' : '';
  if (rpdHit) return GITHUB_429_RPD_TEXT + wait;
  if (rpmHit) return GITHUB_429_RPM_TEXT + wait;
  return null;
}

function humanizeApiError(msg, isLocal, headers) {
  const raw = String(msg || '');
  // 实现 v1.6 T3：429 且带响应头 → 先试 GitHub 频率/日额分支（云端路径；local 表优先）
  if (!isLocal && (/\b429\b/.test(raw) || /rate.?limit/i.test(raw))) {
    const gh = humanizeGithub429(headers);
    if (gh) return gh + '\n\n（原始错误：' + raw.slice(0, 300) + '）';
  }
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

// 修复 ㉚（三轮）：每按键全量估算改防抖——原每次 input 事件都全量遍历消息序列
// （含 JSON.stringify(tool_calls)）重算费用。200ms 合并窗口内多次调用只算一次，
// 末态必达（纯展示标签，无落盘依赖）。
let _costEstTimer = 0;
function updateCostEstimate() {
  clearTimeout(_costEstTimer);
  _costEstTimer = setTimeout(_updateCostEstimateNow, 200);
}
function _updateCostEstimateNow() {
  const el = document.getElementById('costEstimate');
  if (!el) return;
  const s = getCurrentSession();
  if (!s || s.messages.length === 0) { el.textContent = ''; return; }
  const est = estimateNextCost(s);
  el.textContent = '下次发送预估 ¥' + est.low.toFixed(3) + '–' + est.high.toFixed(3) +
    '（含上下文 ' + est.inputTokens.toLocaleString() + ' tok，缓存命中取低值）';
}
