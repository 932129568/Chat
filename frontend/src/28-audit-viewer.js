/* ================= 审计日志查看器（v1.2 R2 配套，PRD Q6 落地） =================
 * 入口：设置 → 工作区 → 安全护栏区块「查看审计日志」→ openAuditViewer()
 * 数据源：callApi('get_audit_log', [limit, offset]) —— 纯本地 audit_log.jsonl，倒序（最新在前）。
 * 记录三类：guard_check 的判定（allow/confirm/block）、用户的决策（allow/deny/session-trust）、
 *          后端强制阻断（block / backend-enforced）。
 * 复用 18-toast 的 _modalRoot/_closeModal；DOM 全部 textContent 赋值，无注入面。
 */

let _auditFilter = 'all';   // 修复 S23：_auditFilter 从未声明，首次打开审计查看器即 ReferenceError（全项目 grep 无 let/const/var）

const AUDIT_STATUS = {
  'block':            { t: '已阻断',       c: 'warn' },
  'backend-enforced': { t: '后端强制阻断', c: 'warn' },
  'deny':             { t: '用户拒绝',     c: 'err'  },
  'allow':            { t: '已允许',       c: 'ok'   },
  'session-trust':    { t: '允许·会话信任', c: 'ok'  },
  'confirm':          { t: '待确认',       c: 'info' },
};

/** 从一条审计记录解析状态键：后端阻断 > 用户决策 > 判定结果。 */
function _auditStatusKey(en) {
  if (en.action === 'block') return en.decision === 'backend-enforced' ? 'backend-enforced' : 'block';
  if (en.action === 'decision') return en.decision || 'allow';
  return en.action || 'confirm';
}
function _auditDetailText(en) {
  const d = en.detail || {};
  // 修复 建议㊳（二轮）：recycle 是字符串 'false' 时不得当假（原 === 布尔恒假）；
  // data.total 兜底（undefined 不再显示"共 undefined 条"）
  const _recycleOff = (v) => v === false || v === 'false';
  if (d.path) return d.path + (_recycleOff(d.recycle) ? '（永久删除）' : '');
  if (d.name) return (d.name || '') + (d.pid != null && d.pid !== '' ? ' (pid=' + d.pid + ')' : '');
  if (d.head) return '剪贴板 ' + (d.len != null ? d.len + ' 字符：' : '') + d.head;
  if (d.server) return 'MCP ' + d.server + ' · ' + (d.tool || '?') +
    (d.tier ? '（' + d.tier + '）' : '') + (d.args ? ' ' + d.args : '');
  const vals = Object.entries(d).map(([k, v]) => k + '=' + v);
  return vals.length ? vals.join(' · ') : '—';
}

async function openAuditViewer() {
  const m = _modalRoot();
  m.innerHTML =
    '<div class="modal-mask"></div>' +
    '<div class="modal-card audit-card" role="dialog" aria-modal="true">' +
    '  <div class="modal-title">审计日志</div>' +
    '  <div class="modal-body">' +
    '    <div class="audit-toolbar">' +
    '      <button class="audit-chip on" data-f="all">全部</button>' +
    '      <button class="audit-chip" data-f="rejected">拒绝与阻断</button>' +
    '      <button class="audit-chip audit-refresh">刷新</button>' +
    '      <span class="audit-count" id="auditCount"></span>' +
    '    </div>' +
    '    <div class="audit-list" id="auditList">加载中…</div>' +
    '    <div class="set-hint" style="margin-top:8px;">流水仅存本机 <code>~/.glm-chat/audit_log.jsonl</code>，最多展示最新 300 条；参数已做摘要脱敏。</div>' +
    '  </div>' +
    '  <div class="modal-btns"><button class="modal-btn modal-ok primary">关闭</button></div>' +
    '</div>';
  m.querySelector('.modal-ok').onclick = _closeModal;
  m.querySelector('.modal-mask').onclick = _closeModal;
  m.querySelectorAll('.audit-chip[data-f]').forEach(btn => {
    btn.onclick = () => {
      m.querySelectorAll('.audit-chip[data-f]').forEach(b => b.classList.toggle('on', b === btn));
      _auditFilter = btn.dataset.f;
      renderAuditList();
    };
  });
  m.querySelector('.audit-refresh').onclick = () => renderAuditList();
  await renderAuditList();
}

async function renderAuditList() {
  const box = document.getElementById('auditList');
  const cnt = document.getElementById('auditCount');
  if (!box) return;
  box.textContent = '加载中…';
  let data = null;
  try {
    data = JSON.parse(await callApi('get_audit_log', [300, 0]));
  } catch (e) {
    box.textContent = '读取失败：' + e.message + '（后端可能为旧版，请重新打包）';
    if (cnt) cnt.textContent = '';
    return;
  }
  if (!data || data.error) {
    box.textContent = '读取失败：' + ((data && data.error) || '未知错误');
    if (cnt) cnt.textContent = '';
    return;
  }
  let entries = data.entries || [];
  if (_auditFilter === 'rejected') {
    entries = entries.filter(en => {
      const k = _auditStatusKey(en);
      return k === 'deny' || k === 'block' || k === 'backend-enforced';
    });
  }
  // 修复 建议㊳（二轮）：data.total 兜底（undefined 不再显示"共 undefined 条"）
  const _total = (data && typeof data.total === 'number') ? data.total : entries.length;
  if (cnt) cnt.textContent = '共 ' + _total + ' 条' + (_auditFilter === 'rejected' ? '（筛选后 ' + entries.length + '）' : '');
  box.textContent = '';
  if (!entries.length) {
    box.textContent = _total ? '没有匹配的记录' : '暂无审计记录——AI 执行受管控操作后，这里会留下流水。';
    return;
  }
  entries.forEach(en => {
    const k = _auditStatusKey(en);
    const st = AUDIT_STATUS[k] || { t: k, c: 'info' };
    const row = document.createElement('div');
    row.className = 'audit-row';
    const ts = document.createElement('span');
    ts.className = 'audit-ts';
    ts.textContent = en.ts || '';
    const op = document.createElement('span');
    op.className = 'audit-op';
    op.textContent = (GUARD_OP_LABEL && GUARD_OP_LABEL[en.op]) || en.op || '?';
    const stEl = document.createElement('span');
    stEl.className = 'audit-st ' + st.c;
    stEl.textContent = st.t;
    const dt = document.createElement('span');
    dt.className = 'audit-detail';
    dt.textContent = _auditDetailText(en);
    row.appendChild(ts); row.appendChild(op); row.appendChild(stEl); row.appendChild(dt);
    box.appendChild(row);
  });
}
