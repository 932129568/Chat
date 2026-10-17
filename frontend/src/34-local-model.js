/* ================= v1.5 本地模型（预留接口层 UI） =================
 * 覆盖 roadmap 连接层 A（A1-A5）：预设 / 探测 / 模型清单 / 元数据展示 / 本地计费 / 无 Key 测试连接。
 * 适配层 B（B1-B5）判定接口已就绪（后端 local_model_service）：上下文窗口自适应阈值 /
 * 工具能力降级 / 慢推理状态 / Ollama 特情 / 本地 MCP 保守策略——Agent 主链路编排
 * （去 tools 重发、watchdog、确认文案注入）在后续迭代接线，本模块先落 UI 与配置面。
 *
 * 契约红线：
 * - js_api：local_probe / local_models / test_provider_endpoint(local=true)（均已登记 _V12_EXTRA）；
 * - 配置：local_* 键经 collectConfig → save_config 合并（运行期合法、测试期不触发）；
 * - DOM/CSS：全部纯新增（id：localModeEnable/localFields/localPreset/localProbeBtn/
 *   localBaseUrl/localModelsBtn/localModelSelect/localMetaBadge/localToolCapable/
 *   localCtxWindow/localTestBtn/localTestStatus/localProbeResult）。
 */
let localState = { mode: false, base_url: '', model: '', ctx_window: 0, tool_capable: 'auto' };

/* 预设表（与后端 LOCAL_PRESETS 同源；UI 一键填充 + 本地零费语义） */
const LOCAL_UI_PRESETS = {
  ollama:  { name: 'Ollama',          base_url: 'http://localhost:11434/v1' },
  lmstudio:{ name: 'LM Studio',       base_url: 'http://localhost:1234/v1' },
  vllm:    { name: 'vLLM',            base_url: 'http://localhost:8000/v1' },
  llamacpp:{ name: 'llama.cpp server',base_url: 'http://localhost:8080/v1' },
  localai: { name: 'LocalAI',         base_url: 'http://localhost:8080/v1' },
  custom:  { name: '自定义',           base_url: '' }
};

function loadLocalUI(cfg) {
  cfg = cfg || {};
  localState = {
    mode: !!cfg.local_mode,
    base_url: cfg.local_base_url || '',
    model: cfg.local_model || '',
    ctx_window: parseInt(cfg.local_ctx_window) || 0,
    tool_capable: cfg.local_tool_capable || 'auto'
  };
  const on = document.getElementById('localModeEnable');
  if (on) on.checked = localState.mode;
  const preset = document.getElementById('localPreset');
  if (preset) preset.value = cfg.local_preset || 'custom';
  const set = (id, v) => { const el = document.getElementById(id); if (el && v != null) el.value = v; };
  set('localBaseUrl', localState.base_url);
  set('localCtxWindow', localState.ctx_window || 0);
  set('localToolCapable', localState.tool_capable);
  refreshLocalModelOptions(localState.model ? [localState.model] : [], localState.model);
  syncLocalUiState();
  applyLocalMetaBadge();
}
function collectLocalConfig() {
  const g = id => (document.getElementById(id) || {}).value || '';
  const on = document.getElementById('localModeEnable');
  const preset = document.getElementById('localPreset');
  return {
    local_mode: on ? !!on.checked : false,
    local_preset: preset ? preset.value : 'custom',
    local_base_url: g('localBaseUrl').trim(),
    local_model: g('localModelSelect').trim(),
    local_ctx_window: parseInt(g('localCtxWindow')) || 0,
    local_tool_capable: g('localToolCapable') || 'auto'
  };
}
function applyLocalConfig() {
  const lc = collectLocalConfig();
  localState = { mode: !!lc.local_mode, base_url: lc.local_base_url, model: lc.local_model,
                 ctx_window: lc.local_ctx_window, tool_capable: lc.local_tool_capable };
  applyLocalMetaBadge();
}
function syncLocalUiState() {
  const wrap = document.getElementById('localFields');
  const on = document.getElementById('localModeEnable');
  if (wrap && on) wrap.style.display = on.checked ? '' : 'none';
}
function onLocalPresetChange(v) {
  const p = LOCAL_UI_PRESETS[v] || LOCAL_UI_PRESETS.custom;
  const base = document.getElementById('localBaseUrl');
  if (base && p.base_url) base.value = p.base_url;   // custom 不覆盖手输
  applyLocalMetaBadge();
}

