/* ================= 搜索面板（v1.8.0 B 域 U1，实现 v1.8.0 B2） =================
 * #searchPanel + .sp-*（纯新增 DOM，UI 契约只增不改——check_contract 验）：
 * 结果列表 / 原文预览 / 缓存来源标注 / 人工接管区 / 阶段 pill + 进度。
 * 契约口径（联调规范 §2/§3.1 + ux-flows 流程 1/2/3）：
 * - 三态状态机 idle/pending/success/error + 请求序号 last-wins
 *   （searchReqSeq，同 36-connect connectIdentifySeq 先例；pending 期间新
 *   触发 → seq+1 覆盖，旧请求返回后 seq!==searchReqSeq 静默丢弃）；
 * - ≥3s 可见等待：browser_search 在途期间 1s 轮询 search_status（§2.4 方案
 *   A：面板打开起、关闭/终态停；phase → 阶段 pill 文案轮换，P2 最短展示
 *   400ms 由 CSS 过渡承担）；
 * - CAPTCHA 接管（流程 2）：CAPTCHA_REQUIRED → 接管区（「请完成验证」+
 *   继续/放弃，面板不可关闭）→ browser_takeover continue 成功载荷渲染 /
 *   abort → CAPTCHA_ABORTED 人话；
 * - typeof 守卫（§2.5 vm 沙箱可测）：模块顶层不直接引用 window/document/
 *   localStorage，一律函数体内守卫或注入；callApi 统一经 spCallApi 四步
 *   （入口守卫 → 序号登记 → 竞速调用 → 序号校验）。
 * 挂载：110-boot.js loadAll 内 try{ searchPanelInit(); }catch（功能分级
 * 开关「浏览器搜索」默认开——spFeatureEnabled，localStorage 持久化）。
 * C 域批次：25-tool-exec.js executeToolRaw 新分支将调 searchPanelRunSearch
 * 驱动 Agent 工具循环的进度与结果渲染（本批只提供面板侧能力）。
 */
const SP_POLL_INTERVAL_MS = 1000;      // search_status 轮询间隔（§2.4）
const SP_STATUS_TIMEOUT_MS = 15000;    // 纯内存状态读，快失败（§2.1 表）
const SP_SEARCH_TIMEOUT_MS = 90000;    // browser_search（extract=full 时前端可传 150000）
const SP_OPEN_TIMEOUT_MS = 60000;      // browser_open（§2.1 表）
const SP_TAKEOVER_TIMEOUT_MS = 90000;  // browser_takeover（§2.1 表）
const SP_STATS_TIMEOUT_MS = 15000;     // search_cache_stats
// 后端 phase → 阶段文案（§2.3 四件套映射表；motion-spec §2.1 为动效真相源）
const SP_PHASE_TEXT = {
  understanding: '正在理解检索意图…',
  cache_check: '正在检查缓存…',
  window_loading: '正在打开搜索引擎…',
  urllib_fallback: '已切换轻量抓取（降级）…',
  extracting: '正在提取搜索结果…',
  filtering: '正在整理结果…',
  deep_extract: '正在读取正文…',
  validating: '正在校验结果…',
  reformulate: '正在改写检索式重试…',
  captcha: '需要人工验证',
  done: '搜索完成',
  failed: '搜索失败'
};
// 功能分级开关键（设置可单独关搜索；默认开——架构 §5 行为兼容）
const SP_FEATURE_KEY = 'glm_feat_search_v18';

let searchReqSeq = 0;          // last-wins 请求序号（每次触发递增，旧请求失效）
let searchPanelState = 'idle'; // idle|pending|success|error|captcha
let searchPollTimer = null;    // 1s 轮询定时器句柄
let searchTakeoverId = null;   // 当前接管会话（captcha 态非空）
let searchLastPayload = null;  // 最近一次成功载荷（原文预览/重渲染用）

