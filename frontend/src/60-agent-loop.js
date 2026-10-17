/* ================= Agent 主循环 ================= */

async function runAgentLoop(s, apiKey) {
  isStreaming = true;   // 修复 S20：同步置位移到最前（原在两个 await 之后，快速双发可起双循环）
  let aiContent = null;   // 修复 ㉗：前置代码移入 try，catch 需要访问 → 提升声明
  let partialContent = '';   // 修复 W21（二轮）：流中部分正文的函数级镜像——abort 时固化入历史（UI 与持久化不分叉）
  let _localWaitTimer = null;   // 修复 B3（v1.5）：本地首字节等待态计时器（函数级声明，异常路径也要清理）
  try {   // 修复 ㉗：原前 27 行在 try 外，任一 throw 变 unhandled rejection 且 isStreaming 卡死
    try { await callApi('set_current_sid', [currentSessionId]); } catch (e) {}
    try { await maybeAutoCompact(s); } catch (e) { console.warn(e); }  // 修复 ㊸：传会话对象（原传合成 {messages}）；压缩失败不中断主流程
    abortController = new AbortController();
    resetCostDefense();   // v1.2 R4：每次任务重置循环/无进展计数
    const sendBtn = document.getElementById('sendBtn');
    sendBtn.textContent = '■';
    sendBtn.style.background = '#ff4d4f';
    sendBtn.onclick = () => abortController.abort();
    document.getElementById('streamBar').classList.add('on');
    aiContent = addMessage('assistant', '');
    aiContent.innerHTML = '<div class="md-body"><div class="typing-dots"><span></span><span></span><span></span></div></div>';
    const mdBody = aiContent.querySelector('.md-body');
    const taskFacts = [];
    let memFlushed = 0;   // 修复 W27：记忆只追加增量（原每轮全量 append_memory，二次方膨胀挤占 prompt）
    // 工具精准路由：按问题域筛选，不全量下发
    const lastUser = [...s.messages].reverse().find(m => m.role === 'user');
    const routeText = lastUser ? (typeof lastUser.content === 'string' ? lastUser.content
      : Array.isArray(lastUser.content) ? lastUser.content.map(p => p.text || '').join(' ') : '') : '';
    // 修复 TOK-4（v1.4）：路由输入增强——回溯「最近 2 轮已调用工具名」与
    // 「最近一条工具结果前 200 字符」，防多步任务漏路由（首条消息没提但后续要用的工具域）
    const recentToolNames = [];
    let rounds = 0;
    for (let i = s.messages.length - 1; i >= 0 && rounds < 2; i--) {
      const m = s.messages[i];
      if (m.role === 'assistant' && m.tool_calls && m.tool_calls.length) {
        rounds++;
        m.tool_calls.forEach(tc => {
          const nm = tc.function ? tc.function.name : tc.name;
          if (nm && !recentToolNames.includes(nm)) recentToolNames.push(nm);
        });
      }
    }
    let recentToolResult = '';
    for (let i = s.messages.length - 1; i >= 0; i--) {
      const m = s.messages[i];
      if (m.role === 'tool' && typeof m.content === 'string' && m.content.trim()) { recentToolResult = m.content; break; }
    }
    const routedSet = routeTools(routeText, /附件/.test(routeText), recentToolNames, recentToolResult);
    const taskUsed = new Set();
    if (routedSet.size <= ROUTE_ALWAYS.length) {          // "继续/然后呢"类短指令：回溯会话近期用过的工具
      for (let i = s.messages.length - 1; i >= Math.max(0, s.messages.length - 40); i--)
        (s.messages[i].tool_calls || []).forEach(tc => taskUsed.add(tc.function ? tc.function.name : tc.name));
    }
    {   // 修复 ㉗：以下为原 try 块主体（保持缩进层级一致）
    const sysPrompt = document.getElementById('systemPrompt').value.trim();
    const enableSearch = document.getElementById('enableSearch').checked;
    // schema 唯一数据源：后端 build_tools（v1.0.0 前端硬编码 TOOLS 与后端双源且已漂移，
    // 缺 clipboard/process/memory 工具；后端失败时 v1.0.0 静默降级导致 AI 悄悄丢能力）。
    // 现在失败即显式报错，不再静默降级。
    const loadBackendTools = async (mode) => {
      const role = mode === 'readonly' ? 'ro' : (mode === 'off' ? 'chat' : 'full');
      // v1.3 R4：full 档才带 MCP 工具（Q3 裁决：MCP 仅进 full 角色）
      const beTools = await callApi('build_tools', [role, mode === 'full']);
      const parsed = beTools ? JSON.parse(beTools) : null;
      if (!Array.isArray(parsed)) throw new Error('build_tools 返回异常');
      const tools = parsed.slice();
      if (enableSearch && isGlmEndpoint()) tools.push({ type: 'web_search',   // v1.2 R6：web_search 为 GLM 专属能力
        web_search: { enable: true, search_engine: document.getElementById('searchEngine').value, search_result: false } });
      return tools;
    };
    let toolMode = document.getElementById('toolMode').value;
    let effectiveTools;
    try {
      effectiveTools = await loadBackendTools(toolMode);
    } catch (e) {
      addMessage('assistant', '⚠️ 无法从后端加载工具定义（build_tools 失败）：' + e.message +
        '\nAI 将不具备任何工具能力。请确认运行的是桌面端 GLM-Chat 并重新打包后重试。');
      aiContent.closest('.message').remove();   // 修复 ㉙：提前 return 前清掉遗留的「正在输入」动画气泡
      return;
    }
    // 路由过滤：只下发当前任务域的工具，省 token
    if (toolMode === 'full' && routedSet.size) {
      const allowed = new Set([...routedSet, ...taskUsed]);
      // v1.3 R4：mcp__ 工具 bypass 路由裁剪（用户显式启用的外部工具不参与域路由）
      effectiveTools = effectiveTools.filter(t => !t.function || allowed.has(t.function.name) || t.function.name.startsWith('mcp__'));
    }
    // 智能档：按任务复杂度自动选模型与推理力度（思考 token 按输出计价，轻任务应关思考）
    const _route = resolveModelEffort(routeText, routedSet.size > ROUTE_ALWAYS.length);
    // 修复（2026-10-17）：本地模式必须用 localState.model——此前本地分支落到
    // providerState.model || _route.model，回落到智能档的 GLM 模型名（glm-5.3-flash），
    // 打到 Ollama 即 404 model not found。
    const currentModel = localModeActive() ? (localState.model || _route.model)
      : (isGlmEndpoint() ? _route.model
        : (providerState.model || _route.model));          // v1.2 R6：自定义端点固定用配置的模型名
    if (_route.auto && isGlmEndpoint()) addSysTip(`智能档：${_route.tier} · ${_route.model} / 思考 ${_route.effort}`);
    else if (!isGlmEndpoint()) addSysTip(currentEndpointName() + ' / ' + currentModel);

    let finished = false;
    const readFileSet = new Set(s._readKeys || []);   // 会话级持久化已读记录
    const listDirsSet = new Set();
    const cmdDeduper = (() => {
      const WRITE = ['>', '>>', 'del', 'rmdir', 'rd', 'remove-item', 'mkdir', 'new-item', 'move', 'copy', 'reg', 'setx', 'format', 'taskkill', 'stop-process', 'start-process', 'iex'];
      let last = null; const recent = new Map(); const MAX = 64;
      return {
        check(cmd) {
          const key = String(cmd || '').trim().replace(/\s+/g, ' ').toLowerCase();
          if (key === last) return '与上一条完全相同的命令已拒绝重复执行;如需观察最新状态,请换角度(加参数)或先说明目的。';
          if (WRITE.some(h => key.includes(h)) && recent.has(key)) return '该写操作本次会话已执行过,已拦截以防误操作;确需重跑请修改参数或说明原因。';
          last = key; recent.set(key, true);
          if (recent.size > MAX) recent.delete(recent.keys().next().value);
          return null;
        }
      };
    })();
    let lastToolSig = null;
    const recentSigs = [];
    const taskEffort = _route.effort;
    const taskCapOut = 16384;  // 统一输出上限，不再区分纯聊天/工具模式
    const taskTemp = parseFloat(document.getElementById('temperature').value);
    const taskTopP = parseFloat(document.getElementById('topP').value);
    // 修复 B3（v1.5）：local 模式 max_tokens 默认 4096（模板默认 16384 时覆盖；
    // 用户显式设的值尊重）——本地小窗口模型输出 token 占比要克制
    const DEFAULT_MAX_TOKENS = 16384;
    let taskMaxTok = parseInt(document.getElementById('maxTokens').value) || 4096;
    if (typeof localState !== 'undefined' && localState.mode && taskMaxTok === DEFAULT_MAX_TOKENS) taskMaxTok = 4096;
    taskMaxTok = Math.min(taskMaxTok, taskCapOut);

    let finishReason = null;
    for (let round = 0; round < 60; round++) {
      // 修复 建议㉔（二轮）：finishReason 每轮复位——原跨轮次残留，上轮 length
      // 会让下轮正常结束也误触发截断续跑
      finishReason = null;
      // 动态检测 toolMode 切换，立即生效
      const curMode = document.getElementById('toolMode').value;
      if (curMode !== toolMode) {
        toolMode = curMode;
        try {
          effectiveTools = await loadBackendTools(curMode);
        } catch (e) {
          addMessage('assistant', '⚠️ 切换权限档后无法从后端加载工具定义：' + e.message);
          break;
        }
        if (toolMode === 'full' && routedSet.size) {
          const allowed = new Set([...routedSet, ...taskUsed]);
          // v1.3 R4：mcp__ 工具 bypass 路由裁剪（权限档热切换后同样放行）
          effectiveTools = effectiveTools.filter(t => !t.function || allowed.has(t.function.name) || t.function.name.startsWith('mcp__'));
        }
      }
      await compactHistory(s);
      freezeBeforeCurrentTask(s);
      const slimMsgs = shrinkHistoryForApi(buildMessagesForAPI(s.messages));
      applyShrinkMarkers(s.messages);   // 修复 UX-1（v1.4）：发送副本瘦身透明化——每轮重算并打弱化标记
      let sysContent = EFFICIENCY_PROMPT + (sysPrompt ? '\n\n' + sysPrompt : '');
      let effTools = effectiveTools;
      try {
        const beSys = await callApi('build_system_prompt', []);
        sysContent = EFFICIENCY_PROMPT + '\n\n' + (beSys ? JSON.parse(beSys) : '') + (sysPrompt ? '\n\n用户附加: ' + sysPrompt : '');
      } catch (e) { /* 系统提示词失败用前端默认 */ }
      const reqMsgs = [{ role: 'system', content: sysContent }, ...slimMsgs];
      if (pendingShots.length && shotState === 'idle') {
        const shotContent = [{ type: 'text', text: pendingShots.length > 1
          ? `[系统附图] 以下是 ${pendingShots.length} 张屏幕截图(按拍摄顺序),请据此操作。`
          : '[系统附图] 以下是当前屏幕截图,请据此判断界面状态并继续操作。' }];
        for (const sh of pendingShots) shotContent.push({ type: 'image_url', image_url: { url: sh } });
        reqMsgs.push({ role: 'user', content: shotContent });
        shotState = 'sending';
      }
      const reqBody = {
        model: currentModel,
        messages: reqMsgs,
        stream: true, stream_options: { include_usage: true },
        temperature: taskTemp, top_p: taskTopP, max_tokens: taskMaxTok
      };
      if (taskEffort === 'off') {
        reqBody.thinking = { type: 'disabled' };
      } else {
        reqBody.reasoning_effort = taskEffort;
      }
      if (!isGlmEndpoint()) {          // v1.2 R6：thinking/reasoning_effort 为 GLM 专属字段，自定义端点一律剥离
        delete reqBody.thinking;
        delete reqBody.reasoning_effort;
      }
      // 修复 B2（v1.5）：local_tool_capable=off 时根本不发 tools（模型能力声明不支持）
      const _localNoTools = (typeof localState !== 'undefined' && localState.mode && localState.tool_capable === 'off');
      if (effTools.length > 0 && !_localNoTools) reqBody.tools = effTools;
      else if (_localNoTools && effTools.length > 0) {
        addSysTip('本地模型已声明不支持工具调用，本轮以纯对话模式发送');
      }
      const now = Date.now();
      const cacheCold = lastReqAt && (now - lastReqAt) > 10 * 60 * 1000;
      lastReqAt = now;
      if (cacheCold) {
        const le = document.getElementById('liveTokenStat');
        if (le) le.textContent = '△ 距上次请求超 10 分钟，缓存可能过期，本轮输入按全价计 | 正在请求…';
      }
      // v1.2 R4：预算硬停检查点（每轮发起新请求前；进行中的工具调用已跑完）
      const hardStop = checkBudgetHardStop(s);
      if (hardStop) {
        showPausePanel(aiContent, s, 'budget', hardStop);
        toast('会话预算已用尽，已暂停发起新请求', 'warn');
        finished = true;
        mdBody.innerHTML = '';   // 修复 ㉙：暂停面板旁不再残留「正在输入」三点动画
        break;
      }
      let resp = await fetchGLMStream({ apiKey, body: reqBody }, abortController.signal);
      // 修复 B2（v1.5）：400 双降级链——① thinking 字段被拒（W24 原逻辑）→ 剥 GLM 专属字段重发；
      // ② 错误体含 tool/function 特征（模型不支持工具调用）→ 去 tools 重发一次并 toast。
      // 两条链各只走一次；errText 只读一次（Response body 不可重复读）。
      if (!resp.ok && resp.status === 400) {
        const errText = await resp.text().catch(() => '');
        if (reqBody.thinking) {
          delete reqBody.thinking;
          delete reqBody.reasoning_effort;   // 修复 建议㉖（二轮）：降级重试同步剥离 reasoning_effort（GLM 400 对同族字段一并拒）
          resp = await fetchGLMStream({ apiKey, body: reqBody }, abortController.signal);
        } else if (reqBody.tools && /tool|function/i.test(errText)) {
          delete reqBody.tools;
          toast('当前模型不支持工具调用，已切换为纯对话模式', 'warn');
          resp = await fetchGLMStream({ apiKey, body: reqBody }, abortController.signal);
        } else {
          throw new Error(humanizeApiError(`HTTP 400: ${errText}`, typeof localState !== 'undefined' && localState.mode));
        }
      }
      if (!resp.ok) {
        const errText = await resp.text().catch(() => '');
        // v1.2 R5：错误码人话映射（1113/401/429…），裸错误码不再直达用户
        // 修复 B4（v1.5）：local 模式走本地错误分类口径（503 loading/404 模型引导/401 免 Key）
        throw new Error(humanizeApiError(`HTTP ${resp.status}: ${errText}`, typeof localState !== 'undefined' && localState.mode));
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      /* 修复 B3（v1.5）：local 模式慢推理适配——首字节 >5s 未到则「本地推理中（已等待 Ns）」
       * 每秒更新（liveTokenStat 复用）；流中间 >120s 无字节提示不断流（病态服务器挂死防护）。
       * 常量与后端 FIRST_TOKEN_WAIT_HINT/IDLE_WATCHDOG 同口径。 */
      const _isLocal = (typeof localState !== 'undefined' && localState.mode);
      const FIRST_TOKEN_HINT_MS = 5000, IDLE_WATCHDOG_MS = 120000;
      let _firstChunk = true, _idleWarned = false;
      const _t0 = Date.now();
      let _lastChunkAt = _t0;
      if (_isLocal) {
        _localWaitTimer = setInterval(() => {
          const now = Date.now();
          if (_firstChunk) {
            const waited = Math.round((now - _t0) / 1000);
            const le = document.getElementById('liveTokenStat');
            if (le) le.textContent = `本地推理中（已等待 ${waited}s）…`;
          } else if (!_idleWarned && now - _lastChunkAt > IDLE_WATCHDOG_MS) {
            // 修复 B3：流中间停滞（read() 挂起期间循环体不执行，必须并发检测）
            _idleWarned = true;
            addSysTip('本地推理流已停滞 2 分钟，可继续等待或点「■」停止后重试');
          }
        }, 1000);
      }
      const _clearWaitTimer = () => { if (_localWaitTimer) { clearInterval(_localWaitTimer); _localWaitTimer = null; } };
      let fullContent = '';
      let fullReasoning = '';
      const toolCallMap = {};
      let usage = null;
      let pending = '';
      const reasonHtml = (rr) => rr ? `<div style="color:var(--text-2);font-style:italic;font-size:13px;margin-bottom:10px;padding:8px;background:var(--hover);border-radius:6px;border-left:3px solid var(--border);">思考中: ${escapeHtml(rr)}</div>` : '';
      const handleSseLine = (line) => {
        if (!line.startsWith('data: ')) return;
        const data = line.slice(6).trim();
        if (!data || data === '[DONE]') return;
        try {
          const json = JSON.parse(data);
          const delta = json.choices?.[0]?.delta;
          if (delta?.reasoning_content) {
            fullReasoning += delta.reasoning_content;
            scheduleRender(mdBody, () => reasonHtml(fullReasoning) + renderMd(fullContent));
            const le = document.getElementById('liveTokenStat');
            const est = Math.ceil((fullContent.length + fullReasoning.length) / 1.8);
            if (le) le.textContent = `生成中… 约 ${est.toLocaleString()} tokens`;
          }
          if (delta?.content) {
            fullContent += delta.content;
            partialContent = fullContent;   // 修复 W21（二轮）：镜像到函数级变量（catch 中不可见块内 let）
            scheduleRender(mdBody, () => reasonHtml(fullReasoning) + renderMd(fullContent));
            const le = document.getElementById('liveTokenStat');
            const est = Math.ceil((fullContent.length + fullReasoning.length) / 1.8);
            if (le) le.textContent = `生成中… 约 ${est.toLocaleString()} tokens`;
          }
          if (delta?.tool_calls) {
            for (const tc of delta.tool_calls) {
              const idx = (tc.index != null) ? tc.index : 0;   // 修复 ㉚：缺 index 的兼容端点退单块聚合（原 undefined 键造成错乱）
              if (!toolCallMap[idx]) toolCallMap[idx] = { id: 'call_r' + round + '_' + idx, name: '', argsStr: '' };
              if (tc.id) toolCallMap[idx].id = tc.id;
              if (tc.function?.name) toolCallMap[idx].name = tc.function.name;
              if (tc.function?.arguments) toolCallMap[idx].argsStr += tc.function.arguments;
            }
          }
          if (json.choices?.[0]?.finish_reason) finishReason = json.choices[0].finish_reason;
          if (json.usage) {
            usage = json.usage;
            const _cached = usage.prompt_tokens_details?.cached_tokens || 0;
            const _pr = usage.prompt_tokens || 0;
            window.__hitRate = _pr ? Math.round(_cached / _pr * 100) : 0;
            if (_pr > 4000 && window.__hitRate < 30) {
              // v1.1.1：从 console 升级为界面可见（缓存命中约 3 折计费，命中率低等于多花钱）
              const _le = document.getElementById('liveTokenStat');
              if (_le) _le.textContent = `△ 缓存命中率仅 ${window.__hitRate}%（本轮输入 ${_pr} tokens 多按全价计）| 建议：避免中途改系统设定/权限档，或 /compact 后重开话题`;
            }
            if (shotState === 'sending') {
              shotState = 'idle'; pendingShots = [];
              try { s.messages.push({ role: 'user', content: '[已向 AI 发送当前屏幕截图]' }); } catch (e) {}   // 修复 W25：原误写 text 字段，混入空 user 消息
            }
          }
        } catch (e) {}
      };
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (_firstChunk) { _firstChunk = false; _clearWaitTimer(); }   // 修复 B3：首字节到达，清等待态
        _lastChunkAt = Date.now();
        pending += decoder.decode(value, { stream: true });
        const lines = pending.split('\n');
        pending = lines.pop() || '';
        for (const line of lines) handleSseLine(line);
      }
      pending += decoder.decode();
      for (const line of (pending ? [pending] : [])) handleSseLine(line);
      pending = '';
      _clearWaitTimer();   // 修复 B3：流正常结束清理等待态计时器

      const toolCalls = Object.values(toolCallMap);
      const assistantMsg = { role: 'assistant', content: fullContent || null };
      if (usage) assistantMsg.usage = { ...usage, model: currentModel };
      if (toolCalls.length > 0) {
        assistantMsg.tool_calls = toolCalls.map(tc => ({
          id: tc.id, type: 'function',
          function: { name: tc.name, arguments: tc.argsStr }
        }));
      }
      s.messages.push(assistantMsg);
      if (usage) accumulateUsage(s, assistantMsg.usage);   // 修复 S8（二轮）：单调累计到会话计数器（归档/compact 不归零）
      if (aiContent && aiContent.dataset) aiContent.dataset.midx = s.messages.length - 1;   // 修复 UX-1/UX-3（v1.4）：live 气泡 stamp 下标（dataset 防御：桩/降级不抛错）

      if (toolCalls.length === 0) {
        if (usage) {
          const u = usage;
          const cached = u.prompt_tokens_details?.cached_tokens || 0;
          const div = document.createElement('div');
          div.className = 'usage-info';
          // 修复 S9 同型（二轮）：usage 字段来自 API 响应（不可信输入），转义后再拼 innerHTML
          let html = `<span>输入 <b>${escapeHtml(String(u.prompt_tokens ?? ''))}</b></span><span>输出 <b>${escapeHtml(String(u.completion_tokens ?? ''))}</b></span><span>合计 <b>${escapeHtml(String(u.total_tokens ?? ''))}</b></span>`;
          if (cached > 0) html += `<span style="color:var(--ok)">缓存命中 <b>${cached.toLocaleString()}</b>（半价）</span>`;
          if (_route.auto && isGlmEndpoint()) html += `<span style="color:var(--text-2)">智能档·${_route.tier}（${_route.model} / 思考 ${_route.effort}）</span>`;
          // v1.2 R5：本会话实时花费随每轮返回 1 秒内更新（与 token 统计同口径）
          const _sessCost = calcUsage(s.messages);
          html += `<span>本会话约花费 <b>¥${_sessCost.cost.toFixed(4)}</b></span>`;
          div.innerHTML = html;
          aiContent.appendChild(div);
          const _prevTurn = window.__turnTokens || 0;
          window.__turnTokens = (u.total_tokens || 0);
          if (_prevTurn > 0 && u.total_tokens > _prevTurn * 1.5) {
            const tip = document.createElement('div');
            tip.className = 'usage-info'; tip.style.color = 'var(--warn)';
            tip.textContent = `△ 本轮 tokens 比上轮高 ${Math.round((u.total_tokens / _prevTurn - 1) * 100)}%，可考虑 /compact 或新开会话`;
            aiContent.appendChild(tip);
          }
        }
        if (fullContent) {
          mdBody.innerHTML = renderMd(fullContent);
          enhanceCodeBlocks(mdBody);
          const copyBtn = document.createElement('button');
          copyBtn.className = 'copy-btn'; copyBtn.textContent = '⧉ 复制';
          copyBtn.onclick = () => navigator.clipboard.writeText(fullContent).then(() => {
            copyBtn.textContent = '✓ 已复制'; setTimeout(() => copyBtn.textContent = '⧉ 复制', 1500);
          });
          aiContent.appendChild(copyBtn);
          const regenBtn = document.createElement('button');
          regenBtn.className = 'copy-btn'; regenBtn.textContent = '↻ 重新生成';
          regenBtn.onclick = regenerate;
          aiContent.appendChild(regenBtn);
          const favBtn = document.createElement('button');
          favBtn.className = 'copy-btn'; favBtn.textContent = '☆ 收藏';
          favBtn.onclick = async () => {
            try {
              await callApi('append_memory', [JSON.stringify({ text: fullContent.slice(0, 500) })]);
              favBtn.textContent = '✓ 已收藏';
            } catch (e) { favBtn.textContent = '✗ 失败'; }
            setTimeout(() => favBtn.textContent = '☆ 收藏', 1500);
          };
          aiContent.appendChild(favBtn);
        }
        if (finishReason === 'length') {
          // 修复 建议㉔（二轮）：length 且带 tool_calls 时参数可能被截断（正则猜参
          // 只发生在极端损坏流）——显式提示，不静默
          if (toolCalls.length > 0) {
            const warn = document.createElement('div');
            warn.className = 'usage-info'; warn.style.color = 'var(--warn)';
            warn.textContent = '△ 输出在工具调用参数中途被截断，参数可能不完整；建议调高 max_tokens 或让 AI 分步执行。';
            aiContent.appendChild(warn);
          }
          const n = document.createElement('div');
          n.className = 'usage-info'; n.style.color = 'var(--warn)';
          n.textContent = '▮ 输出被截断，自动继续生成中…';
          aiContent.appendChild(n);
          s.autoResume = (s.autoResume || 0) + 1;
          if (s.autoResume <= 5) {
            finished = true;
            // 修复 S18：原直接调 continueLastGeneration 是死调用——isStreaming 尚未复位，首行守卫即 return。
            // 改 setTimeout 延续跑：finally 复位 isStreaming 之后才触发，截断输出真正自动继续。
            setTimeout(() => {
              if (currentSessionId !== s.id) return;   // 修复 S7（二轮）：350ms 窗口内切了会话 → 不续跑（防跨会话串扰）
              if (isStreaming) {                        // 修复 W20（二轮）：窗口内用户发了新消息 → 不静默丢弃，补手动按钮
                const contBtn = document.createElement('button');
                contBtn.className = 'copy-btn'; contBtn.textContent = '▸▸ 继续输出';
                contBtn.onclick = () => continueLastGeneration(s, apiKey);
                aiContent.appendChild(contBtn);
                return;
              }
              s.autoResume = 0;   // 修复 建议㉗（二轮）：续跑成功后清零（原只在不续跑的 else 分支清零，自动续跑路径终身累积，第 5 次后本会话再无自动续跑）
              continueLastGeneration(s, apiKey);
            }, 350);
            break;
          } else {
            s.autoResume = 0;
            const contBtn = document.createElement('button');
            contBtn.className = 'copy-btn'; contBtn.textContent = '▸▸ 继续输出';
            contBtn.onclick = () => continueLastGeneration(s, apiKey);
            aiContent.appendChild(contBtn);
          }
        }
        if (!fullContent) mdBody.innerHTML = '';   // 修复 ㉙：空回复不再残留「正在输入」动画
        finished = true;
        break;
      }
      mdBody.innerHTML = fullContent ? renderMd(fullContent) : '';

      const toolUis = toolCalls.map(tc => {
        let args = {};
        try { args = JSON.parse(tc.argsStr || '{}'); }
        catch (e) {
          const raw = String(tc.argsStr || '');
          const grabStr = (key) => {
            const m = raw.match(new RegExp('"' + key + '"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)"'));
            if (!m) return undefined;
            try { return JSON.parse('"' + m[1] + '"'); }
            catch (e2) {
              return m[1]
                .replace(/\\u([0-9a-fA-F]{4})/g, (_, h) => String.fromCharCode(parseInt(h, 16)))
                .replace(/\\n/g, '\n').replace(/\\r/g, '\r').replace(/\\t/g, '\t')
                .replace(/\\"/g, '"').replace(/\\\\/g, '\\');
            }
          };
          const grabLit = (key) => {
            const m = raw.match(new RegExp('"' + key + '"\\s*:\\s*(true|false|-?\\d+(?:\\.\\d+)?)'));
            if (!m) return undefined;
            return m[1] === 'true' ? true : m[1] === 'false' ? false : Number(m[1]);
          };
          args = {};
          ['path','new_path','content','cmd','old','new','file_path','filename'].forEach(k => {
            const v = grabStr(k); if (v !== undefined) args[k] = v;
          });
          ['offset','limit'].forEach(k => {
            const v = grabLit(k); if (v !== undefined) args[k] = v;
          });
          const ra = grabLit('replace_all');
          if (ra !== undefined) args.replace_all = ra;
          if (!args.path) {
            const m2 = raw.match(/"path"\s*:\s*"([^"]+)/);
            if (m2) args.path = m2[1];
          }
        }
        ['path','new_path','file_path','filename'].forEach(k => {
          if (typeof args[k] === 'string') args[k] = args[k].replace(/^"+|"+$/g, '');
        });
        if (!args.path && (args.file_path || args.filename || args.file || args.target)) {
          args.path = args.path || args.file_path || args.filename || args.file || args.target;
        }
        const label = buildToolLabel(tc.name, args);
        const toolDiv = document.createElement('div');
        toolDiv.className = 'tool-call-item';
        toolDiv.innerHTML = '<span class="tool-spinner"></span><span>' + escapeHtml(label) + '</span>';
        aiContent.appendChild(toolDiv);
        return { tc, args, label, toolDiv };
      });
      document.getElementById('chatContainer').scrollTop = document.getElementById('chatContainer').scrollHeight;

      const WRITE_SEQ_TOOLS = ['write_file','append_file','search_replace','move_path','copy_path','delete_path'];
      const toolResults = [];
      let batchPending = toolUis.slice();
      while (batchPending.length) {
        const seqIdx = batchPending.findIndex(t => WRITE_SEQ_TOOLS.includes(t.tc.name));
        const batch = seqIdx >= 0 ? batchPending.slice(0, seqIdx + 1) : batchPending;
        const batchResults = await Promise.all(batch.map(async ({ tc, args, label, toolDiv }) => {
        let result;
        if (tc.name === 'read_file' && args.path && args.force !== true) {
          const fileKey = String(args.path).toLowerCase() + '@' + (args.offset || 0);
          if (readFileSet.has(fileKey)) {
            result = JSON.stringify({ info: `文件 ${args.path} 自 ${args.offset || 0} 行起本次会话已读过；原文仍在上下文中，直接引用，禁止重读。`, path: args.path, skipped: true });
          } else {
            readFileSet.add(fileKey);
            result = await executeTool(tc.name, args);
          }
        } else if (tc.name === 'read_file' && args.path) {
          // force=true 放行重读
          result = await executeTool(tc.name, args);
        } else if (tc.name === 'list_dir') {
          const dirKey = String(args.path || '.').toLowerCase();
          if (listDirsSet.has(dirKey)) {
            result = JSON.stringify({ info: `目录 ${args.path || '.'} 本次任务已列出，请直接引用上方结果，不要重复列目录。`, path: args.path, skipped: true });
          } else {
            listDirsSet.add(dirKey);
            result = await executeTool(tc.name, args);
          }
        } else if (['run_command','run_powershell','run_admin_command'].includes(tc.name)) {
          const dupTip = cmdDeduper.check(args.cmd || args.command || '');
          if (dupTip) {
            result = JSON.stringify({ info: dupTip, skipped: true });
          } else {
            result = await executeTool(tc.name, args);
            try { const d = JSON.parse(result); if (d.output) { d.output = compressCliOutput(d.output); result = JSON.stringify(d); } } catch (e) {}
          }
        } else {
          result = await executeTool(tc.name, args);
          if (['write_file','append_file','search_replace','run_command','run_powershell','move_path','delete_path'].includes(tc.name)) {
            try { if (JSON.parse(result).ok) taskFacts.push(tc.name + ': ' + String(args.path || args.cmd || args.src || '').slice(0, 60)); } catch (e) {}
          }
          if (['write_file','append_file','search_replace','move_path','copy_path','delete_path'].includes(tc.name)) {
            try {
              const r = JSON.parse(result);
              if (r.ok) {
                const desc = {
                  write_file: `写入文件 ${args.path}`,
                  append_file: `追加内容到 ${args.path}`,
                  search_replace: `修改 ${args.path}`,
                  move_path: `移动 ${args.path} → ${args.new_path || args.dst}`,
                  copy_path: `复制 ${args.path} → ${args.new_path || args.dst}`,
                  delete_path: `删除 ${args.path}`
                }[tc.name] || tc.name;
                callApi('append_worklog', [desc]).catch(() => {});
              }
            } catch (e) {}
            if (['write_file','append_file','search_replace','delete_path','move_path','copy_path'].includes(tc.name)) {
              try {
                const parsed = JSON.parse(result);
                if (parsed.ok) {
                  const pks = [args.path, args.src, args.dst].filter(Boolean).map(p => String(p).toLowerCase());
                  for (const k of [...readFileSet]) {
                    if (pks.some(pk => k.startsWith(pk + '@'))) readFileSet.delete(k);
                  }
                }
              } catch (e) {}
            }
          }
        }
        const sp = toolDiv.querySelector('.tool-spinner');
        if (sp) sp.style.display = 'none';
        let tail = '';
        if (result === null) tail = '✗ 工具无返回';
        else {
          try {
            const r = JSON.parse(result);
            if (r && typeof r === 'object') {
              if (r.error) tail = '✗ ' + String(r.error).slice(0, 80);
              else if (r.skipped) tail = '⊘ ' + String(r.reason || r.info || '已拦截').slice(0, 60);
            }
          } catch (e) {}
        }
        toolDiv.innerHTML = '<span class="tc-dot"></span><span>' + escapeHtml(label + tail) + '</span>';
        toolDiv.classList.add(tail.startsWith('✗') ? 'fail' : 'done');
        try {
          const parsed = JSON.parse(result);
          if (tc.name === 'take_screenshot' && parsed.thumbnail) {
            const img = document.createElement('img');
            img.src = parsed.thumbnail;
            img.style.cssText = 'max-width:100%;max-height:200px;margin-top:6px;border-radius:6px;border:1px solid var(--border);cursor:pointer';
            img.onclick = () => window.open(parsed.thumbnail);
            toolDiv.appendChild(img);
          }
        } catch (e) {}
        /* 状态样式改由 .tool-call-item.done / .fail 类承载（原内联 background 已移除） */
        let resultForHistory = result;
        try {
          const parsed = JSON.parse(result);
          if (Array.isArray(parsed.content)) {   // 修复 ㉛：MCP 数组型 content 先 join 归一，再进入字符串截断逻辑
            parsed.content = parsed.content.map(p =>
              (p && typeof p === 'object') ? (p.text != null ? String(p.text) : JSON.stringify(p)) : String(p)).join('\n');
            resultForHistory = JSON.stringify(parsed);
          }
          if (parsed.dataUrl) {
            parsed.dataUrl = '[截图已保存到 ' + (parsed.path || '') + '，图片不再重复进上下文]';
            resultForHistory = JSON.stringify(parsed);
          }
          if (parsed.thumbnail) {
            delete parsed.thumbnail;
            resultForHistory = JSON.stringify(parsed);
          } else if (parsed.content && parsed.content.length > 240000) {
            parsed.content = parsed.content.slice(0, 240000) + '\n…(超大文件截断，可传 offset 继续读)';
            resultForHistory = JSON.stringify(parsed);
          } else if (parsed.output && parsed.output.length > 20000) {
            parsed.output = parsed.output.slice(0, 20000) + '\n…(超大输出截断，需要时可重新执行)';
            resultForHistory = JSON.stringify(parsed);
          }
        } catch (e) {}
        return { id: tc.id, content: resultForHistory, name: tc.name };
      }));
        toolResults.push(...batchResults);
        batchPending = batchPending.slice(batch.length);
      }
      toolResults.forEach(r => s.messages.push({ role: 'tool', tool_call_id: r.id, content: r.content, __tool: r.name }));
      toolCalls.forEach(tc => taskUsed.add(tc.name));  // 回填已用工具，后续轮次保留
      s._readKeys = [...readFileSet];   // 跨任务持久化已读记录

      const sig = JSON.stringify(toolCalls.map(tc => [tc.name, tc.argsStr]));
      const n = recentSigs.length;
      const alternating = n >= 3 && sig === recentSigs[n-2] && recentSigs[n-1] === recentSigs[n-3];
      recentSigs.push(sig); if (recentSigs.length > 6) recentSigs.shift();
      lastToolSig = sig;
      // v1.2 R4：循环熔断——同工具同参数 ×3（或交替模式）→ 暂停并询问，不再静默自动停止
      const loopHit = registerToolSig(sig);
      if (loopHit || alternating) {
        showPausePanel(aiContent, s, 'loop', loopHit || { count: '交替', sig });
        toast('检测到循环工具调用，已熔断暂停', 'err');
        finished = true; break;
      }
      // v1.2 R4：连续 15 步无进展熔断
      if (registerProgress(taskFacts.length, fullContent.length)) {
        showPausePanel(aiContent, s, 'stall', {});
        toast('连续多步无进展，已熔断暂停', 'warn');
        finished = true; break;
      }
      const spent = sessionSpent(s).tokens;   // 修复 S8（二轮）：30 万提醒读单调计数器（压缩不归零）
      if (spent > 300000 && !s.__budgetWarned) {
        s.__budgetWarned = true;
        const div = document.createElement('div');
        div.className = 'usage-info'; div.style.color = 'var(--warn)';
        div.textContent = `⚠ 本任务累计已消耗 ${spent.toLocaleString()} tokens，已超 30 万提醒线。建议总结进度后新开会话（任务继续运行，不会强制停止）。`;
        aiContent.appendChild(div);
      }
      s.updatedAt = Date.now();
      if (taskFacts.length > memFlushed) {   // 修复 W27：只追加本轮新增的增量事实
        try { await callApi('append_memory', [JSON.stringify({ text: taskFacts.slice(memFlushed, memFlushed + 20).join('；') })]); window.__memCache = await callApi('get_memory', []); } catch (e) {}
        memFlushed = taskFacts.length;
      }
      renderSessionList();
    }
    if (!finished) {
      const note = document.createElement('div');
      note.className = 'usage-info';
      note.textContent = '▮ 已达单次任务工具调用轮次上限(60)，如需继续，请发送「继续」。';
      aiContent.appendChild(note);
    }
    saveSessions();
    }   // 修复 ㉗：原 try 块主体结束
  } catch (err) {
    // 修复 S6（二轮）：请求失败/abort 后截图不能永久失陷——复位 shotState 让下轮可重发
    if (shotState === 'sending') shotState = 'idle';
    if (err.name === 'AbortError') {
      // 修复 W21（二轮）：abort 时固化部分正文入历史（原流中气泡有字但 messages 无此消息，
      // 重开即丢）+ 清理「正在输入」动画残留
      if (partialContent) {
        const last = s.messages[s.messages.length - 1];
        if (!last || last.role !== 'assistant') s.messages.push({ role: 'assistant', content: partialContent });
      }
      if (aiContent) {
        const dots = aiContent.querySelector && aiContent.querySelector('.typing-dots');
        if (dots) dots.remove();
      }
      const last = s.messages[s.messages.length - 1];
      if (last && last.role === 'assistant' && last.tool_calls) {
        const done = new Set(s.messages.filter(m => m.role === 'tool').map(m => m.tool_call_id));
        last.tool_calls.forEach(t => {
          if (!done.has(t.id)) s.messages.push({ role: 'tool', tool_call_id: t.id, content: '（用户已停止，未执行）' });
        });
      }
      saveSessions();
    } else {
      if (_localWaitTimer) { clearInterval(_localWaitTimer); _localWaitTimer = null; }   // 修复 B3：异常路径清理等待态计时器
      const shown = humanizeApiError(err.message);   // v1.2 R5：错误人话 + 可行操作
      if (aiContent) {
        aiContent.className = 'content error';
        aiContent.textContent = '请求失败: ' + shown;
      } else {
        addMessage('error', '请求失败: ' + shown);   // 修复 ㉗：循环未建气泡前出错不再砸在 null 上
      }
      toast('请求失败', 'err', { detail: String(err.message || '').slice(0, 400) });
      saveSessions();
    }
  } finally {
    isStreaming = false;
    document.getElementById('streamBar').classList.remove('on');
    const btn = document.getElementById('sendBtn');
    btn.textContent = '➤';
    btn.style.background = '';
    btn.onclick = sendMessage;
  }
}