/* ---- 元数据徽标（后端 model_meta 三级来源：精确表 → 前缀启发式 → 保守默认） ---- */
function applyLocalMetaBadge() {
  const badge = document.getElementById('localMetaBadge');
  if (!badge) return;
  const model = localState.model || (document.getElementById('localModelSelect') || {}).value || '';
  if (!model) { badge.textContent = '元数据待获取'; badge.className = 'local-badge'; return; }
  const ctx = localState.ctx_window > 0 ? localState.ctx_window : null;
  const meta = localMetaCache[model];
  if (meta) {
    const w = ctx || meta.ctx_window;
    const toolTxt = localState.tool_capable === 'off' ? '工具关'
      : localState.tool_capable === 'on' ? '工具开'
      : (meta.tool_capable ? '工具可用' : '工具存疑');
    badge.textContent = '窗口 ' + (w >= 1024 ? (w / 1024) + 'k' : w) + (meta.estimated ? '（估）' : '') + ' · ' + toolTxt;
    badge.className = 'local-badge ' + (meta.tool_capable ? 'on' : 'warn');
  } else {
    badge.textContent = ctx > 0 ? ('窗口 ' + (ctx >= 1024 ? (ctx / 1024) + 'k' : ctx) + '（手设）') : '元数据待获取';
    badge.className = 'local-badge';
  }
}
let localMetaCache = {};    // model -> {ctx_window, tool_capable, estimated}

/* ---- A2：并行探测（4 端口并行，各 2s 超时，总墙钟 ≤1s 目标） ---- */
async function localProbeNow() {
  const btn = document.getElementById('localProbeBtn');
  const box = document.getElementById('localProbeResult');
  if (btn) { btn.disabled = true; btn.textContent = '探测中…'; }
  try {
    const r = JSON.parse(await callApi('local_probe', []));
    if (box) box.innerHTML = '';
    if (!r.ok) { toast('探测失败：' + (r.error || ''), 'err'); return; }
    (r.reachable || []).forEach(it => {
      localMetaCache = {};    // 新探测结果 → 元数据缓存失效
      const row = document.createElement('div');
      row.className = 'local-probe-item ok';
      row.innerHTML = '<span class="dot"></span><span></span><span class="models"></span>';
      row.children[1].textContent = it.base_url + '（' + it.kind + ' · ' + it.latency_ms + 'ms）';
      row.children[2].textContent = (it.models || []).length + ' 个模型';
      if (box) box.appendChild(row);
      /* 命中预设 → 一键填充 base_url 并拉清单 */
      if (it.kind !== 'custom') {
        const base = document.getElementById('localBaseUrl');
        if (base) base.value = it.base_url;
        localLoadModels(it.base_url);
      }
    });
    (r.unreachable || []).forEach(it => {
      const row = document.createElement('div');
      row.className = 'local-probe-item';
      row.innerHTML = '<span class="dot"></span><span></span>';
      row.children[1].textContent = it.base_url + ' — ' + (it.error || '不可达');
      if (box) box.appendChild(row);
    });
    const hit = (r.reachable || []).length;
    toast(hit ? '探测到 ' + hit + ' 个本地服务器' : '未探测到本地服务器（' + r.elapsed_ms + 'ms）', hit ? 'ok' : 'warn');
    applyLocalMetaBadge();
  } catch (e) {
    toast('探测失败：' + e.message, 'err');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '探测本机'; }
  }
}