/* ---------- typeof 守卫取值（§2.5：vm 沙箱无 DOM 不炸） ---------- */
function searchPanelEl() {
  return (typeof document !== 'undefined') ? document.getElementById('searchPanel') : null;
}
function spEl(id) {
  return (typeof document !== 'undefined') ? document.getElementById(id) : null;
}
function spFeatureEnabled() {
  try {
    if (typeof localStorage === 'undefined') return true;
    const v = localStorage.getItem(SP_FEATURE_KEY);
    return v === null || v === '1';   // 缺省 = 开（默认开）
  } catch (e) { return true; }
}
function spCallApi(name, args, timeoutMs) {
  // §2.1 四步之①入口守卫（与 callApi 既有口径一致，vm 下显式抛可断言）
  if (typeof callApi !== 'function') {
    throw new Error('pywebview bridge 未就绪: ' + name);
  }
  return callApi(name, args, timeoutMs);
}
function spToast(msg, kind) {
  if (typeof toast === 'function') toast(msg, kind || 'info');
}

/* ---------- 面板骨架（纯新增 DOM；动态创建，不碰 index.template.html） ---------- */
function searchPanelInit() {
  if (!spFeatureEnabled()) return false;          // 功能分级开关：关则不挂载
  if (searchPanelEl()) { searchPanelWire(); return true; }   // 幂等
  if (typeof document === 'undefined') return false;
  const panel = document.createElement('div');
  panel.id = 'searchPanel';
  panel.className = 'sp-root';
  panel.setAttribute('data-state', 'idle');
  panel.innerHTML =
    '<div class="sp-head">' +
      '<span class="sp-title">浏览器搜索</span>' +
      '<span class="sp-pill" id="spPill">就绪</span>' +
      '<button class="sp-fold" id="spFold" title="折叠/展开面板" aria-label="折叠/展开面板">▾</button>' +
      '<button class="sp-close" id="spClose" title="关闭面板（Esc）" aria-label="关闭面板">×</button>' +
    '</div>' +
    '<div class="sp-progress"><div class="sp-progress-bar" id="spProgressBar"></div></div>' +
    '<div class="sp-query">' +
      '<input class="sp-input" id="spInput" placeholder="输入检索词，如 python 教程" maxlength="500">' +
      '<button class="sp-search-btn" id="spSearchBtn">搜索</button>' +
    '</div>' +
    '<div class="sp-meta" id="spMeta"></div>' +
    '<div class="sp-takeover" id="spTakeover" style="display:none">' +
      '<div class="sp-takeover-title">🔒 搜索引擎要求人机验证</div>' +
      '<div class="sp-takeover-desc">请在弹出的窗口中完成验证，然后点击「继续」。</div>' +
      '<div class="sp-takeover-timer" id="spTakeoverTimer">已等待 0:00</div>' +
      '<div class="sp-takeover-btns">' +
        '<button class="sp-btn sp-btn-primary" id="spTakeoverContinue">继续</button>' +
        '<button class="sp-btn" id="spTakeoverAbort">放弃</button>' +
      '</div>' +
    '</div>' +
    '<div class="sp-results" id="spResults"></div>' +
    '<div class="sp-foot" id="spFoot"></div>';
  document.body.appendChild(panel);
  searchPanelWire();
  return true;
}
function searchPanelWire() {
  const close = spEl('spClose');
  if (close) close.addEventListener('click', () => searchPanelClose());
  const fold = spEl('spFold');
  if (fold) fold.addEventListener('click', () => searchPanelToggleFold());
  const btn = spEl('spSearchBtn');
  if (btn) btn.addEventListener('click', () => {
    const input = spEl('spInput');
    searchPanelRunSearch({ query: input ? input.value : '' });
  });
  const cont = spEl('spTakeoverContinue');
  if (cont) cont.addEventListener('click', () => searchPanelTakeoverAction('continue'));
  const ab = spEl('spTakeoverAbort');
  if (ab) ab.addEventListener('click', () => searchPanelTakeoverAction('abort'));
  /* v1.8.0 交互补全：Esc 关闭（captcha 态除外，与 × 同规则）+ 点面板外关闭。
     typeof 守卫：vm 沙箱 document 桩可能无 addEventListener（§2.5） */
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      const panel = searchPanelEl();
      if (!panel || !panel.classList.contains('show')) return;
      if (searchPanelState === 'captcha') {
        spToast('请先完成验证或点击「放弃」', 'warn');
        return;
      }
      searchPanelClose();
    });
    document.addEventListener('mousedown', (e) => {
      const panel = searchPanelEl();
      if (!panel || !panel.classList.contains('show')) return;
      if (e.target && e.target.closest && e.target.closest('#searchPanel')) return;
      if (searchPanelState === 'captcha') return;   // 接管中不误关
      searchPanelClose();
    });
  }
  searchPanelRefreshStats();
}

