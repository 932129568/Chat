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
  /* ================= v1.8.0 M3：/plan 计划模式入口 =================
   * /plan <任务> → 生成计划（LLM JSON / 模板兜底）→ 计划卡待批准 →
   * 批准 → 建检查点 → 以任务文本走原 Agent 循环（todo 由 60-agent-loop 推进）。 */
  if (text.indexOf('/plan') === 0) {
    input.value = ''; attachments = []; renderPreview();
    const task = text.slice(5).trim() || (text ? '' : '');
    if (!task) {
      isStreaming = false;
      addMessage('assistant', '用法：/plan <任务描述>\n例：/plan 查一下 Qwen3 发布信息并整理成笔记保存到工作区');
      return;
    }
    isStreaming = false;   // 计划阶段不占流式；批准后由内层发送逻辑重新置位
    await planModeRun(task);
    return;
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
  if (typeof navUpdateEmptyGuide === 'function') navUpdateEmptyGuide();   // 修复（四轮）：首条消息发出后空态引导立即消失
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
/* 一次性绑定标记挂函数属性（勿用模块级 let——vm harness 抽函数体会丢外层声明） */
function toggleSettings() {
  const panel = document.getElementById('settingsPanel');
  if (!panel) return;
  if (!toggleSettings._bound) {
    toggleSettings._bound = true;
    // 点遮罩（窗口外空白）关闭；Esc 关闭（v4 设置窗口化交互补全）。
    // typeof 守卫：vm 沙箱的 panel/document 桩可能无 addEventListener（test_v13_qa）
    if (panel.addEventListener) {
      panel.addEventListener('click', (e) => { if (e.target === panel) toggleSettings(); });
    }
    if (typeof document !== 'undefined' && document.addEventListener) {
      document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        if (!panel.classList.contains('show')) return;
        const tag = (e.target && e.target.tagName) || '';
        if (tag === 'TEXTAREA' || tag === 'INPUT') return;   // 输入中不误关
        toggleSettings();
      });
    }
  }
  if (panel.classList.contains('show')) {
    // v4：关=播退场（v4SetWinOut 140ms in-soft）再撤 .show——不再生硬瞬消
    if (panel.classList.contains('hiding')) return;   // 防重入
    panel.classList.add('hiding');
    const done = () => { try { panel.classList.remove('show', 'hiding'); } catch (e) {} };
    if (typeof MOTION !== 'undefined' && !MOTION.instant()) {
      MOTION.onAnimEnd(panel, 'animationend', MOTION.compOut()).then(done);
    } else { done(); }
    return;
  }
  panel.classList.add('show');
  // 打开设置面板时顺带刷新 MCP 服务器列表（纯本地读取，零网络；失败已在 loadMcpServers 内 toast）
  try { loadMcpServers(); } catch (e) {}
  // 修复 UX-4（v1.4）：设置浮层打开时构建锚点导航（DOM 已就绪；每次打开重建保持幂等）
  try { buildSetNav(); } catch (e) {}
}
function toggleSidebar() { document.getElementById('sidebar').classList.toggle('collapsed'); }


/* ================= v1.8.0 M3：计划模式主流程 =================
 * 计划生成策略（ux-flows 流程 8）：LLM 输出 JSON 计划为主，解析失败/
 * 桥不可用回落模板计划（按句读/分号/换行拆分，3-7 步）——任何情况下
 * 都不阻断「先看计划再执行」的核心体验。 */
