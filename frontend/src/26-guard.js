/* ================= 安全护栏（v1.2 R2）：确认矩阵前端拦截 + 设置 UI =================
 * 覆盖操作：delete_path / kill_process / clipboard_write / clipboard_read / take_screenshot
 *   + run_command / run_powershell / run_admin_command（修复 S4②：三个命令执行 op 纳入
 *   前端确认矩阵；默认 off 档 → 行为不变，用户提档加固时确认框才会出现）。
 * 三档：always（每次确认）/ list（保护名单）/ session（会话内首次确认）；off 不拦截。
 * 后端 guard_check 负责名单匹配与审计；本模块负责弹窗（复用 18-toast 的 uiConfirm）。
 *
 * 修复 S4①（confirm-token 前端接线）：确认框「允许」后先调后端 guard_confirm_token(op, detail)
 * 换取一次性 token（TTL 60s、绑定 op+detail 摘要），再携带 token 调实际 op——武装后的后端
 * 执行点（enforce_exec）只认 token/会话信任，前端确认不再是唯一防线。
 * 「本会话内不再提示」勾选 → guard_session_trust(op) 登记后端会话信任（切会话自动清空）。
 */

const GUARD_OP_MAP = {
  delete_path: 'delete_path',
  kill_process: 'kill_process',
  clipboard_write: 'clipboard_write',
  clipboard_read: 'clipboard_read',
  take_screenshot: 'take_screenshot',
  run_command: 'run_command',
  run_powershell: 'run_powershell',
  run_admin_command: 'run_admin_command'
};
const GUARD_OP_LABEL = {
  delete_path: '删除文件/目录', kill_process: '结束进程',
  clipboard_write: '写入剪贴板', clipboard_read: '读取剪贴板', take_screenshot: '屏幕截图',
  run_command: '执行命令', run_powershell: '执行 PowerShell', run_admin_command: '管理员命令'
};
const GUARD_RUN_OPS = ['run_command', 'run_powershell', 'run_admin_command'];

async function _guardDetailOf(op, args) {
  args = args || {};
  const d = {};
  // 修复 S4①：detail 必须与执行点传参同源（后端按 op+detail 摘要绑定 token）
  if (op === 'delete_path') d.path = args.path || args.file_path || args.filename || args.file || args.target || args.src || '';
  if (op === 'kill_process') { d.pid = args.pid != null ? args.pid : ''; d.name = args.name || ''; }
  if (op === 'clipboard_write') { d.len = (args.text || '').length; d.head = (args.text || '').slice(0, 40); }
  if (GUARD_RUN_OPS.includes(op)) d.cmd = String(args.cmd != null ? args.cmd : (args.command || ''));   // 与 executeToolRaw 的取值口径一致
  return d;
}

async function _guardDescribe(op, args) {
  args = args || {};
  const d = await _guardDetailOf(op, args);
  if (op === 'delete_path') {
    let sizeTxt = '';
    try {
      const r = JSON.parse(await callApi('get_file_info', [d.path]));
      if (r && r.size != null) sizeTxt = '（' + (r.size > 1048576 ? (r.size / 1048576).toFixed(1) + ' MB' : r.size + ' B') + '）';
    } catch (e) {}
    const recycle = args.recycle !== false;
    return { title: '确认删除', body: 'AI 请求删除：\n' + d.path + sizeTxt +
      '\n去向：' + (recycle ? '回收站（可恢复）' : '永久删除（不可恢复）'), danger: true };
  }
  if (op === 'kill_process')
    return { title: '确认结束进程', body: 'AI 请求结束进程：\n' + (d.name || 'pid=' + d.pid) +
      '\n未保存的数据将丢失。', danger: true };
  if (op === 'clipboard_write')
    return { title: '确认写入剪贴板', body: 'AI 请求写入剪贴板（' + d.len + ' 字符）：\n「' + d.head + '」\n将覆盖你当前的剪贴板内容。', danger: false };
  if (op === 'clipboard_read')
    return { title: '确认读取剪贴板', body: 'AI 请求读取你的剪贴板内容。\n剪贴板可能含敏感信息（密码/隐私文本）。', danger: false };
  if (op === 'take_screenshot')
    return { title: '确认屏幕截图', body: 'AI 请求截取当前屏幕。\n截图中可能包含你的其他窗口内容。', danger: false };
  if (op === 'run_command')
    return { title: '确认执行命令', body: 'AI 请求执行命令：\n' + String(d.cmd || '').slice(0, 400), danger: true };
  if (op === 'run_powershell')
    return { title: '确认执行 PowerShell', body: 'AI 请求执行 PowerShell：\n' + String(d.cmd || '').slice(0, 400), danger: true };
  if (op === 'run_admin_command')
    return { title: '确认管理员命令', body: 'AI 请求以管理员权限执行：\n' + String(d.cmd || '').slice(0, 400) +
      '\n该命令将以系统管理员权限运行，风险较高。', danger: true };
  return { title: '确认操作', body: op, danger: false };
}

