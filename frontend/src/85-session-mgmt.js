/* ================= 会话管理 ================= */
async function continueInNewSession() {
  const s = getCurrentSession();
  const btn = document.getElementById('continueNewBtn');
  if (!s || !s.messages.length) { newSession(); return; }
  const apiKey = effectiveApiKey();
  if (!apiKey) { toast('请先设置 API Key', 'warn'); document.getElementById('settingsPanel').classList.add('show'); return; }
  if (btn) btn.textContent = '⏳ 总结中…';
  // 实现 v1.6 W28：生成中 compactNow 会静默跳过压缩（isStreaming 早退），原流程
  // 仍继续 newSession() → 用户在新会话丢失全部上下文且无感知。生成中直接中止并明示。
  if (isStreaming) {
    toast('AI 正在生成中，稍后再「新对话继续」（避免未压缩就开新会话丢失上下文）', 'warn');
    if (btn) btn.textContent = '⇥ 新对话继续';
    return;
  }
  try { await compactNow(s, apiKey, { quiet: false }); }
  catch (e) {
    // 修复 W25（二轮）：压缩失败不再静默吞——否则用户在新会话丢失全部上下文且无察觉
    toast('历史压缩失败，已中止开新会话（当前对话未受影响）：' + (e && e.message || e), 'err');
    if (btn) btn.textContent = '⇥ 新对话继续';
    return;
  }
  newSession();
  if (btn) btn.textContent = '⇥ 新对话继续';
  document.getElementById('userInput').focus();
}
function newSession() {
  if (isStreaming && abortController) { abortController.abort(); }
  currentSessionId = null;
  window.__hitRate = 0;
  window.__turnTokens = 0;
  attachments = [];
  guardTrusted.clear();               // v1.2 R2：会话级信任随会话结束失效
  mcpTrusted.clear();                 // 修复 W26：MCP 会话信任同步清空（文案「本会话内不再提示」原本被当成进程级永久信任）
  renderPreview();
  document.getElementById('chatContainer').innerHTML =
    `<div class="empty-state" id="emptyState">
      <div class="empty-icon">✦</div>
      <h2>开始和 GLM 聊天</h2>
      <p>支持文字、图片、视频、文本文件 · 历史记录自动保存</p>
    </div>`;
  renderSessionList();
  updateLiveTokenStat();
  lastShotHash = null; pendingShots = []; shotState = 'idle';
  try { callApi('clear_caches', []).catch(() => {}); } catch (e) {}   // 修复 ㊲：补 rejection 处理（原只挡同步 throw）
  try { callApi('set_current_sid', [null]).catch(() => {}); } catch (e) {}   // 修复 ㊲：同上；后端借此清空会话信任态（含 MCP）
  refreshWsCard();
}
function switchSession(id, silent) {
  if (isStreaming) {
    // 修复 ㉑（三轮）：流式中静默 return——用户点了没反应，以为卡死。补 toast 反馈
    if (typeof toast === 'function') toast('正在生成回复，请先暂停或等待完成', 'warn');
    return;
  }
  const target = sessions.find(s => s.id === id);   // 修复 ㊳：先校验存在性再赋值（原先赋值，非法 id 时 currentSessionId 悬空）
  if (!target) return;
  currentSessionId = id;
  window.__hitRate = 0;
  window.__turnTokens = 0;
  attachments = [];
  guardTrusted.clear();               // v1.2 R2：会话级信任随会话切换失效
  mcpTrusted.clear();                 // 修复 W26：与文案「本会话内不再提示」对齐，切会话即失效
  renderPreview();
  // v4：切会话容器级过渡——先 .swapping 淡出（140ms in-soft），重建历史后再淡入（200ms out-soft）；
  // boot 首次（silent）与 fx-off/reduced-motion 降级直接重建，避免开屏空容器闪一下
  const box = document.getElementById('chatContainer');
  if (silent || (typeof MOTION !== 'undefined' && MOTION.instant())) {
    renderChatHistory(target);
  } else {
    box.classList.add('swapping');
    // 修复 S14（三轮）：原 .swapping 移除与渲染同回调无 finally——渲染抛错
    // （持久化数据含畸形消息）即 opacity:0 永久锁死聊天区，只能重启
    MOTION.onAnimEnd(box, 'transitionend', MOTION.compOut()).then(() => {
      try {
        renderChatHistory(target);
      } finally {
        void box.offsetWidth; box.classList.remove('swapping');
      }
    }).catch(() => { box.classList.remove('swapping'); });
  }
  renderSessionList();
  updateLiveTokenStat();
  lastShotHash = null; pendingShots = []; shotState = 'idle';
  try { callApi('clear_caches', []).catch(() => {}); } catch (e) {}   // 修复 ㊲
  try { callApi('set_current_sid', [currentSessionId]).catch(() => {}); } catch (e) {}   // 修复 ㊲：后端据此清空会话信任态（含 MCP）
  refreshWsCard();
}
/** 修复 ㉘：抽出的历史回放渲染（switchSession / regenerate 共用——原 regenerate 只回放 user，历史 assistant 消失） */
function renderChatHistory(s) {
  const box = document.getElementById('chatContainer');
  // v4：重建期间挂 .batch——禁消息逐条重播入场动画（否则长历史瞬间刷屏）
  box.classList.add('batch');
  box.innerHTML = '';
  let pendingTools = [];
  const flushTools = () => {
    if (!pendingTools.length) return;
    const div = document.createElement('div');
    div.className = 'tool-call-item done';
    div.style.margin = '4px 0 10px 43px';
    div.innerHTML = '<span class="tc-dot"></span><span>' + escapeHtml('本次操作 · ' + pendingTools.join(' · ')) + '</span>';
    box.appendChild(div);
    pendingTools = [];
  };
  (s.messages || []).forEach((m, i) => {
    if (m.role === 'user') {
      flushTools();
      let text = '';
      if (typeof m.content === 'string') text = m.content;
      else if (Array.isArray(m.content)) {
        m.content.forEach(p => {
          if (p.type === 'text') text += p.text;
          else if (p.type === 'image_url') text += '\n[图片]';
          else if (p.type === 'video_url') text += '\n[视频]';
        });
      }
      const uEl = addMessage('user', text, {});
      if (uEl && uEl.dataset) uEl.dataset.midx = i;   // 修复 UX-3（v1.4）：消息元素 stamp 源消息下标，供会话搜索跳转定位（dataset 防御）
      if (text.trim()) addMsgActions(uEl, text.trim(), true);
    } else if (m.role === 'assistant') {
      let text = typeof m.content === 'string' ? m.content : '';
      const toolCalls = m.tool_calls && m.tool_calls.length ? m.tool_calls : null;
      if (toolCalls) {
        toolCalls.forEach(tc => {
          let args = {}; try { args = JSON.parse(tc.function?.arguments || '{}'); } catch (e) {}
          const nm = tc.function?.name || '';
          if (nm === 'read_file') pendingTools.push('读 ' + (args.path || ''));
          else if (nm === 'list_dir') pendingTools.push('列 ' + (args.path || ''));
          else if (nm === 'write_file') pendingTools.push('写 ' + (args.path || ''));
          else if (nm === 'append_file') pendingTools.push('追加 ' + (args.path || ''));
          else if (nm === 'search_replace') pendingTools.push('改 ' + (args.path || ''));
          else if (nm === 'run_command') pendingTools.push('执行 ' + String(args.cmd || '').slice(0, 30));
          else if (nm === 'run_powershell') pendingTools.push('执行 ' + String(args.cmd || '').slice(0, 30));
          else if (nm === 'take_screenshot') pendingTools.push('截图');
          else pendingTools.push(nm);
        });
      }
      if (text.trim()) {
        flushTools();
        const extra = m.usage ? { usage: m.usage } : {};
        const contentEl = addMessage('assistant', text, extra);
        if (contentEl && contentEl.dataset) contentEl.dataset.midx = i;   // 修复 UX-3（v1.4）：stamp 源消息下标，供会话搜索跳转定位（dataset 防御）
        addMsgActions(contentEl, text);
        enhanceCodeBlocks(contentEl);
        if (m.__compactCard || m.__archiveCard) renderCompactCard(box, s, m);   // 修复 UX-1（v1.4）：压缩/归档卡片（token 对比+恢复原文）
      }
    }
  });
  flushTools();
  // v4：两帧后摘 .batch——重建完成，此后新消息恢复正常入场动画
  requestAnimationFrame(() => requestAnimationFrame(() => box.classList.remove('batch')));
}
/** 修复 F1（v1.4）：会话导出为 Markdown——前端序列化（零后端/零新 js_api/零依赖）。
 *  消息角色标题 + 工具调用块 + 时间戳 + 可选 token 统计页脚；Blob 下载。
 *  边界：空会话正常生成（仅标题+说明）；超长消息截断防爆；文件名净化非法字符。 */