/* ---------- 折叠（只留头部+查询行；治「不能缩回去」） ---------- */
function searchPanelToggleFold() {
  const panel = searchPanelEl();
  if (!panel) return;
  panel.classList.toggle('sp-collapsed');
  const fold = spEl('spFold');
  if (fold) fold.title = panel.classList.contains('sp-collapsed') ? '展开面板' : '折叠面板';
}

/* ---------- 开/关（面板打开起轮询、关闭停；captcha 态不可关闭） ---------- */
function spManualOpen() {
  if (!searchPanelEl()) searchPanelInit();
  const panel = searchPanelEl();
  if (panel && panel.classList.contains('show')) { searchPanelClose(); return; }  // 再点=收起
  searchPanelOpen();
  const input = spEl('spInput');
  if (input) setTimeout(() => input.focus(), 60);
}
function searchPanelOpen() {
  const panel = searchPanelEl();
  if (!panel) return;
  if (panel.classList.contains('hiding')) {
    panel.classList.remove('hiding');   // 退场中途重开：直接落位
  }
  panel.classList.add('show');
  searchPanelRefreshStats();
  searchPanelStartPolling();
}
function searchPanelClose() {
  // ux-flows 流程 2④：takeover_prompting 面板不可关闭（只能继续/放弃）——
  // 防用户忽略后 Agent 永久挂起
  if (searchTakeoverId && searchPanelState === 'captcha') {
    spToast('请先完成验证或点击「放弃」', 'warn');
    return;
  }
  const panel = searchPanelEl();
  searchPanelStopPolling();
  if (!panel || !panel.classList.contains('show')) return;
  panel.classList.add('hiding');
  const done = () => {
    try { panel.classList.remove('show', 'hiding'); } catch (e) {}
  };
  if (typeof MOTION !== 'undefined' && !MOTION.instant()) {
    MOTION.onAnimEnd(panel, 'animationend', MOTION.compOut()).then(done);
  } else { done(); }
}

/* ---------- 三态 + last-wins 主入口（C 域 25-tool-exec 分发亦走此函数） ---------- */
async function searchPanelRunSearch(params) {
  const seq = ++searchReqSeq;                       // ②序号登记
  searchPanelSetState('pending');
  searchPanelOpen();                                // 打开即起轮询（≥3s 可见等待）
  const btn = spEl('spSearchBtn');
  if (btn) btn.disabled = true;                     // pending 防连点
  const bar = spEl('spProgressBar');
  if (bar) { bar.classList.add('indet'); bar.style.transform = ''; }   // 不确定进度扫光
  try {
    const raw = await spCallApi('browser_search', [params || {}],
      (params && params.extract === 'full') ? 150000 : SP_SEARCH_TIMEOUT_MS);  // ③竞速
    if (seq !== searchReqSeq) return;               // ④last-wins：旧请求静默失效
    const d = JSON.parse(raw || '{}');
    if (d && d.ok) {
      searchLastPayload = d;
      searchPanelRenderResults(d);
      searchPanelSetState('success');
    } else if (d && d.error && d.error.code === 'CAPTCHA_REQUIRED') {
      searchTakeoverId = d.error.takeover_id || null;
      searchPanelShowTakeover(d.error);
      searchPanelSetState('captcha');
    } else {
      searchPanelRenderError((d && d.error) || { code: 'INTERNAL', message: '搜索失败' });
      searchPanelSetState('error');
    }
  } catch (e) {
    if (seq !== searchReqSeq) return;
    searchPanelRenderError({ code: 'BRIDGE_TIMEOUT',
      message: (e && e.message) || String(e) });
    searchPanelSetState('error');
  } finally {
    const btn2 = spEl('spSearchBtn');
    if (btn2) btn2.disabled = false;                // 终态恢复（pending 防连点）
    const bar2 = spEl('spProgressBar');
    if (bar2) bar2.classList.remove('indet');       // 停不确定扫光（确定进度由 phase 驱动）
    searchPanelRefreshStats();
  }
}

