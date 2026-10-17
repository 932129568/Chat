/* ================= UX-3 会话搜索（v1.4） =================
 * 跨会话关键词检索：入口（侧栏「⌕ 搜索」）→ 模态输入 → 遍历全部 sessions.messages
 * （user/assistant/tool 内容 + 工具调用名/参数，大小写不敏感）→ 结果列表
 * （会话标题 / 命中时间 / 片段 ±80 字 + <mark> 高亮）→ 点击跳转到该会话并滚动到命中消息。
 * 纯前端零后端零新 js_api；DOM/CSS 全部纯新增（UI 契约只增不改）。
 */

/** 片段内所有命中词包 <mark>（大小写不敏感；先 escape 再插标记，杜绝注入）。 */
function _markSnippet(text, kw) {
  const lower = text.toLowerCase();
  const k = kw.toLowerCase();
  const klen = k.length;
  let out = '', i = 0;
  for (;;) {
    const pos = lower.indexOf(k, i);
    if (pos < 0) { out += escapeHtml(text.slice(i)); break; }
    out += escapeHtml(text.slice(i, pos)) + '<mark>' + escapeHtml(text.slice(pos, pos + klen)) + '</mark>';
    i = pos + klen;
    if (i >= text.length) break;
  }
  return out;
}

function _msgSearchText(msg) {
  let text = '';
  if (typeof msg.content === 'string') text = msg.content;
  else if (Array.isArray(msg.content)) {
    text = msg.content.map(p => p.text || (p.type === 'image_url' ? '[图片]' : p.type === 'video_url' ? '[视频]' : '')).join(' ');
  }
  if (msg.tool_calls) {
    text += ' ' + msg.tool_calls.map(tc => (tc.function ? tc.function.name + ' ' + (tc.function.arguments || '') : '')).join(' ');
  }
  return text;
}

function runSessionSearch(kwRaw) {
  const box = document.getElementById('sessionSearchResults');
  if (!box) return;
  const kw = String(kwRaw || '').trim();
  if (!kw) {
    box.innerHTML = '<div class="search-empty">输入关键词，跨全部历史会话搜索（大小写不敏感）</div>';
    return;
  }
  const lower = kw.toLowerCase();
  const hits = [];
  const HIT_CAP = 100;   // 结果上限：防会话海量时 DOM 爆炸（提示截断）
  outer:
  for (const s of (sessions || [])) {
    const msgs = s.messages || [];
    for (let idx = 0; idx < msgs.length; idx++) {
      if (hits.length >= HIT_CAP) break outer;
      const text = _msgSearchText(msgs[idx]);
      if (!text) continue;
      const pos = text.toLowerCase().indexOf(lower);
      if (pos < 0) continue;
      hits.push({ s: s, idx: idx, pos: pos, text: text });
    }
  }
  if (!hits.length) {
    box.innerHTML = '<div class="search-empty">没有会话命中「' + escapeHtml(kw) + '」</div>';
    return;
  }
  const SNIP = 80;
  let html = '';
  for (const h of hits) {
    const from = Math.max(0, h.pos - SNIP);
    const to = Math.min(h.text.length, h.pos + kw.length + SNIP);
    const snippet = (from > 0 ? '…' : '') + _markSnippet(h.text.slice(from, to), kw) + (to < h.text.length ? '…' : '');
    const roleName = { user: '我', assistant: 'AI', tool: '工具', system: '系统' }[h.s.messages[h.idx].role] || h.s.messages[h.idx].role;
    html += `<div class="search-hit" onclick="jumpToSearchHit('${_escId(h.s.id)}', ${h.idx})">
      <div class="search-hit-head">
        <span class="search-hit-title">${escapeHtml(h.s.title || '新对话')}</span>
        <span class="search-hit-meta">${escapeHtml(roleName)} · ${escapeHtml(formatTime(h.s.updatedAt))}</span>
      </div>
      <div class="search-hit-snippet">${snippet}</div>
    </div>`;
  }
  box.innerHTML = html + (hits.length >= HIT_CAP ? '<div class="search-empty">结果过多仅显示前 ' + HIT_CAP + ' 条，请用更精确的关键词</div>' : '');
}

function openSessionSearch() {
  const m = _modalRoot();
  m.innerHTML =
    '<div class="modal-mask"></div>' +
    '<div class="modal-card search-card" role="dialog" aria-modal="true">' +
    '  <div class="modal-title">搜索全部会话</div>' +
    '  <input class="modal-input" id="sessionSearchInput" placeholder="关键词（大小写不敏感，回车立即搜索）">' +
    '  <div class="search-results" id="sessionSearchResults"><div class="search-empty">输入关键词，跨全部历史会话搜索（大小写不敏感）</div></div>' +
    '  <div class="modal-btns"><button class="modal-btn modal-cancel">关闭</button></div>' +
    '</div>';
  const input = m.querySelector('#sessionSearchInput');
  let timer = null;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => runSessionSearch(input.value), 150);   // 防抖 150ms：≤1s 返回验收
  });
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { clearTimeout(timer); runSessionSearch(input.value); } });
  m.querySelector('.modal-cancel').onclick = _closeModal;
  m.querySelector('.modal-mask').onclick = _closeModal;
  setTimeout(() => input.focus(), 30);
}

/** 点击搜索结果：切换会话 → 滚动到命中消息 → 高亮闪烁 2.4s。 */
function jumpToSearchHit(sessionId, midx) {
  _closeModal();
  if (isStreaming) { toast('正在生成回复，请先停止', 'warn'); return; }
  if (currentSessionId !== sessionId) switchSession(sessionId);
  requestAnimationFrame(() => {
    const el = document.querySelector('#chatContainer [data-midx="' + String(midx) + '"]');
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.add('search-hit-flash');
      setTimeout(() => el.classList.remove('search-hit-flash'), 2400);
    } else {
      const box = document.getElementById('chatContainer');
      if (box) box.scrollTop = box.scrollHeight;   // 目标消息未产出 DOM（空内容等）→ 兜底滚到底
    }
  });
}
