/* ================= 模型服务商抽象（v1.2 R6：OpenAI 兼容端点） =================
 * 原则：GLM 保持默认；自定义端点 opt-in。
 * providerState 从 config.json 的 provider_* 键加载（save_config 合并已支持，契约不受影响）。
 * GLM 专属请求字段（thinking / reasoning_effort / web_search 工具）仅在 GLM 端点发送。
 * v1.5 本地模式：localState 优先于 providerState——本机 OpenAI 兼容服务器
 * （Ollama/LM Studio/vLLM/llama.cpp/LocalAI），免 Key、零费用；local_mode 默认关，
 * 关闭时全部请求入口行为与本版之前完全一致。
 */

const PROVIDER_PRESETS = {
  deepseek: { name: 'DeepSeek', base_url: 'https://api.deepseek.com/v1', model: 'deepseek-v4.1-256k',
              prices: { in: 2, out: 8, cache: 0.4 } },
  custom:   { name: '自定义 OpenAI 兼容', base_url: '', model: '', prices: { in: 2, out: 8, cache: 0.4 } }
};

/** 端点地址解析：45-request-debounce 的 fetch 目标。v1.5：local 模式优先。 */
function resolveApiEndpoint() {
  if (localState && localState.mode && localState.base_url) {
    const base = String(localState.base_url).trim().replace(/\/+$/, '');
    if (base) return base.endsWith('/chat/completions') ? base : base + '/chat/completions';
  }
  if (providerState && providerState.enabled && providerState.base_url) {
    const base = String(providerState.base_url).trim().replace(/\/+$/, '');
    if (base) return base.endsWith('/chat/completions') ? base : base + '/chat/completions';
  }
  return API_URL;
}
function isGlmEndpoint() {
  if (localState && localState.mode && localState.base_url) return false;
  return !(providerState && providerState.enabled && providerState.base_url);
}
/** 当前端点显示名（本地模式 / 服务商 / GLM）。 */
function currentEndpointName() {
  if (localState && localState.mode && localState.base_url) return '本地 · ' + (localState.model || '?');
  if (providerState && providerState.enabled && providerState.base_url) return providerState.name || 'custom';
  return 'GLM';
}

/** 生效的 API Key：本地模式免 Key（本机服务器通常无鉴权）；自定义端点启用且填了 Key
 *  → 用服务商 Key；否则回退 GLM Key（#apiKey）。
 *  所有请求入口（发送/重新生成/压缩/断点续跑）统一走此函数，避免端点切了 Key 没切。 */
/** 本地模式是否生效（勾选启用 + 有 base_url；本地端点无需 API Key）。
 *  修复（2026-10-17）：此前 effectiveApiKey() 在本地模式返回 ''（fetch 层语义正确），
 *  但 sendMessage 的两处校验把 '' 当「未配置」误报「请先填入 API Key」——
 *  抽出本判断供发送前校验放行。 */
function localModeActive() {
  return !!(localState && localState.mode && localState.base_url);
}

function effectiveApiKey() {
  if (localModeActive()) return '';
  if (providerState && providerState.enabled && providerState.key) return String(providerState.key).trim();
  const el = document.getElementById('apiKey');
  return el ? el.value.trim() : '';
}

/** 价格表：本地模式零费（A4）；自定义端点优先，GLM 按 MODEL_PRICE。 */
function providerPriceFor(model) {
  if (localState && localState.mode && localState.base_url) {
    return { in: 0, out: 0, cache: 0 };
  }
  if (providerState && providerState.enabled && providerState.model === model) {
    const p = providerState.prices || {};
    return { in: Number(p.in) || 0, out: Number(p.out) || 0, cache: Number(p.cache) || 0 };
  }
  return MODEL_PRICE[model] || MODEL_PRICE['glm-5.3-flashx'];
}