/* ---------- 接管动作（流程 2 步骤 4a/4b） ---------- */
async function searchPanelTakeoverAction(action) {
  if (!searchTakeoverId) return;
  const seq = ++searchReqSeq;
  const cont = spEl('spTakeoverContinue');
  const ab = spEl('spTakeoverAbort');
  if (cont) cont.disabled = true;                   // 防连点（后端亦幂等）
  if (ab) ab.disabled = true;
  try {
    const raw = await spCallApi('browser_takeover', [searchTakeoverId, action],
      SP_TAKEOVER_TIMEOUT_MS);
    if (seq !== searchReqSeq) return;
    const d = JSON.parse(raw || '{}');
    if (d && d.ok) {
      searchTakeoverId = null;
      searchPanelHideTakeover();
      searchLastPayload = d;
      searchPanelRenderResults(d);
      searchPanelSetState('success');
      spToast('验证通过，继续搜索', 'ok');
      // v1.8.0 C 域：接管终态通知 Agent 循环（§2.4：成功载荷注入挂起的工具轮次；
      // typeof 守卫——vm 单模块沙箱无 60-agent-loop 时不炸）
      if (typeof harborTakeoverNotify === 'function') harborTakeoverNotify(d);
    } else if (d && d.error && d.error.code === 'CAPTCHA_REQUIRED') {
      const n = (d.error.retry || 1);
      spToast('验证未通过，请重试（' + n + '/' + (d.error.max_retries || 3) + '）', 'warn');
    } else if (d && d.error && d.error.code === 'CAPTCHA_ABORTED') {
      searchTakeoverId = null;
      searchPanelHideTakeover();
      searchPanelRenderError(d.error);
      searchPanelSetState('error');
      spToast('已放弃本次搜索', 'warn');
      // v1.8.0 C 域：放弃终态同样通知（Agent 换引擎/告知用户）
      if (typeof harborTakeoverNotify === 'function') harborTakeoverNotify(d);
    } else {
      searchPanelRenderError((d && d.error) || { code: 'INTERNAL', message: '操作失败' });
      searchPanelSetState('error');
    }
  } catch (e) {
    if (seq !== searchReqSeq) return;
    spToast('接管操作失败：' + ((e && e.message) || String(e)), 'err');
  } finally {
    if (cont) cont.disabled = false;
    if (ab) ab.disabled = false;
    searchPanelRefreshStats();
  }
}

/* ---------- 1s 轮询（§2.4 方案 A：打开起、关闭/终态停） ---------- */
function searchPanelStartPolling() {
  if (searchPollTimer || typeof setInterval === 'undefined') return;
  searchPollTimer = setInterval(searchPanelPollOnce, SP_POLL_INTERVAL_MS);
}
function searchPanelStopPolling() {
  if (searchPollTimer && typeof clearInterval !== 'undefined') {
    clearInterval(searchPollTimer);
  }
  searchPollTimer = null;
}
async function searchPanelPollOnce() {
  let d = null;
  try {
    const raw = await spCallApi('search_status', [], SP_STATUS_TIMEOUT_MS);
    d = JSON.parse(raw || '{}');
  } catch (e) {
    return;   // 轮询快失败不打扰（下一拍再试；后端继续跑不依赖轮询）
  }
  if (!d || !d.ok) return;
  if (d.active === false && d.phase !== 'done' && d.phase !== 'failed') {
    searchPanelStopPolling();                       // 无活跃搜索 → 停
    return;
  }
  searchPanelSetPhase(d.phase, d);
  if (d.phase === 'done' || d.phase === 'failed' ||
      (d.active === false && d.phase !== 'captcha')) {
    searchPanelStopPolling();                       // 终态停（captcha 续轮）
  }
}