/* ---- A3：补拉模型清单（探测过期时用；返回 {id, ctx_window, tool_capable, estimated}） ---- */
async function localLoadModels(baseUrl) {
  const base = (baseUrl || (document.getElementById('localBaseUrl') || {}).value || '').trim();
  if (!base) { toast('请先填写 Base URL', 'warn'); return; }
  const btn = document.getElementById('localModelsBtn');
  if (btn) { btn.disabled = true; btn.textContent = '拉取中…'; }
  try {
    const r = JSON.parse(await callApi('local_models', [base]));
    if (!r.ok) { toast('获取模型清单失败：' + (r.error || ''), 'err'); return; }
    refreshLocalModelOptions((r.models || []).map(m => m.id), localState.model);
    localMetaCache = {};
    (r.models || []).forEach(m => { localMetaCache[m.id] = m; });
    applyLocalMetaBadge();
    if (typeof CS !== 'undefined' && CS.syncAll) CS.syncAll();
    toast('已获取 ' + (r.models || []).length + ' 个模型', 'ok');
  } catch (e) {
    toast('获取模型清单失败：' + e.message, 'err');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '拉取模型清单'; }
  }
}
function refreshLocalModelOptions(ids, keep) {
  const sel = document.getElementById('localModelSelect');
  if (!sel) return;
  const prev = keep || sel.value;
  sel.innerHTML = '';
  (ids || []).forEach(id => {
    const opt = document.createElement('option');
    opt.value = id; opt.textContent = id;
    sel.appendChild(opt);
  });
  if (prev && (ids || []).includes(prev)) sel.value = prev;
  else if ((ids || []).length) sel.value = ids[0];
  applyLocalMetaBadge();
}

/* ---- A5：本地测试连接（免 Key；503 冷启动返回 loading 态而非失败） ---- */
async function localTestNow() {
  const base = (document.getElementById('localBaseUrl') || {}).value.trim();
  const model = (document.getElementById('localModelSelect') || {}).value.trim();
  const btn = document.getElementById('localTestBtn');
  const st = document.getElementById('localTestStatus');
  if (!base || !model) { toast('请先填写 Base URL 并选择模型', 'warn'); return; }
  if (btn) { btn.disabled = true; btn.textContent = '测试中…'; }
  try {
    /* 复用 provider 测试通道 + local 标志（roadmap A5：不新建测试通道）；
       前端桥接 timeoutMs 放宽到 90s（冷启动加载可见） */
    const r = JSON.parse(await callApi('test_provider_endpoint', [base, '', model, 30, true], 90000));
    if (st) {
      if (r.ok && r.state === 'loading') {
        st.textContent = '⏳ ' + (r.message || '模型加载中'); st.style.color = 'var(--warn)';
      } else {
        st.textContent = r.ok ? '✓ 连接成功' + (r.reply ? '：' + r.reply : '') : '✗ ' + (r.error || '失败');
        st.style.color = r.ok ? 'var(--ok)' : 'var(--err)';
      }
    }
    toast(r.ok ? (r.state === 'loading' ? '模型加载中（等待即可）' : '本地端点连接成功') : '测试失败：' + (r.error || ''),
          r.ok ? 'ok' : 'err', { stay: !r.ok, detail: r.error || '' });
  } catch (e) {
    if (st) { st.textContent = '✗ ' + e.message; st.style.color = 'var(--err)'; }
    toast('本地端点测试失败：' + e.message, 'err');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '测试连接'; }
  }
}

/* ---- A4：本地模式计费标签（会话头部零费语义；UI 侧辅助函数） ---- */
function localBillingLabel() {
  return localState.mode ? '本地 · 0 费用' : null;
}

/* ---- B1：压缩阈值前端同口径（与后端 compact_threshold 一字不差）----
 * 窗口 × 档位系数：aggressive .4 / std .6 / relaxed .8；窗口三级来源
 * （元数据表 → 用户手设 → 默认 8k 保守）。GLM 128k×.6≈76.8k 与现标准档衔接；
 * 本地 8k 模型 → 4.8k 提前压缩（小窗口模型不爆窗）。 */
const COMPACT_LEVEL_RATIO = { aggressive: 0.4, std: 0.6, relaxed: 0.8 };
function compactThresholdLocal(ctxWindow, level) {
  let ctx = parseInt(ctxWindow) || 0;
  if (ctx <= 0) ctx = 8192;   // DEFAULT_LOCAL_META 保守值（与后端一致）
  const ratio = COMPACT_LEVEL_RATIO[level] || COMPACT_LEVEL_RATIO.std;
  return Math.round(ctx * ratio);
}
/** 当前 local 模式的压缩阈值（窗口取 localState 手设值 → 元数据缓存 → 默认）。 */
function localCompactThreshold() {
  const level = (document.getElementById('saverLevel') || {}).value || 'std';
  let ctx = localState.ctx_window > 0 ? localState.ctx_window : 0;
  if (ctx <= 0 && localState.model && localMetaCache[localState.model]) {
    ctx = localMetaCache[localState.model].ctx_window || 0;
  }
  return compactThresholdLocal(ctx, level);
}