let _planGenSeq = 0;
async function planModeRun(task) {
  addMessage('user', '/plan ' + task);
  const plan = await planGenerate(task);
  if (!plan || !plan.steps || !plan.steps.length) {
    addMessage('assistant', '计划生成失败，请直接发送任务描述让 Agent 执行。');
    return;
  }
  let created = null;
  try {
    const raw = await pcCall('plan_create', [plan.title, plan.steps], 20000);
    created = JSON.parse(raw || '{}');
  } catch (e) { created = null; }
  const full = (created && created.ok && created.plan) ? created.plan
    : { task_id: 'local_' + Date.now(), title: plan.title, steps: plan.steps, status: 'planning' };
  if (plan.files && plan.files.length) full.files = plan.files;
  try {
    await planShow(full);   // 等用户批准；拒绝 → AbortError
  } catch (e) {
    return;   // 已拒绝（toast 已提示）
  }
  // 批准：task_id 落库到当前会话（85-session-mgmt 真删 session_purge 的 taskIds 数据源；
  // 只挂 task_id，不挂整个 plan 对象；65-session-store 白名单同步放行）
  {
    const _s = getCurrentSession();
    if (_s) { _s.plan = { task_id: full.task_id }; saveSessions(); }
  }
  // 批准：建检查点（git 锚点 + 计划涉及文件快照；空 files 时 git HEAD 仍记录）
  try {
    let ws = '';
    try {
      const eff = JSON.parse(await callApi('get_effective_ws', []) || '{}');
      ws = (eff && eff.ws) || '';
    } catch (e) {}
    const raw = await pcCall('checkpoint_create', [full.task_id, full.files || [], ws], 60000);
    const r = JSON.parse(raw || '{}');
    if (r && r.ok) ckptShow(full.task_id, r);
    else if (r && r.error) pcToast('检查点创建失败：' + r.error + '（任务继续，但无法回滚）', 'warn');
  } catch (e) {
    pcToast('检查点创建失败（任务继续，但无法回滚）', 'warn');
  }
  // 以任务文本走原发送链（isStreaming 由 sendMessage 内部管理）
  const input = document.getElementById('userInput');
  if (input) input.value = task;
  sendMessage();
}

/** 生成计划：LLM JSON 优先，模板兜底。steps: [{text, risk}]。 */
async function planGenerate(task) {
  const seq = ++_planGenSeq;
  const sysPrompt = '你是任务规划器。把用户任务拆成 3-7 个可执行步骤，只输出 JSON：' +
    '{"title":"计划标题","steps":[{"text":"步骤描述","risk":"l2|l0|"}],"files":["涉及的相对路径"]}。' +
    'risk 标注：会写文件/执行命令的步骤标 l2（授权内），删除/越界/提权标 l0（需确认），只读不标。' +
    '只输出 JSON，不要解释。';
  // HF-1 约定：所有 messages 构造点必须过 normalizeSystemMessages（防多 system
  // 被 Qwen/Ollama Jinja 模板拒；fetchGLMStream 内部虽也归一，构造点显式过是铁律）
  const planMsgs = normalizeSystemMessages([
    { role: 'system', content: sysPrompt },
    { role: 'user', content: task }
  ]);
  try {
    const resp = await fetchGLMStream({
      apiKey: (typeof effectiveApiKey === 'function') ? effectiveApiKey() : '',
      body: {
        model: (typeof connectModelValue === 'function' && connectModelValue()) || 'glm-5.3-flash',
        messages: planMsgs,
        temperature: 0.3, max_tokens: 800, stream: false
      }
    }, undefined);
    if (resp && resp.ok) {
      const txt = await resp.text();
      const m = txt.match(/\{[\s\S]*\}/);
      if (m) {
        const d = JSON.parse(m[0]);
        if (d && Array.isArray(d.steps) && d.steps.length) {
          if (seq !== _planGenSeq) return null;
          return { title: d.title || task.slice(0, 40), steps: d.steps.map(x => ({
            text: String(x.text || x.step || '').slice(0, 200),
            risk: String(x.risk || '').slice(0, 4)
          })), files: Array.isArray(d.files) ? d.files.slice(0, 20) : [] };
        }
      }
    }
  } catch (e) { /* 回落模板 */ }
  if (seq !== _planGenSeq) return null;
  return planGenerateFallback(task);
}

/** 模板兜底计划：按句读/分号/换行拆 3-7 步（本地零依赖，断网可用）。 */
function planGenerateFallback(task) {
  const parts = String(task || '')
    .split(/[。；;\n]+|\s+然后\s+|\s+接着\s+|\s+再\s+/)
    .map(x => x.trim()).filter(x => x.length >= 2);
  const steps = (parts.length >= 2 ? parts.slice(0, 7) : [
    '理解任务：' + task.slice(0, 60),
    '执行核心操作',
    '验证结果并汇报'
  ]).map(t => ({ text: t.slice(0, 200), risk: /删|除|reset|push|force|提权|admin/i.test(t) ? 'l0'
    : (/写|保存|提交|commit|生成|创建|修改/i.test(t) ? 'l2' : '') }));
  return { title: '任务计划 · ' + task.slice(0, 30), steps: steps, files: [] };
}
