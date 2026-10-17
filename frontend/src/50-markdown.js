/* ================= Markdown 渲染（高亮 + 节流） ================= */
if (window.DOMPurify) {
  DOMPurify.addHook('afterSanitizeAttributes', (n) => {
    if (n.tagName === 'A') { n.setAttribute('target', '_blank'); n.setAttribute('rel', 'noopener'); }
  });
}
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
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
      navigator.clipboard.writeText(t).then(() => {
        btn.textContent = '✓';
        setTimeout(() => btn.textContent = '复制', 1500);
      });
    };
    pre.appendChild(btn);
  });
}
function viewImage(src) {
  const ov = document.createElement('div');
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:9999;display:flex;align-items:center;justify-content:center;cursor:zoom-out;';
  const img = document.createElement('img');
  img.src = src; img.style.cssText = 'max-width:92%;max-height:92%;border-radius:10px;';
  ov.appendChild(img); ov.onclick = () => ov.remove();
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
  return div.querySelector('.content');
}
function addMsgActions(contentEl, text, onlyCopy) {
  if (!contentEl || !text) return;
  const bar = document.createElement('div');
  bar.style.cssText = 'margin-top:8px;display:flex;gap:6px;';
  const mk = (label, fn) => {
    const b = document.createElement('button');
    b.className = 'copy-btn'; b.textContent = label;
    b.onclick = () => fn(b);
    bar.appendChild(b); return b;
  };
  mk('⧉ 复制', (b) => {
    navigator.clipboard.writeText(text).then(() => { b.textContent = '✓ 已复制'; setTimeout(() => b.textContent = '⧉ 复制', 1500); });
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
