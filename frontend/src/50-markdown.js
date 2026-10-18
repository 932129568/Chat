/* ================= Markdown 渲染（高亮 + 节流） ================= */
if (window.DOMPurify) {
  DOMPurify.addHook('afterSanitizeAttributes', (n) => {
    if (n.tagName === 'A') { n.setAttribute('target', '_blank'); n.setAttribute('rel', 'noopener'); }
  });
}
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  // 修复 W29（三轮）：textContent→innerHTML 只转义 & < >，不转义引号——onclick
  // 属性上下文（'...'）存在注入面。补引号转义（纵深防御；当前 id 规则不可触发）
  return div.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function renderMd(text) {
  if (window.marked && window.DOMPurify) {
    try { return DOMPurify.sanitize(marked.parse(text || '')); } catch (e) {}
  }
  // 修复 S19：fail-closed —— purify 未加载/消毒抛异常时不再回退到未消毒的裸 marked
  //（模型输出是半不可信输入，XSS 在 pywebview 下等于拿到全部 js_api 本地能力），降级为纯文本转义。
  return '<p>' + escapeHtml(text || '') + '</p>';
}
const _rafPendingSet = new WeakSet();   // 修复 W28：按 el 记录待渲染（原全局单 flag，两个元素交替刷新时丢帧）
function scheduleRender(el, fn) {
  if (_rafPendingSet.has(el)) return;
  _rafPendingSet.add(el);
  requestAnimationFrame(() => { _rafPendingSet.delete(el); try { el.innerHTML = fn(); } catch (e) {} });
}
function enhanceCodeBlocks(container) {
  container.querySelectorAll('pre').forEach(pre => {
    const code = pre.querySelector('code');
    if (code && window.hljs && !code.dataset.hl) {
      try { hljs.highlightElement(code); } catch (e) {}
      code.dataset.hl = '1';
    }
    if (code && /language-[\w+-]/.test(code.className) && !pre.querySelector('.code-lang')) {
      const lang = (code.className.match(/language-([\w+-]+)/) || [])[1] || 'code';
      const tag = document.createElement('span');
      tag.className = 'code-lang'; tag.textContent = lang;
      pre.appendChild(tag);
    }
    if (pre.querySelector('.code-copy')) return;
    const btn = document.createElement('button');
    btn.className = 'code-copy'; btn.textContent = '复制';
    btn.onclick = (e) => {
      e.stopPropagation();
      const t = (pre.querySelector('code') || {}).innerText || pre.innerText;
      navigator.clipboard.writeText(t).then(() => {   // 修复 建议㉔（三轮）：补 .catch，剪贴板权限拒绝不再 unhandled rejection
        btn.textContent = '✓';
        setTimeout(() => btn.textContent = '复制', 1500);
      }).catch(() => { btn.textContent = '✗'; setTimeout(() => btn.textContent = '复制', 1500); });
    };
    pre.appendChild(btn);
  });
}
function viewImage(src) {
  // 修复 建议㉓（三轮）：单例 + Esc 关闭——原多开叠加无上限、只能点图关闭
  const prev = document.getElementById('__imgViewer');
  if (prev) prev.remove();
  const ov = document.createElement('div');
  ov.id = '__imgViewer';
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:9999;display:flex;align-items:center;justify-content:center;cursor:zoom-out;';
  const img = document.createElement('img');
  img.src = src; img.style.cssText = 'max-width:92%;max-height:92%;border-radius:10px;';
  ov.appendChild(img);
  const close = () => { ov.remove(); document.removeEventListener('keydown', onKey); };
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  ov.onclick = close;
  document.addEventListener('keydown', onKey);
  document.body.appendChild(ov);
}
function addMessage(role, content, extra) {
  const container = document.getElementById('chatContainer');
  const empty = document.getElementById('emptyState');
  if (empty) empty.remove();
  const div = document.createElement('div');
  div.className = 'message ' + role;
  let extraHtml = '';
  if (extra && extra.images)
    // 修复 建议㉜（二轮）：images URL 未转义直拼 innerHTML（上轮点名漏修，
    // 当时仅因 dataURL 巧合无引号而侥幸安全）
    extraHtml = '<div class="msg-images">' + extra.images.map(u => `<img src="${escapeHtml(String(u))}" onclick="viewImage(this.src)">`).join('') + '</div>';
  if (extra && extra.files)
    extraHtml += extra.files.map(f => `<div class="msg-file">📎 ${escapeHtml(f)}</div>`).join('');
  if (extra && extra.usage) {
    const u = extra.usage;
    // 修复 S9（二轮）：usage 三字段来自 API 响应（自定义端点=不可信输入），
    // 未转义直拼 innerHTML 可被恶意端点注入（pywebview 下 XSS = 全部 js_api 本地能力）
    extraHtml += `<div class="usage-info"><span>输入 <b>${escapeHtml(String(u.prompt_tokens ?? ''))}</b></span>` +
      `<span>输出 <b>${escapeHtml(String(u.completion_tokens ?? ''))}</b></span><span>合计 <b>${escapeHtml(String(u.total_tokens ?? ''))}</b></span></div>`;
  }
  const body = (role === 'assistant' && typeof content === 'string') ? renderMd(content) : escapeHtml(content || '');
  div.innerHTML = `
    <div class="avatar">${role === 'user' ? '我' : 'AI'}</div>
    <div class="content ${role === 'error' ? 'error' : ''}">${body}${extraHtml}</div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  // v4 配色重设计（用户反馈「气泡颜色太深」）：错误气泡前缀红字加粗、正文中性色——
  // 语义色收窄到标题（完整规则见模板 .message .content.error：中性卡+红色左边条）
  if (role === 'error') fillErrorBubble(div.querySelector('.content'), content);
  return div.querySelector('.content');
}
/* v4 配色重设计：错误气泡文本装配——「请求失败:」前缀红字（b.err-title），
   正文中性色；textContent 组装不碰 innerHTML（端点错误文本=不可信输入，防注入）。 */
function fillErrorBubble(el, text) {
  if (!el) return;
  const txt = String(text == null ? '' : text);
  const m = /^([^:：]{0,12}[:：])\s*/.exec(txt);
  el.textContent = '';
  if (m) {
    const t = document.createElement('b');
    t.className = 'err-title';
    t.textContent = m[1] + ' ';
    el.appendChild(t);
    el.appendChild(document.createTextNode(txt.slice(m[0].length)));
  } else {
    el.textContent = txt;
  }
}
/* v4：触屏/无悬停设备——点消息唤出操作条（.acting），点其他消息或空白处收起 */
document.addEventListener('click', (e) => {
  const msg = (e.target && e.target.closest) ? e.target.closest('.message') : null;
  document.querySelectorAll('.message.acting').forEach(m => { if (m !== msg) m.classList.remove('acting'); });
  if (msg && !(e.target.closest && e.target.closest('.msg-actions'))) msg.classList.add('acting');
});
function addMsgActions(contentEl, text, onlyCopy) {
  if (!contentEl || !text) return;
  const bar = document.createElement('div');
  bar.className = 'msg-actions';   // v4：悬停弹出条（CSS 控制显隐）
  const mk = (label, fn) => {
    const b = document.createElement('button');
    b.className = 'copy-btn'; b.textContent = label;
    b.onclick = () => fn(b);
    bar.appendChild(b); return b;
  };
  mk('⧉ 复制', (b) => {
    // 修复 ㉔（三轮）：补 .catch——剪贴板不可用（非安全上下文/权限拒绝）时不再
    // unhandled rejection（50:45 同型已修，此处为消息操作条路径）
    navigator.clipboard.writeText(text).then(() => { b.textContent = '✓ 已复制'; setTimeout(() => b.textContent = '⧉ 复制', 1500); }).catch(() => { b.textContent = '复制失败'; });
  });
  if (!onlyCopy) {
    mk('↩ 追问', () => { document.getElementById('userInput').focus(); });
    mk('☆ 收藏', async (b) => {
      try {
        await callApi('append_memory', [JSON.stringify({ text: text.slice(0, 500) })]);
        b.textContent = '✓ 已收藏'; setTimeout(() => b.textContent = '☆ 收藏', 1500);
      } catch (e) { b.textContent = '✗ 失败'; }
    });
  }
  contentEl.appendChild(bar);
}
