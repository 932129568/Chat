/* ================= v1.8.0 · 输入区重构（74-input-plus.js） =================
 * 用户实测（WorkBuddy 同款）：附件 4 钮平铺占位 → 「+」弹出菜单；
 * 省出位置加模型选择 chip（图标+模型名+caret）→ 弹出模型列表
 * （数据源 = 设置区 modelSelect 的 options，双向同步不改契约 id）；
 * 列表底部「配置自定义模型」→ 跳设置「连接与模型」块并闪光定位。
 */

const PLUS_ITEMS = [
  { key: 'img', label: '图片', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>' },
  { key: 'vid', label: '视频', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="14" height="14" rx="2"/><path d="M16 10l6-3v10l-6-3z"/></svg>' },
  { key: 'file', label: '文本文件', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/></svg>' },
  { key: 'zip', label: '压缩包 (zip)', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 8v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l2 3h5a2 2 0 0 1 2 2z"/><path d="M10 12h4M12 12v3"/></svg>' }
];

function ipEl(id) {
  return (typeof document !== 'undefined') ? document.getElementById(id) : null;
}

/* ---- 自定义模型库（localStorage：harbor_custom_models；config.json 零污染） ---- */
const CN_MODELS_KEY = 'harbor_custom_models';
function ipCustomModels() {
  try { return JSON.parse(localStorage.getItem(CN_MODELS_KEY) || '[]').filter(x => typeof x === 'string'); }
  catch (e) { return []; }
}
function ipCustomSave(list) {
  try { localStorage.setItem(CN_MODELS_KEY, JSON.stringify(list)); } catch (e) {}
}
function ipCustomAdd(name) {
  const list = ipCustomModels();
  if (list.indexOf(name) === -1) { list.unshift(name); ipCustomSave(list); }
}
function ipCustomRemove(name) {
  ipCustomSave(ipCustomModels().filter(x => x !== name));
}

/* ---------- 「+」附件菜单 ---------- */
function ipPlusToggle() {
  const pop = ipEl('atPop');
  const mc = ipEl('mcPop');
  if (mc) mc.classList.remove('on');
  if (!pop) return;
  if (pop.classList.contains('on')) { pop.classList.remove('on'); return; }
  ipPlusRender();
  pop.classList.add('on');
}
function ipPlusRender() {
  const pop = ipEl('atPop');
  if (!pop) return;
  pop.innerHTML = PLUS_ITEMS.map(it =>
    '<button type="button" class="at-item" data-key="' + it.key + '">' +
    '<span class="at-ic">' + it.icon + '</span><span>' + it.label + '</span></button>').join('');
  pop.querySelectorAll('.at-item').forEach(btn => {
    btn.addEventListener('click', () => {
      const key = btn.getAttribute('data-key');
      const input = ipEl(key + 'Input');
      if (input) input.click();
      pop.classList.remove('on');
    });
  });
}

/* ---------- 模型选择 chip ---------- */
function ipModelCurrentName() {
  const sel = ipEl('modelSelect');
  if (sel && sel.selectedOptions && sel.selectedOptions[0]) {
    return sel.selectedOptions[0].textContent.trim() || '选择模型';
  }
  return '选择模型';
}
function ipModelRefresh() {
  const nameEl = ipEl('modelChipName');
  if (nameEl) nameEl.textContent = ipModelCurrentName();
}
function ipModelToggle() {
  const pop = ipEl('mcPop');
  const at = ipEl('atPop');
  if (at) at.classList.remove('on');
  if (!pop) return;
  if (pop.classList.contains('on')) { pop.classList.remove('on'); return; }
  ipModelRender();
  pop.classList.add('on');
}
function ipModelRender() {
  const pop = ipEl('mcPop');
  if (!pop) return;
  const sel = ipEl('modelSelect');
  const cur = sel ? sel.value : '';
  const esc = (t) => (typeof escapeHtml === 'function' ? escapeHtml(String(t)) : String(t));
  // 预设/识别模型（来自设置区模型流）
  let rows = '';
  if (sel) {
    for (const opt of sel.options) {
      if (opt.value && ipCustomModels().indexOf(opt.value) !== -1) continue;   // 自定义项不重复列
      rows += '<button type="button" class="mc-item' + (opt.value === cur ? ' on' : '') +
        '" data-val="' + String(opt.value).replace(/"/g, '&quot;') + '">' +
        '<span class="mc-name">' + esc(opt.textContent) + '</span>' +
        (opt.value === cur ? '<span class="mc-check">✓</span>' : '') + '</button>';
    }
  }
  if (!rows) rows = '<div class="mc-empty">暂无预设模型，请先在设置中识别</div>';
  // 自定义模型区（可删）
  const customs = ipCustomModels();
  const customRows = customs.map(m =>
    '<div class="mc-item' + (m === cur ? ' on' : '') + '" data-val="' + esc(m) + '">' +
      '<span class="mc-name">' + esc(m) + '</span>' +
      (m === cur ? '<span class="mc-check">✓</span>' : '') +
      '<button type="button" class="mc-del" data-del="' + esc(m) + '" title="删除该自定义模型">✕</button>' +
    '</div>').join('');
  // 手动输入行（点击展开输入框）
  const manual = '<div class="mc-manual-row" id="mcManualRow">' +
    '<button type="button" class="mc-item mc-add" id="mcAddBtn"><span class="mc-name">＋ 手动输入模型名…</span></button>' +
    '<div class="mc-add-form" id="mcAddForm" style="display:none;">' +
      '<input type="text" id="mcAddInput" placeholder="模型名，回车确认（如 deepseek-v4.1）" spellcheck="false">' +
    '</div></div>';
  pop.innerHTML = '<div class="mc-pop-head">选择模型</div>' +
    '<div class="mc-list">' + rows + '</div>' +
    (customs.length ? '<div class="mc-sec">自定义模型</div><div class="mc-list mc-custom-list">' + customRows + '</div>' : '') +
    manual +
    '<button type="button" class="mc-config">配置自定义模型 →</button>';

  // 选择（预设区 + 自定义区共用）
  pop.querySelectorAll('.mc-item[data-val]').forEach(btn => {
    if (btn.classList.contains('mc-add')) return;
    btn.addEventListener('click', (e) => {
      if (e.target.closest && e.target.closest('.mc-del')) return;
      const val = btn.getAttribute('data-val');
      if (sel) {
        sel.value = val;
        if (typeof onModelChange === 'function') { try { onModelChange(val); } catch (err) {} }
      }
      ipModelRefresh();
      pop.classList.remove('on');
    });
  });
  // 删除自定义模型
  pop.querySelectorAll('.mc-del').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      ipCustomRemove(btn.getAttribute('data-del'));
      ipModelRender();   // 重渲染（删除后若当前模型被删不切状态——仅从库移除）
    });
  });
  // 手动输入：展开 → 回车加入并选用
  const addBtn = ipEl('mcAddBtn'), addForm = ipEl('mcAddForm'), addInput = ipEl('mcAddInput');
  if (addBtn && addForm && addInput) {
    addBtn.addEventListener('click', () => {
      addForm.style.display = '';
      addInput.focus();
    });
    const commit = () => {
      const v = addInput.value.trim();
      if (!v) { addForm.style.display = 'none'; return; }
      ipCustomAdd(v);
      if (sel) {
        sel.value = v;
        if (typeof onModelChange === 'function') { try { onModelChange(v); } catch (err) {} }
      }
      ipModelRefresh();
      ipModelRender();
      addInput.value = '';
      addForm.style.display = 'none';
    };
    addInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); commit(); } });
    addInput.addEventListener('blur', () => { if (!addInput.value.trim()) addForm.style.display = 'none'; });
  }
  const cfg = pop.querySelector('.mc-config');
  if (cfg) cfg.addEventListener('click', () => {
    pop.classList.remove('on');
    ipGotoModelSettings();
  });
}