/**
 * 护栏拦截入口（executeToolRaw 头部调用）。
 * 返回 {blocked, token}：
 *   blocked 为 null → 放行；blocked 为 JSON 字符串 → 拦截结果（直接作为工具结果返回给 AI）；
 *   token → 修复 S4①：用户「允许」后从后端换取的一次性 confirm token（携带调实际 op）。
 */
async function guardCheckTool(name, args) {
  const op = GUARD_OP_MAP[name];
  if (!op) return { blocked: null, token: null };
  args = args || {};
  // 会话内已信任：直接放行（后端持有同一会话信任态；名单仍会在 delete/kill 上兜底强制）
  if (guardTrusted.has(op)) return { blocked: null, token: null };
  // 修复 ③（三轮）：off 档本地短路——boot 已加载 guardConfig（110-boot loadGuardConfig），
  // 该 op 档位为 off 且无保护名单语义时不再发 guard_check RPC（原每个受护栏命令一次往返，
  // guard 全 off 时纯属浪费）。delete_path/kill_process 的保护名单 block 在后端优先于
  // 档位（guard_service.check 名单先行），仍走 RPC 保底；guardConfig 未加载（null）时
  // 保守走 RPC 由后端定档，行为不回退。
  if (guardConfig && guardConfig.tiers && guardConfig.tiers[op] === 'off'
      && op !== 'delete_path' && op !== 'kill_process') {
    return { blocked: null, token: null };
  }
  const detail = await _guardDetailOf(op, args);
  let verdict = { action: 'confirm' };
  try {
    const raw = await callApi('guard_check', [op, JSON.stringify(detail)]);
    verdict = JSON.parse(raw) || {};
  } catch (e) {
    // 后端不可用（旧 exe）：退回默认档位（delete/kill/clipboard_write 确认，其余放行）
    if (op !== 'delete_path' && op !== 'kill_process' && op !== 'clipboard_write') return { blocked: null, token: null };
  }
  if (verdict.action === 'block') {
    const reason = verdict.reason || '该操作命中保护名单，已被拒绝。';
    toast(reason, 'warn');
    return { blocked: JSON.stringify({ info: reason, skipped: true }), token: null };
  }
  if (verdict.action !== 'confirm') return { blocked: null, token: null };    // allow → 放行
  const desc = await _guardDescribe(op, args);
  const r = await uiConfirm({
    title: desc.title, body: desc.body, danger: desc.danger,
    okText: desc.danger ? '允许执行' : '允许',
    checkboxLabel: '本会话内不再提示「' + GUARD_OP_LABEL[op] + '」',
    // 修复 UX-2（v1.4）：第二勾选=永久信任（op 级，写 guard.json trustedOps，重启仍生效）
    checkboxLabel2: '永久信任此操作（重启后仍不再确认，可在设置→安全护栏重置）'
  });
  try {
    callApi('guard_audit', [op, JSON.stringify(detail),
      r.ok ? (r.checked2 ? 'trust-persistent' : (r.checked ? 'session-trust' : 'allow')) : 'deny']).catch(() => {});
  } catch (e) {}
  if (!r.ok) {
    const msg = '用户拒绝了本次' + GUARD_OP_LABEL[op] + '操作。请调整方案或询问用户意图，不要原样重试。';
    toast('已拒绝 AI 的' + GUARD_OP_LABEL[op] + '请求', 'ok');
    return { blocked: JSON.stringify({ info: msg, skipped: true }), token: null };
  }
  // 修复 S4①：同意后换取一次性 confirm token（TTL 60s，绑定 op+detail 摘要），执行点携带
  let token = null;
  try {
    const t = JSON.parse(await callApi('guard_confirm_token', [op, JSON.stringify(detail)]));
    if (t && t.token) token = t.token;
  } catch (e) { /* 旧 exe 无此方法：token 留空，按 legacy 行为直调（新后端会强制拦截并返回人话错误） */ }
  if (r.checked) {
    guardTrusted.add(op);
    // 修复 S4①：会话信任登记到后端（切会话由 set_current_sid 自动清空，与文案「本会话内」对齐）
    try { callApi('guard_session_trust', [op]).catch(() => {}); } catch (e) {}
  }
  // 修复 UX-2（v1.4）：永久信任落库（guard.json trustedOps，op 级）——读-改-写经
  // guard_save_config（既有 js_api，无新方法）；首次启用弹风险文案（PRD 验收）
  if (r.ok && r.checked2) await _trustPersistently(op);
  return { blocked: null, token };
}