function exportSessionMd(id, e) {
  if (e) e.stopPropagation();
  const s = sessions.find(x => x.id === id);
  if (!s) { toast('会话不存在', 'warn'); return; }
  const lines = [];
  lines.push('# ' + (s.title || 'Harbor 会话'));
  lines.push('');
  // 修复 建议㊷（三轮）：APP_VERSION 前端永无定义（原恒显旧版 '1.4'）——兜底取全局
  // window.__appVersion（后端可注入），再无则省略版本号，不显示错误版本
  const _ver = (typeof APP_VERSION !== 'undefined' && APP_VERSION)
    ? APP_VERSION : (window.__appVersion || '');
  lines.push('> 导出自 Harbor' + (_ver ? ' v' + _ver : '') +
    ' · ' + new Date().toLocaleString('zh-CN'));
  lines.push('');
  let toolCount = 0, usage = null;
  for (const m of (s.messages || [])) {
    if (m.role === 'user') {
      let text = typeof m.content === 'string' ? m.content : '';
      if (Array.isArray(m.content)) {
        text = m.content.map(p => p.text || (p.type === 'image_url' ? '[图片]' : p.type === 'video_url' ? '[视频]' : '')).join(' ');
      }
      lines.push('## 🧑 我', '', String(text).slice(0, 20000), '');
    } else if (m.role === 'assistant') {
      if (m.tool_calls && m.tool_calls.length) {
        for (const tc of m.tool_calls) {
          toolCount++;
          let args = {};
          try { args = JSON.parse(tc.function?.arguments || '{}'); } catch (e) {}
          lines.push('#### 🔧 工具调用 · `' + (tc.function?.name || '') + '`');
          lines.push('```json');
          lines.push(JSON.stringify(args, null, 2).slice(0, 4000));
          lines.push('```', '');
        }
      }
      if (m.content && String(m.content).trim()) {
        lines.push('## 🤖 AI', '', String(m.content).slice(0, 20000), '');
      }
      if (m.usage) usage = m.usage;   // 最后一次 usage = 会话累计口径（calcUsage 同源）
    } else if (m.role === 'tool') {
      lines.push('<details><summary>📄 工具结果</summary>', '', '```', String(m.content || '').slice(0, 8000), '```', '', '</details>', '');
    }
  }
  if (usage) {
    lines.push('---', '', '**Token 统计**：输入 ' + (usage.prompt_tokens || 0) +
      ' · 输出 ' + (usage.completion_tokens || 0) +
      ' · 合计 ' + (usage.total_tokens || 0) +
      (usage.prompt_tokens_details?.cached_tokens ? ' · 缓存命中 ' + usage.prompt_tokens_details.cached_tokens : '') +
      ' · 工具调用 ' + toolCount + ' 次', '');
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = (s.title || 'chat').replace(/[\\/:*?"<>|]/g, '_').slice(0, 40) +
    '-' + new Date().toISOString().slice(0, 10) + '.md';
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  toast('已导出 Markdown', 'ok');
}

async function deleteSession(id, e) {
  e.stopPropagation();
  if (isStreaming && id === currentSessionId) { toast('正在生成回复，请先停止', 'warn'); return; }
  const r = await uiConfirm({ title: '删除对话', body: '确定删除这条对话？该操作不可恢复。', danger: true, okText: '删除' });
  if (!r.ok) return;
  sessions = sessions.filter(s => s.id !== id);
  rememberDeletedSession(id);   // 修复 W24（二轮）：删除墓碑（防后端写失败后合并复活）
  saveSessions();
  callApi('delete_session_ws', [id]).catch(() => {});
  if (currentSessionId === id) newSession();
  else renderSessionList();
}
/** 修复 建议㉝（二轮）：会话 id 拼 onclick 前统一转义（模块作用域，UX-3 搜索跳转同样复用）。 */
// 修复 建议㉝（二轮）：会话 id 拼 onclick 前统一转义（模块作用域，UX-3 搜索跳转同样复用）。
// 修复 51（三轮）：补双引号转义——escapeHtml 走 textContent→innerHTML 不转引号，
// 属性上下文（onclick="..."）里双引号同样有注入面（与单引号一并纵深防御）
const _escId = (id) => escapeHtml(String(id)).replace(/'/g, '&#39;').replace(/"/g, '&quot;');
function renderSessionList() {
  const box = document.getElementById('sessionList');
  if (sessions.length === 0) {
    box.innerHTML = '<div class="sidebar-empty">暂无历史对话</div>';
    updateTokenStat();
    return;
  }
  const sorted = [...sessions].sort((a, b) => b.updatedAt - a.updatedAt);
  // v4 深化（2026-10-21）：日期分组（今天/昨天/更早）——长列表的时间锚点
  let lastGroup = '';
  const html = sorted.map(s => {
    const g = _dayGroup(s.updatedAt);
    const head = (g !== lastGroup) ? '<div class="session-group">' + g + '</div>' : '';
    lastGroup = g;
    return head +
    `<div class="session-item ${s.id === currentSessionId ? 'active' : ''}" onclick="switchSession('${_escId(s.id)}')">
      <div class="session-title">${escapeHtml(s.title || '新对话')}</div>
      <div class="session-time">${formatTime(s.updatedAt)}</div>
      <span class="session-acts">
        <button class="session-exp" title="导出为 Markdown" onclick="exportSessionMd('${_escId(s.id)}', event)">⤓</button>
        <button class="session-del" onclick="deleteSession('${_escId(s.id)}', event)">✕</button>
      </span>
    </div>`;
  }).join('');
  box.innerHTML = html;
  updateTokenStat();
}
/** 日期分组键：今天/昨天/更早（跨天边界用自然日比对，非 24h 减法）。 */
function _dayGroup(ts) {
  const t = Number(ts);
  if (!ts || !isFinite(t)) return '更早';
  const d = new Date(t), now = new Date();
  const sameDay = (a, b) => a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  if (sameDay(d, now)) return '今天';
  const y = new Date(Date.now() - 86400000);
  if (sameDay(d, y)) return '昨天';
  return '更早';
}
function formatTime(ts) {
  // 修复 建议㉲（三轮）：undefined/非时间戳不再显示 Invalid Date/NaN
  const t = Number(ts);
  if (!ts || !isFinite(t)) return '';
  const d = new Date(t), now = new Date();
  if (d.toDateString() === now.toDateString())
    return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0');
  return (d.getMonth() + 1) + '/' + d.getDate();
}
function ensureSession() {
  if (!currentSessionId) {
    currentSessionId = 's_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
    sessions.push({ id: currentSessionId, title: '', createdAt: Date.now(), updatedAt: Date.now(), messages: [] });
  }
}
function updateSessionTitle(text) {
  const s = getCurrentSession();
  if (!s || s.title) return;
  s.title = text.replace(/\s+/g, ' ').slice(0, 20) || '新对话';
}