/** 跳设置「连接与模型」块：切面板 → 滚动入视 → 一次性闪光定位。 */
function ipGotoModelSettings() {
  if (typeof switchPanel === 'function') switchPanel('settings');
  setTimeout(() => {
    const block = ipEl('cmBlock');
    if (!block) return;
    block.scrollIntoView({ behavior: (typeof MOTION !== 'undefined' && MOTION.instant()) ? 'auto' : 'smooth', block: 'start' });
    block.classList.remove('cn-flash');
    void block.offsetWidth;
    block.classList.add('cn-flash');
    setTimeout(() => block.classList.remove('cn-flash'), 1600);
  }, 260);   // 等面板切换淡入落位
}

/* ---------- 初始化 ---------- */
function inputPlusInit() {
  if (typeof document === 'undefined') return false;
  if (ipEl('atPop')) return true;
  const row = document.querySelector('.input-row');
  if (!row) return false;
  row.style.position = 'relative';
  // 「+」钮替换原 4 个附件钮的可见性（DOM 保留旧钮防 onclick 契约回归——
  //  改用 CSS 隐藏旧钮，新 + 钮复用同一批隐藏 file input）
  const plus = document.createElement('button');
  plus.type = 'button';
  plus.id = 'plusBtn';
  plus.className = 'tool-btn';
  plus.title = '添加附件';
  plus.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>';
  plus.addEventListener('click', (e) => { e.stopPropagation(); ipPlusToggle(); });
  row.insertBefore(plus, row.firstChild);
  // 模型 chip（send 钮前）
  const send = ipEl('sendBtn');
  const chip = document.createElement('button');
  chip.type = 'button';
  chip.id = 'modelChip';
  chip.className = 'model-chip';
  chip.title = '选择模型';
  chip.innerHTML = '<svg class="mc-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a4 4 0 0 1 4 4v1a4 4 0 0 1-1 2.6V14a4 4 0 0 1-8 0v-3.4A4 4 0 0 1 6 8V7a4 4 0 0 1 4-4z"/><path d="M8 21h8M12 18v3"/></svg>' +
    '<span id="modelChipName">选择模型</span>' +
    '<svg class="mc-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>';
  chip.addEventListener('click', (e) => { e.stopPropagation(); ipModelToggle(); });
  if (send) row.insertBefore(chip, send); else row.appendChild(chip);
  // 两个浮层
  const atPop = document.createElement('div');
  atPop.id = 'atPop';
  atPop.className = 'at-pop';
  row.appendChild(atPop);
  const mcPop = document.createElement('div');
  mcPop.id = 'mcPop';
  mcPop.className = 'mc-pop';
  row.appendChild(mcPop);
  // 空白关闭
  document.addEventListener('click', (e) => {
    const at = ipEl('atPop'), mc = ipEl('mcPop');
    if (e.target.closest && (e.target.closest('#atPop') || e.target.closest('#plusBtn'))) return;
    if (at) at.classList.remove('on');
    if (e.target.closest && (e.target.closest('#mcPop') || e.target.closest('#modelChip'))) return;
    if (mc) mc.classList.remove('on');
  });
  ipModelRefresh();
  // 设置区模型流变化时同步 chip（connectFillModels 已存在——挂个轮询兜底太糙，
  //  改用 MutationObserver 监听 modelSelect 子列表与选中项）
  const sel = ipEl('modelSelect');
  if (sel && typeof MutationObserver !== 'undefined') {
    new MutationObserver(() => ipModelRefresh()).observe(sel, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
    sel.addEventListener('change', () => ipModelRefresh());
  }
  return true;
}