/** 修复 UX-2（v1.4）：把 op 加入持久信任集（guard.json trustedOps）。失败不阻塞主流程。 */
async function _trustPersistently(op) {
  try {
    let cfg = {};
    try { cfg = JSON.parse(await callApi('guard_get_config', [])) || {}; } catch (e) { cfg = {}; }
    const list = Array.isArray(cfg.trustedOps) ? cfg.trustedOps.slice() : [];
    const firstTime = !list.includes(op);
    if (!list.includes(op)) list.push(op);
    cfg.trustedOps = list;
    const r = JSON.parse(await callApi('guard_save_config', [JSON.stringify(cfg)]));
    if (r && r.error) { toast('永久信任保存失败: ' + r.error, 'err'); return; }
    if (firstTime) {
      // 首次永久信任：明示风险（PRD：重启后该类操作仍不再确认）
      toast('已开启「' + GUARD_OP_LABEL[op] + '」永久信任：重启后该类操作仍不再确认。' +
            '如需恢复，设置 → 安全护栏 → 重置全部信任。', 'warn', { stay: true });
    } else {
      toast('已信任「' + GUARD_OP_LABEL[op] + '」', 'ok');
    }
  } catch (e) {
    toast('永久信任保存失败: ' + e.message, 'err');
  }
}

/** 修复 UX-2（v1.4）：重置全部持久信任（设置面板入口，二次确认）。 */
async function resetAllGuardTrust() {
  const r = await uiConfirm({
    title: '重置全部信任', body: '将清空所有「永久信任」的操作（本会话信任随重启自然失效）。\n之后每次危险操作都会重新确认。',
    danger: true, okText: '全部重置'
  });
  if (!r.ok) return;
  try {
    let cfg = {};
    try { cfg = JSON.parse(await callApi('guard_get_config', [])) || {}; } catch (e) { cfg = {}; }
    cfg.trustedOps = [];
    const rr = JSON.parse(await callApi('guard_save_config', [JSON.stringify(cfg)]));
    if (rr && rr.error) { toast('重置失败: ' + rr.error, 'err'); return; }
    toast('已重置全部持久信任', 'ok');
  } catch (e) {
    toast('重置失败: ' + e.message, 'err');
  }
}

/* ---- 护栏设置 UI（工作区面板「安全护栏」区块） ---- */
async function loadGuardConfig() {
  try {
    guardConfig = JSON.parse(await callApi('guard_get_config', [])) || null;
  } catch (e) { guardConfig = null; }
  renderGuardSettings();
}
function renderGuardSettings() {
  if (!guardConfig) return;
  const ops = [
    ['delete_path', '删除文件/目录'], ['kill_process', '结束进程'],
    ['clipboard_write', '写剪贴板'], ['clipboard_read', '读剪贴板'], ['take_screenshot', '截屏'],
    ['run_command', '执行命令'], ['run_powershell', 'PowerShell'], ['run_admin_command', '管理员命令']
  ];
  const tierName = { always: '每次确认', list: '仅保护名单', session: '会话内首次确认', off: '不拦截' };
  ops.forEach(([op, label]) => {
    const sel = document.getElementById('guard_' + op);
    if (sel) sel.value = (guardConfig.tiers || {})[op] || 'always';
  });
  const pp = document.getElementById('guardProtectPaths');
  if (pp) pp.value = (guardConfig.protect_paths || []).join('\n');
  const pc = document.getElementById('guardProtectProcs');
  if (pc) pc.value = (guardConfig.protect_processes || []).join('\n');
  // 修复 UX-2（v1.4）：持久信任状态展示（op 级；空态明示未开启）
  const ts = document.getElementById('guardTrustState');
  if (ts) {
    const list = (guardConfig.trustedOps || []).filter(op => GUARD_OP_LABEL[op]);
    ts.textContent = list.length
      ? '已永久信任：' + list.map(op => GUARD_OP_LABEL[op]).join('、')
      : '持久信任：未开启（确认框勾选「永久信任此操作」后生效）';
  }
}
async function saveGuardSettings() {
  if (!guardConfig) guardConfig = { tiers: {}, protect_paths: [], protect_processes: [] };
  guardConfig.tiers = guardConfig.tiers || {};
  Object.keys(GUARD_OP_LABEL).forEach(op => {
    const sel = document.getElementById('guard_' + op);
    if (sel) guardConfig.tiers[op] = sel.value;
  });
  const pp = document.getElementById('guardProtectPaths');
  guardConfig.protect_paths = (pp ? pp.value : '').split('\n').map(s => s.trim()).filter(Boolean);
  const pc = document.getElementById('guardProtectProcs');
  guardConfig.protect_processes = (pc ? pc.value : '').split('\n').map(s => s.trim()).filter(Boolean);
  try {
    const r = JSON.parse(await callApi('guard_save_config', [JSON.stringify(guardConfig)]));
    if (r && r.error) toast('护栏配置保存失败: ' + r.error, 'err');
    else toast('安全护栏配置已保存', 'ok');
  } catch (e) {
    toast('护栏配置保存失败: ' + e.message, 'err');
  }
}
