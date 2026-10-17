/* ================= 端点抽象（v4 · 完全单端点） =================
 * 全 App 只有一个「当前端点」概念，由 36-connect.js 的预设状态机决定：
 * 「连接与模型」区块的预设下拉是唯一开关（GLM / DeepSeek / Moonshot / 通义千问 /
 * Ollama / LM Studio / vLLM / llama.cpp / LocalAI / 自定义）。
 *
 * 运行态派生（36-connect.js connectSyncState 写入，本模块只读）：
 * - providerState = {enabled, name(预设 id), base_url, model, key, prices} —— 云端与 GLM 共用；
 * - localState = {mode, base_url, model, ctx_window, tool_capable} —— 本地系预设派生，
 *   60-agent-loop 的本地模型分支继续依赖它（localState.model 优先）。
 *
 * GLM 判据（v4 改判）：provider_name === 'glm' 或 base_url 含 bigmodel.cn ——
 * 决定 thinking / reasoning_effort / web_search 工具 / 智能档 / 内置价格表。
 * 语义与合并前一致：GLM 端点全开，非 GLM（云端第三方 / 本地）全部关闭。
 */

/** Base URL 是否指向智谱官方域名（自定义预设填官方地址也按 GLM 对待）。 */
function isGlmBaseUrl(url) {
  return /bigmodel\.cn/i.test(String(url || ''));
}

/** 本地端点是否生效（本地系预设 + 有 base_url；本地端点无需 API Key）。 */
function localModeActive() {
  return !!(localState && localState.mode && localState.base_url);
}

/** chat/completions 拼接（base 已含则原样）。 */
function chatCompletionsOf(base) {
  const b = String(base || '').trim().replace(/\/+$/, '');
  if (!b) return '';
  return b.endsWith('/chat/completions') ? b : b + '/chat/completions';
}

/** 端点地址解析：45-request-debounce / 97-compact 的 fetch 目标。
 *  本地系预设 → localState.base_url；其余 → providerState.base_url；都空 → 官方 API_URL。 */
function resolveApiEndpoint() {
  if (localModeActive()) {
    const local = chatCompletionsOf(localState.base_url);
    if (local) return local;
  }
  const base = chatCompletionsOf((providerState && providerState.base_url) || '');
  if (base) return base;
  return API_URL;
}

/** 当前端点是否智谱 GLM（GLM 专属能力总开关）。
 *  判据（v4 D5）：provider_name === 'glm' 或 base_url 含 bigmodel.cn。 */
function isGlmEndpoint() {
  if (localModeActive()) return false;
  const st = providerState || {};
  const name = String(st.name || '').trim().toLowerCase();
  const base = String(st.base_url || '').trim();
  if (name === 'glm') return true;               // 判据一：预设即智谱官方
  if (name) return isGlmBaseUrl(base);           // 判据二：非 GLM 预设，只有填了官方域名才算
  return base ? isGlmBaseUrl(base) : true;       // 无端点信息 → 沿用 GLM 官方默认
}

/** 当前端点显示名（会话里 addSysTip 用）。 */
function currentEndpointName() {
  if (localModeActive()) return '本地 · ' + (localState.model || '?');
  if (isGlmEndpoint()) return 'GLM';
  const id = String((providerState && providerState.name) || '');
  const meta = (typeof connectPresetMeta === 'function') ? connectPresetMeta(id) : null;
  return (meta && meta.name) || id || 'custom';
}

/** 生效的 API Key：本地系免 Key；其余用合并块唯一的 Key 字段（#apiKey，
 *  旧运行态 providerState.key 作为内存回退）。
 *  所有请求入口（发送/重新生成/压缩/断点续跑）统一走此函数，避免端点切了 Key 没切。 */
function effectiveApiKey() {
  if (localModeActive()) return '';
  const el = document.getElementById('apiKey');
  const typed = el ? String(el.value || '').trim() : '';
  if (typed) return typed;
  return (providerState && providerState.key) ? String(providerState.key).trim() : '';
}

/** 价格表：本地系零费（A4）；非 GLM 云端端点用「高级 · 计费三价」；GLM 用内置 MODEL_PRICE。 */
function providerPriceFor(model) {
  if (localModeActive()) {
    return { in: 0, out: 0, cache: 0 };
  }
  if (!isGlmEndpoint() && providerState && providerState.prices) {
    const p = providerState.prices;
    const has = Number(p.in) > 0 || Number(p.out) > 0 || Number(p.cache) > 0;
    if (has) return { in: Number(p.in) || 0, out: Number(p.out) || 0, cache: Number(p.cache) || 0 };
  }
  return MODEL_PRICE[model] || MODEL_PRICE['glm-5.3-flashx'];
}

/** 品牌位 / 会话头标题：显示当前生效模型名（手动态取文本框）。 */
function updateBrandModel() {
  let txt = '';
  if (typeof connectModelValue === 'function') txt = connectModelValue();
  if (!txt) {
    const sel = document.getElementById('modelSelect');
    const v = sel ? String(sel.value || '') : '';
    txt = (v && v !== '__manual__' && v !== '__group__') ? v : '';
  }
  if (!txt) txt = 'glm-5.3-flash';
  const bm = document.getElementById('brandModel');
  const ht = document.getElementById('headerTitle');
  if (bm) bm.textContent = txt;
  if (ht) ht.textContent = txt;
}