/** 从 boot 加载的 cfg 回填 provider 设置 UI。 */
function loadProviderUI(cfg) {
  cfg = cfg || {};
  providerState = {
    enabled: !!cfg.provider_enabled,
    name: cfg.provider_name || 'custom',
    base_url: cfg.provider_base_url || '',
    model: cfg.provider_model || '',
    key: cfg.provider_key || '',
    prices: cfg.provider_prices || PROVIDER_PRESETS.custom.prices
  };
  const on = document.getElementById('providerEnabled');
  if (on) on.checked = providerState.enabled;
  const preset = document.getElementById('providerPreset');
  if (preset) preset.value = providerState.name || 'custom';
  const set = (id, v) => { const el = document.getElementById(id); if (el && v != null) el.value = v; };
  set('providerBase', providerState.base_url);
  set('providerModel', providerState.model);
  set('providerKey', providerState.key);
  const pr = providerState.prices || {};
  set('providerPriceIn', pr.in); set('providerPriceOut', pr.out); set('providerPriceCache', pr.cache);
  syncProviderUiState();
  updateBrandModel();
}
function syncProviderUiState() {
  const wrap = document.getElementById('providerFields');
  const on = document.getElementById('providerEnabled');
  if (wrap && on) wrap.style.display = on.checked ? '' : 'none';
}
function onProviderPresetChange(v) {
  const p = PROVIDER_PRESETS[v] || PROVIDER_PRESETS.custom;
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
  set('providerBase', p.base_url); set('providerModel', p.model);
  set('providerPriceIn', p.prices.in); set('providerPriceOut', p.prices.out); set('providerPriceCache', p.prices.cache);
}
async function testProviderNow() {
  const base = document.getElementById('providerBase').value.trim();
  const key = document.getElementById('providerKey').value.trim();
  const model = document.getElementById('providerModel').value.trim();
  const btn = document.getElementById('providerTestBtn');
  const st = document.getElementById('providerTestStatus');
  if (btn) { btn.disabled = true; btn.textContent = '测试中…'; }
  try {
    const r = JSON.parse(await callApi('test_provider_endpoint', [base, key, model]));
    if (st) {
      st.textContent = r.ok ? '✓ 连接成功' + (r.reply ? '：' + r.reply : '') : '✗ ' + (r.error || '失败');
      st.style.color = r.ok ? 'var(--ok)' : 'var(--err)';
    }
    toast(r.ok ? '端点连接成功' : '端点测试失败：' + (r.error || ''), r.ok ? 'ok' : 'err', { stay: !r.ok, detail: r.error || '' });
  } catch (e) {
    if (st) { st.textContent = '✗ ' + e.message; st.style.color = 'var(--err)'; }
    toast('端点测试失败：' + e.message, 'err');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '测试连接'; }
  }
}
function collectProviderConfig() {
  const on = document.getElementById('providerEnabled');
  return {
    provider_enabled: on ? on.checked : false,
    provider_name: (document.getElementById('providerPreset') || {}).value || 'custom',
    provider_base_url: (document.getElementById('providerBase') || {}).value || '',
    provider_model: (document.getElementById('providerModel') || {}).value || '',
    provider_key: (document.getElementById('providerKey') || {}).value || '',
    provider_prices: {
      in: parseFloat((document.getElementById('providerPriceIn') || {}).value) || 0,
      out: parseFloat((document.getElementById('providerPriceOut') || {}).value) || 0,
      cache: parseFloat((document.getElementById('providerPriceCache') || {}).value) || 0
    }
  };
}
/** 保存后刷新运行态与品牌位。 */
function applyProviderConfig() {
  const pc = collectProviderConfig();
  providerState = {
    enabled: !!pc.provider_enabled,
    name: pc.provider_name, base_url: pc.provider_base_url,
    model: pc.provider_model, key: pc.provider_key, prices: pc.provider_prices
  };
  updateBrandModel();
}
function updateBrandModel() {
  const txt = (localState && localState.mode && localState.model)
    ? localState.model
    : providerState.enabled && providerState.model
      ? providerState.model
      : (document.getElementById('modelSelect')?.value || 'glm-5.3-flash');
  const bm = document.getElementById('brandModel');
  const ht = document.getElementById('headerTitle');
  if (bm) bm.textContent = txt;
  if (ht) ht.textContent = txt;
}