/* ---------- 渲染 ---------- */
function searchPanelSetState(state) {
  searchPanelState = state;
  const panel = searchPanelEl();
  if (panel) panel.setAttribute('data-state', state);
  const pill = spEl('spPill');
  if (pill) {
    pill.textContent = state === 'pending' ? '进行中'
      : state === 'captcha' ? '需要人工验证'
      : state === 'success' ? '已完成'
      : state === 'error' ? '失败' : '就绪';
    pill.className = 'sp-pill' + (state === 'error' ? ' sp-pill-err'
      : state === 'captcha' ? ' sp-pill-warn'
      : state === 'success' ? ' sp-pill-ok' : '');
  }
}
function searchPanelSetPhase(phase, d) {
  const pill = spEl('spPill');
  if (pill && SP_PHASE_TEXT[phase]) pill.textContent = SP_PHASE_TEXT[phase];
  const bar = spEl('spProgressBar');
  if (bar && typeof d === 'object' && d) {
    if (d.phase === 'deep_extract' && d.deep_extract && d.deep_extract.total) {
      // 确定进度 scaleX(done/total)（§2.3 deep_extract 行）
      bar.style.transform = 'scaleX(' +
        (d.deep_extract.done / d.deep_extract.total) + ')';
    } else if (typeof d.progress_pct === 'number') {
      bar.style.transform = 'scaleX(' + (d.progress_pct / 100) + ')';
    }
  }
  if (d && d.phase === 'captcha' && d.takeover && d.takeover.takeover_id) {
    if (d.takeover.takeover_id !== searchTakeoverId) {
      searchTakeoverId = d.takeover.takeover_id;
      searchPanelShowTakeover({ takeover_id: searchTakeoverId, retry: d.takeover.retries,
        max_retries: d.takeover.max_retries });
    }
    const timer = spEl('spTakeoverTimer');
    if (timer && typeof d.takeover.elapsed_s === 'number') {
      const s = d.takeover.elapsed_s;
      const mm = Math.floor(s / 60), ss = ('0' + (s % 60)).slice(-2);
      timer.textContent = '已等待 ' + mm + ':' + ss;
    }
  }
}
function searchPanelRenderResults(d) {
  const meta = spEl('spMeta');
  if (meta) {
    const cached = d.source === 'cache';
    const secs = d.elapsed_ms != null ? (d.elapsed_ms / 1000).toFixed(1) + 's' : '';
    meta.innerHTML =
      '<span class="sp-src' + (cached ? ' cache' : '') + '" id="spSrcBadge">' +
        (cached ? '缓存' : '实时') + '</span>' +
      '<span class="sp-q">' + spEsc(d.query || '') + '</span>' +
      '<span class="sp-e">' + spEsc(d.engine || '') + '</span>' +
      (d.channel ? '<span class="sp-ch">' + (d.channel === 'urllib' ? '直连抓取' : '窗口') + '</span>' : '') +
      (secs ? '<span class="sp-t">' + secs + '</span>' : '') +
      (d.deep_extract ? '<span class="sp-deep">深度提取 ' + d.deep_extract.done +
        '/' + d.deep_extract.total + (d.deep_extract.failed ? '（' + d.deep_extract.failed + ' 篇失败）' : '') + '</span>' : '') +
      (d.truncated ? '<span class="sp-trunc">结果已截断，全文见 full_ref</span>' : '');
  }
  const box = spEl('spResults');
  if (!box) return;
  box.innerHTML = '';
  const list = d.results || [];
  if (!list.length) {
    const empty = document.createElement('div');
    empty.className = 'sp-empty';
    empty.textContent = '未找到相关内容，建议调整关键词后重试。';
    box.appendChild(empty);
    return;
  }
  list.forEach((r, i) => {
    const item = document.createElement('div');
    item.className = 'sp-item';
    const top = document.createElement('div');
    top.className = 'sp-item-top';
    const pos = document.createElement('span');
    pos.className = 'sp-pos';
    pos.textContent = String(r.position || (i + 1));
    top.appendChild(pos);
    const a = document.createElement('a');
    a.className = 'sp-item-title';
    a.href = r.url || '#';
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = r.title || r.url || '（无标题）';
    a.title = r.title || r.url || '';   // 截断时悬浮全称
    top.appendChild(a);
    item.appendChild(top);
    if (r.snippet) {
      const sn = document.createElement('div');
      sn.className = 'sp-item-snippet';
      sn.textContent = r.snippet;
      item.appendChild(sn);
    }
    if (r.extra && r.extra.content) {
      const ct = document.createElement('div');
      ct.className = 'sp-item-content';
      ct.textContent = r.extra.content.slice(0, 400) +
        (r.extra.content.length > 400 ? '…' : '');
      item.appendChild(ct);
    }
    const foot = document.createElement('div');
    foot.className = 'sp-item-foot';
    const dom = document.createElement('span');
    dom.className = 'sp-item-domain';
    dom.textContent = r.domain || '';
    foot.appendChild(dom);
    if (r.date) {
      const dt = document.createElement('span');
      dt.className = 'sp-item-date';
      dt.textContent = r.date;
      foot.appendChild(dt);
    }
    item.appendChild(foot);
    box.appendChild(item);
  });
}
function searchPanelRenderError(e) {
  const meta = spEl('spMeta');
  if (meta) meta.innerHTML = '<span class="sp-src err">错误</span>';
  const box = spEl('spResults');
  if (!box) return;
  box.innerHTML = '';
  const d = document.createElement('div');
  d.className = 'sp-error';
  d.textContent = (e && e.message) || '搜索失败';
  box.appendChild(d);
  if (e && e.hint) {
    const h = document.createElement('div');
    h.className = 'sp-error-hint';
    h.textContent = e.hint;
    box.appendChild(h);
  }
}
function searchPanelShowTakeover(err) {
  const box = spEl('spTakeover');
  if (box) box.style.display = '';
  const pill = spEl('spPill');
  if (pill) { pill.textContent = '需要人工验证'; pill.className = 'sp-pill sp-pill-warn'; }
  const cont = spEl('spTakeoverContinue');
  if (cont && err && err.retry) {
    cont.textContent = '继续（重试 ' + err.retry + '/' + (err.max_retries || 3) + '）';
  } else if (cont) {
    cont.textContent = '继续';
  }
}
function searchPanelHideTakeover() {
  searchTakeoverId = null;
  const box = spEl('spTakeover');
  if (box) box.style.display = 'none';
  const timer = spEl('spTakeoverTimer');
  if (timer) timer.textContent = '已等待 0:00';
}
async function searchPanelRefreshStats() {
  const foot = spEl('spFoot');
  if (!foot) return;
  try {
    const raw = await spCallApi('search_cache_stats', [], SP_STATS_TIMEOUT_MS);
    const d = JSON.parse(raw || '{}');
    if (d && d.ok) {
      foot.textContent = '缓存 ' + d.entries + ' 条 · 命中 ' + d.hits +
        ' / 未命中 ' + d.misses + ' · ' + d.size_kb + 'KB · TTL ' + d.ttl_minutes + ' 分钟';
    }
  } catch (e) { /* 脚注统计失败静默（不打扰主流程） */ }
}
function spEsc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
