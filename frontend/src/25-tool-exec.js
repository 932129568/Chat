/* ================= 工具执行 =================
 * v3 · 前端插桩计时：executeTool 外层 performance.now() 计时，
 * 耗时写入结果 JSON 的 __ms 字段（仅供分析面板聚合展示，不参与 AI 对话语义）。
 * 纯前端改动，不新增任何后端方法。
 * 修复 S4①：护栏确认通过后携带后端签发的一次性 confirm token 调实际 op（仅追加尾参，
 * 旧 exe 未收到多余位置参数，保持兼容）。
 */
async function executeToolRaw(name, args) {
  if (!window.pywebview || !window.pywebview.api) {
    return JSON.stringify({error: '请在 Harbor.exe 桌面端中使用此功能'});
  }
  try { await callApi('set_current_sid', [currentSessionId]); } catch (e) {}
  args = args || {};   // 修复 ㊱：args 缺省兜底（原 pickPath 对 undefined 取属性虽不炸，但统一归一更稳）
  // v1.2 R2：破坏性操作护栏（delete/kill/剪贴板/截屏/命令执行 → 确认矩阵/保护名单）
  let guardToken = null;
  try {
    const g = await guardCheckTool(name, args);
    if (g && g.blocked) return g.blocked;
    guardToken = (g && g.token) || null;   // 修复 S4①：确认通过换取的一次性 token
  } catch (e) { /* 护栏自身异常不阻断工具执行（fail-open 由后端名单兜底） */ }
  // v1.3 R4：MCP 工具护栏挂点（mcp__ 前缀 → 定档确认；异常 fail-closed）
  let mcpDecision = 'deny';
  let mcpToken = null;
  if (name.startsWith('mcp__')) {
    try {
      const g = await mcpGuardCheck(name, args);
      if (g.blocked) return g.blocked;
      mcpDecision = g.decision;
      mcpToken = (g && g.token) || null;   // 修复 S4①：MCP 确认 token
    } catch (e) {
      return JSON.stringify({ error: 'MCP 护栏检查失败: ' + (e.message || e) });
    }
  }
  // 修复 ㊱：pickPath 缺省 ''（原 undefined 会以位置参数形式把 undefined 传给后端）
  const pickPath = (a) => a.path || a.file_path || a.filename || a.file || a.target || a.src || '';
  // 修复 ㊱：命令取值与护栏 detail 同口径（args.cmd 优先，缺失时回退 args.command）
  const pickCmd = (a) => a.cmd != null ? String(a.cmd) : String(a.command || '');
  // 修复 ㊱：timeout 显式判断（原 `args.timeout || 60` 吞 0 值）
  // 修复 ⑧（三轮）：兼容数字字符串（模型常传 "120"）——原 typeof number 检查被吞成默认 60
  const pickTimeout = (a) => {
    const t = a.timeout;
    if (typeof t === 'number' && t > 0) return t;
    if (typeof t === 'string' && /^\d+(\.\d+)?$/.test(t.trim()) && parseFloat(t) > 0) return parseFloat(t);
    return 60;
  };
  // 修复 S4①：token 作为最后一个位置参数追加（仅非空时——旧 exe 没有该形参，多传会 TypeError）
  const withToken = (arr, token) => token ? arr.concat([token]) : arr;
  try {
    if (name === 'write_file')        return await callApi('write_file', [pickPath(args), args.content]);
    if (name === 'append_file')       return await callApi('append_file', [pickPath(args), args.content]);
    if (name === 'search_replace')    return await callApi('search_replace', [pickPath(args), args.old, args.new, args.replace_all === true]);
    if (name === 'read_file')         return await callApi('read_file', [pickPath(args), args.offset || 0, args.limit || 0, args.force === true]);
    if (name === 'list_dir')          return await callApi('list_dir', [pickPath(args) || null]);
    if (name === 'make_dir')          return await callApi('make_dir', [pickPath(args)]);
    if (name === 'delete_path')       return await callApi('delete_path', withToken([pickPath(args), args.recycle !== false], guardToken));
    if (name === 'move_path')         return await callApi('move_path', [pickPath(args), args.new_path || args.dst]);
    if (name === 'copy_path')         return await callApi('copy_path', [pickPath(args), args.new_path || args.dst]);
    if (name === 'get_file_info')     return await callApi('get_file_info', [pickPath(args)]);
    if (name === 'run_command')       return await callApi('run_command', withToken([pickCmd(args), pickTimeout(args)], guardToken), 660000);
    if (name === 'run_powershell')    return await callApi('run_powershell', withToken([pickCmd(args), pickTimeout(args)], guardToken), 660000);
    if (name === 'run_admin_command') {
      /* 修复 S5/W8（三轮）：① timeout 参数接线（原只传 cmd，后端 timeout 是死参数）；
       * ② 前端 150s 超时与后端人审口径对齐——人审是 MessageBox 无限期阻塞，前端超时后
       *    模型若重试会排队等第二个确认框（二次提权执行）。超时返回不可重试语义。 */
      try {
        return await callApi('run_admin_command', withToken([pickCmd(args), pickTimeout(args)], guardToken), 150000);
      } catch (e) {
        const msg = String((e && e.message) || e);
        if (/timeout|超时|Timeout/i.test(msg)) {
          return JSON.stringify({ error: '管理员命令的人审确认未在 150 秒内完成，命令未执行。请勿原样重试——重复调用会再次弹出确认框；请等待用户确认或改用普通命令。', non_retryable: true });
        }
        throw e;
      }
    }
    if (name === 'read_more')         return await callApi('read_more', [args.cache_id, args.offset || 0, args.limit || 2000]);
    if (name === 'open_app')          return await callApi('open_app', [pickPath(args)]);
    if (name === 'open_url')          return await callApi('open_url', [args.url]);
    if (name === 'clipboard_read')    return await callApi('get_clipboard', withToken([], guardToken));
    if (name === 'clipboard_write')   return await callApi('set_clipboard', withToken([args.text || ''], guardToken));
    if (name === 'list_processes')    return await callApi('list_processes', [args.keyword || null]);
    if (name === 'kill_process')      return await callApi('kill_process', withToken([args.pid || null, args.name || null], guardToken));
    if (name === 'take_screenshot') {
      const res = await callApi('take_screenshot', withToken([args.left || null, args.top || null, args.width || null, args.height || null], guardToken));
      try {
        const data = JSON.parse(res);
        if (data.dataUrl) {
          const comp = await compressScreenshot(data.dataUrl);
          const dup = await shotDedup(comp);
          if (dup) return JSON.stringify({ok: true, path: data.path, info: dup});
          pendingShots.push(comp);
          return JSON.stringify({ok: true, path: data.path, note: '截图已压缩，下一步将自动作为图片提供给你分析屏幕内容。', thumbnail: comp});
        }
        return JSON.stringify({error: data.error || '截图失败'});
      } catch (e) { return JSON.stringify({error: '截图返回解析失败'}); }
    }
    if (name === 'append_memory')     return await callApi('append_memory', [typeof args === 'string' ? args : JSON.stringify(args)]);
    // v1.3 R4：MCP 工具分发（后端二次 enforce + 审计 + 结果渲染）
    if (name.startsWith('mcp__')) {
      try {
        return await mcpExecTool(name, args, mcpDecision, mcpToken);
      } catch (e) {
        return JSON.stringify({ error: 'MCP 工具调用失败: ' + (e.message || e) });
      }
    }
    return JSON.stringify({error: '未知工具: ' + name});
  } catch (e) { return JSON.stringify({error: (e && e.message) ? e.message : String(e)}); }   // 修复 ㊱：catch 输出 err.message（非 Error 抛出兜底 String）
}
async function executeTool(name, args) {
  const t0 = performance.now();
  const result = await executeToolRaw(name, args);
  const ms = performance.now() - t0;
  try {
    const d = JSON.parse(result);
    if (d && typeof d === 'object' && !d.__ms) { d.__ms = Math.round(ms); return JSON.stringify(d); }
  } catch (e) { /* 非 JSON 返回：保持原样，图表侧按无耗时处理 */ }
  return result;
}
