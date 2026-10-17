/* ================= 发送 ================= */
async function sendMessage() {
  if (isStreaming) return;
  const input = document.getElementById('userInput');
  const text = input.value.trim();
  if (!text && attachments.length === 0) return;
  const apiKey = effectiveApiKey();
  if (!apiKey && !localModeActive()) {   // 修复：本地模式无需 API Key（原误报）
    addMessage('error', '请先在「设置」中填入 API Key');
    document.getElementById('settingsPanel').classList.add('show');
    return;
  }
  // 修复 S20：入口同步置位 isStreaming——runAgentLoop 原先在两个 await 之后才置位，
  // Enter 长按连发/快速双击可在置位前过守卫，起双并发 Agent 循环（消息交错/计费翻倍）。
  // 以下所有提前 return 的路径都必须复位。
  isStreaming = true;
  try {
  ensureSession();
  const s = getCurrentSession();
  if (s.messages.length <= 1 && !s.worklogInjected) {
    try {
      const wl = await callApi('get_worklog', []);
      if (wl && wl.trim().length > 0) {
        s.worklogInjected = true;
        s.messages.push({ role: 'system', content:
          '【工作日志】\n' + wl + '\n（来自 _glm_worklog.md，供延续上下文）' });
      }
    } catch (e) {}
  }
  try {
    if (sumSessionTokens(s) > 200000 && s.messages.length >= 6) {
      await compactNow(s, apiKey, { force: true, quiet: true });
    }
  } catch (e) {}
  if (text === '/compact') {
    input.value = ''; attachments = []; renderPreview();
    if (s.messages.length && String(s.messages[0]?.content || '').includes('【历史纪要】')) {
      isStreaming = false;   // 修复 S20：提前 return 路径复位
      addMessage('assistant', '刚刚已做过压缩，历史已是纪要态，无需重复。'); return;
    }
    isStreaming = false;     // 修复 S20：/compact 不进入生成循环，复位后走压缩
    await compactNow(s, apiKey); return;
  }
  const images = attachments.filter(a => a.type === 'image');
  const videos = attachments.filter(a => a.type === 'video');
  const textFiles = attachments.filter(a => a.type === 'text');
  const mem = recallMemory(text);
  const memBlock = mem ? '\n\n[相关历史记忆]\n' + mem + '\n（背景参考，无关可忽略）' : '';
  let userContent;
  if (images.length === 0 && videos.length === 0 && textFiles.length === 0) {
    userContent = (text + memBlock) || '请回复';
  } else {
    const parts = [];
    let fullText = (text ? text + memBlock : '');
    if (textFiles.length > 0) {
      const ATT_FULL = 200000;   // ≤20万字符直接全文注入
      const results = await Promise.all(textFiles.map(async f => {
        let p = '';
        try { p = await callApi('save_workspace_file', [f.name, f.text]); } catch (e) {}
        if (f.text.length <= ATT_FULL) {
          return `\n----- 附件: ${f.name} | 全文 ${f.text.length} 字已完整注入 | 原文件路径: ${p} -----\n修改此文件用 search_replace 打补丁到上述路径, 禁止另存副本。\n${f.text}`;
        }
        return `\n----- 附件: ${f.name} | 全文 ${f.text.length} 字超预算, 已存工作区 | 路径: ${p} -----\n预览前500字:\n${f.text.slice(0,500)}…\n需要原文用 read_file(路径, force=true) 分段读`;
      }));
      fullText = (fullText ? fullText + '\n' : '') + results.join('\n');
    }
    parts.push({ type: 'text', text: fullText || '请分析以上内容' });
    images.forEach(img => parts.push({ type: 'image_url', image_url: { url: img.dataUrl } }));
    videos.forEach(v => parts.push({ type: 'video_url', video_url: { url: v.dataUrl } }));
    userContent = parts;
  }
  const displayText = text + (textFiles.length > 0 ? `\n（附带 ${textFiles.length} 个文本文件）` : '');
  const displayExtra = {};
  if (images.length > 0) displayExtra.images = images.map(i => i.dataUrl);
  if (textFiles.length > 0) displayExtra.files = textFiles.map(f => f.name);
  const uEl = addMessage('user', displayText || '（发送附件）', displayExtra);
  if (text) addMsgActions(uEl, text, true);
  s.messages.push({ role: 'user', content: userContent });
  // 修复 UX-1/UX-3（v1.4）：live 消息也 stamp 下标（瘦身标记/搜索跳转用）。
  // dataset 防御：非 DOM 元素（测试桩/降级路径）时静默跳过，不抛错中断发送
  if (uEl && uEl.dataset) uEl.dataset.midx = s.messages.length - 1;
  updateSessionTitle(text || (textFiles[0]?.name || '附件'));
  s.updatedAt = Date.now();
  saveSessions();
  renderSessionList();
  input.value = '';
  input.style.height = 'auto';
  attachments = [];
  renderPreview();
  runAgentLoop(s, apiKey);
  } catch (e) {
    isStreaming = false;   // 修复 S20：附件读取等未预期的异常不再把应用卡在「生成中」
    toast('发送失败: ' + (e && e.message ? e.message : e), 'err');
  }
}
async function continueLastGeneration(s, apiKey) {
  if (isStreaming) return;
  runAgentLoop(s, apiKey);
}
async function regenerate() {
  const s = getCurrentSession();
  if (!s || isStreaming) return;
  let lastAssistant = -1;
  for (let i = s.messages.length - 1; i >= 0; i--) {
    if (s.messages[i].role === 'assistant') { lastAssistant = i; break; }
  }
  if (lastAssistant >= 0) s.messages.splice(lastAssistant);
  // 修复 ㉘：重建全部历史消息（原只回放 user，历史 assistant 回复与工具摘要从界面消失）
  renderChatHistory(s);
  const apiKey = effectiveApiKey();
  if (!apiKey && !localModeActive()) {   // 修复：本地模式无需 API Key（原误报）
    addMessage('error', '请先在「设置」中填入 API Key');
    document.getElementById('settingsPanel').classList.add('show');
    return;
  }
  runAgentLoop(s, apiKey);
}
function exportChat() {
  const s = getCurrentSession();
  if (!s || s.messages.length === 0) { toast('当前没有对话可导出', 'warn'); return; }
  let md = `# ${s.title || '对话'}\n\n`;
  s.messages.forEach(m => {
    if (m.role === 'user') {
      let text = typeof m.content === 'string' ? m.content
        : (Array.isArray(m.content) ? m.content.map(p => p.text || '').join(' ') : '');
      md += `## 我\n\n${text}\n\n`;
    } else if (m.role === 'assistant' && typeof m.content === 'string' && m.content) {
      md += `## GLM\n\n${m.content}\n\n`;
    }
  });
  const blob = new Blob([md], { type: 'text/markdown' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = (s.title || 'chat').replace(/[\\/:*?\"<>|]/g, '_').slice(0, 40) + '.md';
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
function toggleSettings() {
  const panel = document.getElementById('settingsPanel');
  panel.classList.toggle('show');
  // 打开设置面板时顺带刷新 MCP 服务器列表（纯本地读取，零网络；失败已在 loadMcpServers 内 toast）
  try { loadMcpServers(); } catch (e) {}
  // 修复 UX-4（v1.4）：设置浮层打开时构建锚点导航（DOM 已就绪；每次打开重建保持幂等）
  try { if (panel.classList.contains('show')) buildSetNav(); } catch (e) {}
}
function toggleSidebar() { document.getElementById('sidebar').classList.toggle('collapsed'); }
