/* ================= v1.8.0 M3 域·Plan-Act 计划执行 UI（67-plan-card.js） =================
 * 计划卡 / todo 五态 / 偏差暂停条 / 批量澄清表单 / 检查点进度与回滚确认。
 * 设计：design/v18/ux-flows.md 流程 8/9/10 + motion-spec.md §1-10/11/13/14
 *   + prototype.html（plan-/clr-/ckpt-/dev- 九域类名与动效值同源）。
 * 数据：后端 plan_* / checkpoint_* / clarify_collect（_V12_EXTRA 隐身，联调规范 §3.5）。
 * 交互铁律（ux-flows）：
 *   - 计划即契约：Act 阶段以计划为基准；重大偏差 → 暂停条回问（不等执行完）
 *   - 澄清一次问完（≤5 问单表单），禁止执行中挤牙膏
 *   - 回滚二次确认用 inline（禁模态叠模态）；检查点超限降级有 warn
 *  typeof 守卫：模块顶层不直接引用 window/document（vm 沙箱可测）。
 */

let planCurrent = null;        // 当前计划 {task_id, title, steps[], status}
let planCardEl = null;         // 计划卡 DOM（消息流内）
let planRunning = false;       // 计划执行中（agent loop 回调推进 todo）
let planResolveApprove = null; // 批准 Promise 的 resolve（agent loop 等待用户批准）

/* ---------- 工具 ---------- */
function pcEl(id) {
  return (typeof document !== 'undefined') ? document.getElementById(id) : null;
}
function pcEsc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function pcCall(name, args, timeout) {
  if (typeof callApi !== 'function') return Promise.reject(new Error('pywebview bridge 未就绪'));
  return callApi(name, args, timeout || 30000);
}
function pcToast(msg, kind) {
  if (typeof toast === 'function') toast(msg, kind || 'info');
}
function pcScrollChat() {
  if (typeof scrollChat === 'function') scrollChat();
  else {
    const c = pcEl('chatContainer');
    if (c) c.scrollTop = c.scrollHeight;
  }
}

/* ---------- 计划卡渲染 ---------- */
function planCardRender(plan) {
  if (typeof document === 'undefined') return null;
  const host = pcEl('chatContainer') || document.body;
  if (planCardEl) planCardEl.remove();
  const card = document.createElement('div');
  card.className = 'plan-card';
  card.id = 'planCard';
  const files = (plan.files && plan.files.length)
    ? '<div class="plan-files">涉及：' + plan.files.map(pcEsc).join(' · ') + '</div>' : '';
  card.innerHTML =
    '<div class="plan-head">' +
      '<span class="plan-badge pending" id="planBadge">待批准</span>' +
      '<span class="plan-title">' + pcEsc(plan.title || '任务计划') + '</span>' +
    '</div>' + files +
    '<div class="plan-steps" id="planSteps">' +
      (plan.steps || []).map((s, i) =>
        '<div class="plan-step pending" data-i="' + i + '" style="animation-delay:' +
        (60 + i * 40) + 'ms">' +
        '<span class="st"></span><span class="txt">' + pcEsc(s.text) + '</span>' +
        (s.risk ? '<span class="risk ' + pcEsc(s.risk) + '">' +
          (s.risk === 'l2' ? '授权内' : '需确认') + '</span>' : '') +
        '</div>').join('') +
    '</div>' +
    '<div class="plan-acts" id="planActs">' +
      '<button class="pill-btn primary" id="planApproveBtn">批准执行</button>' +
      '<button class="pill-btn" id="planEditBtn">编辑</button>' +
      '<button class="pill-btn" id="planRejectBtn">拒绝</button>' +
    '</div>' +
    '<div class="plan-summary" id="planSummary"></div>';
  host.appendChild(card);
  planCardEl = card;
  const ap = pcEl('planApproveBtn');
  if (ap) ap.onclick = () => planCardApprove();
  const ed = pcEl('planEditBtn');
  if (ed) ed.onclick = () => pcToast('编辑态（示意）：可增删步骤、改风险标注', 'info');
  const rj = pcEl('planRejectBtn');
  if (rj) rj.onclick = () => planCardReject();
  pcScrollChat();
  return card;
}

/** 展示计划（ux-flows 流程 8 plan_review 态）。 */
async function planShow(plan) {
  planCurrent = plan;
  planCardRender(plan);
  // 等用户批准（agent loop 挂起）；拒绝 → 抛 AbortError 由调用方转为「已拒绝」
  return new Promise((resolve, reject) => {
    planResolveApprove = { resolve, reject };
  });
}

function planCardApprove() {
  const card = planCardEl;
  if (!card || !planResolveApprove) return;
  const acts = pcEl('planActs');
  const badge = pcEl('planBadge');
  if (badge) { badge.className = 'plan-badge running'; badge.textContent = '执行中'; }
  if (acts) {
    acts.classList.add('gone');
    const done = () => { acts.style.display = 'none'; };
    if (typeof MOTION !== 'undefined' && !MOTION.instant()) {
      MOTION.onAnimEnd(acts, 'transitionend', MOTION.compOut()).then(done);
    } else done();
  }
  const r = planResolveApprove;
  planResolveApprove = null;
  if (planCurrent) planCurrent.status = 'running';
  if (typeof pcCall === 'function' && planCurrent) {
    pcCall('plan_update', [planCurrent.task_id, 'running'], 15000).catch(() => {});
  }
  r.resolve();
}

function planCardReject() {
  const card = planCardEl;
  if (!card) return;
  card.style.transition = 'opacity var(--dur-comp-out) var(--ease-in-soft),transform var(--dur-comp-out) var(--ease-in-soft)';
  card.style.opacity = '0';
  card.style.transform = 'translateY(calc(-1 * var(--shift-comp)))';
  setTimeout(() => { card.remove(); if (planCardEl === card) planCardEl = null; }, 300);
  const r = planResolveApprove;
  planResolveApprove = null;
  if (r) r.reject(new DOMException('计划已被用户拒绝', 'AbortError'));
  pcToast('已拒绝计划 · 对话继续', 'info');
}

/** todo 步骤状态推进（agent loop 每个工具调用前后调用）。 */
function planStepStatus(index, status) {
  const card = planCardEl;
  if (!card || !planCurrent) return;
  const el = card.querySelector('.plan-step[data-i="' + index + '"]');
  if (!el) return;
  el.classList.remove('pending', 'doing', 'done', 'blocked', 'skipped');
  el.classList.add(status);
  if (planCurrent.steps && planCurrent.steps[index]) planCurrent.steps[index].status = status;
  if (planCurrent.task_id) {
    pcCall('plan_update', [planCurrent.task_id, '', index, status], 15000).catch(() => {});
  }
}

/** 完成摘要（ux-flows 流程 8 delivering → done）。 */
function planFinish(summaryText) {
  const card = planCardEl;
  if (!card || !planCurrent) return;
  const badge = pcEl('planBadge');
  if (badge) { badge.className = 'plan-badge done'; badge.textContent = '已完成'; }
  const sum = pcEl('planSummary');
  if (sum) {
    sum.innerHTML = pcEsc(summaryText || '任务完成') +
      '<br><a class="plan-rollback" onclick="ckptRollbackFlow(\'' + pcEsc(planCurrent.task_id) +
      '\');return false">回滚到此任务前 →</a>';
    sum.classList.add('show');
  }
  card.style.opacity = '.82';
  if (planCurrent.task_id) {
    pcCall('plan_update', [planCurrent.task_id, 'done'], 15000).catch(() => {});
  }
  pcScrollChat();
  pcToast('任务完成 · 已生成交付摘要', 'ok');
}

/* ---------- 偏差暂停条（ux-flows 流程 8 偏差检测） ---------- */
let planResolveDev = null;
function planDeviationShow(desc) {
  if (typeof document === 'undefined' || !planCardEl) return Promise.resolve('continue');
  const bar = document.createElement('div');
  bar.className = 'dev-bar flash';
  bar.id = 'devBar';
  bar.innerHTML =
    '<span class="ic">⚠</span><span class="t">' + pcEsc(desc || '出现计划外操作') + '</span>' +
    '<span class="a">' +
    '<button class="pill-btn" data-act="continue">自适应继续</button>' +
    '<button class="pill-btn danger" data-act="stop">停止任务</button>' +
    '</span>';
  // 偏差条插在计划卡后（同一消息流容器）
  planCardEl.parentNode.insertBefore(bar, planCardEl.nextSibling);
  pcScrollChat();
  return new Promise(resolve => {
    planResolveDev = resolve;
    bar.querySelectorAll('button').forEach(b => {
      b.onclick = () => {
        const act = b.dataset.act;
        bar.style.transition = 'opacity var(--dur-panel-out) var(--ease-in-soft),transform var(--dur-panel-out) var(--ease-in-soft)';
        bar.style.opacity = '0';
        bar.style.transform = 'translateY(calc(-1 * var(--shift-panel)))';
        setTimeout(() => bar.remove(), 300);
        if (planResolveDev) { planResolveDev(act); planResolveDev = null; }
      };
    });
  });
}

/* ---------- 批量澄清表单（ux-flows 流程 9） ---------- */
function clarifyShow(questions) {
  if (typeof document === 'undefined' || !planCardEl) return Promise.resolve({});
  const qs = (questions || []).slice(0, 5);   // 协议上限 5 问
  const form = document.createElement('div');
  form.className = 'clr-form';
  form.id = 'clarifyCard';
  form.innerHTML =
    '<div style="font-size:12.5px;font-weight:600;margin-bottom:4px">需要澄清 ' + qs.length +
    ' 个问题（一次问完）</div>' +
    qs.map((q, i) =>
      '<div class="clr-q" style="animation-delay:' + i * 40 + 'ms">' +
      '<div class="q">' + (i + 1) + '. ' + pcEsc(q.q) +
      '<span class="def">默认：' + pcEsc((q.options || [])[q.default || 0] || '') + '</span></div>' +
      (q.options || []).map((o, j) =>
        '<button class="clr-opt' + (j === (q.default || 0) ? ' on' : '') +
        '" data-q="' + i + '" data-o="' + j + '" style="animation-delay:' + (60 + i * 40) + 'ms">' +
        pcEsc(o) + '</button>').join('') +
      '</div>').join('') +
    '<div class="clr-acts">' +
      '<button class="pill-btn primary" id="clrSubmit">按所选继续</button>' +
      '<button class="pill-btn" id="clrDefault">全按默认继续</button>' +
      '<span class="clr-limit">澄清轮次 1/2 · 上限 5 问</span>' +
    '</div>';
  planCardEl.parentNode.insertBefore(form, planCardEl.nextSibling);
  pcScrollChat();
  form.querySelectorAll('.clr-opt').forEach(b => {
    b.onclick = () => {
      form.querySelectorAll('.clr-opt[data-q="' + b.dataset.q + '"]').forEach(o => o.classList.remove('on'));
      b.classList.add('on');
    };
  });
  return new Promise(resolve => {
    const submit = (allDefault) => {
      const answers = {};
      form.querySelectorAll('.clr-opt.on').forEach(o => { answers[o.dataset.q] = o.dataset.o; });
      form.querySelectorAll('.clr-q').forEach(q => q.style.opacity = '.55');
      form.style.transition = 'opacity var(--dur-comp-out) var(--ease-in-soft)';
      form.style.opacity = '0';
      setTimeout(() => form.remove(), 300);
      // 后端收集（缺项默认值）——失败也不阻断（本地同款兜底）
      pcCall('clarify_collect', [qs, answers], 15000)
        .then(raw => { try { resolve(JSON.parse(raw || '{}').resolved || []); } catch (e) { resolve([]); } })
        .catch(() => resolve([]));
    };
    const sb = pcEl('clrSubmit');
    if (sb) sb.onclick = () => submit(false);
    const df = pcEl('clrDefault');
    if (df) df.onclick = () => submit(true);
  });
}

/* ---------- 检查点与回滚（ux-flows 流程 10） ---------- */
function ckptShow(taskId, result) {
  if (typeof document === 'undefined' || !planCardEl) return;
  const modeTxt = result.mode === 'git' ? 'git HEAD 锚点' : (result.mode === 'snapshot' ? '文件快照' : '仅清单');
  const warn = (result.warnings && result.warnings.length)
    ? '<div class="ckpt-more">⚠ ' + pcEsc(result.warnings[0]) + '</div>' : '';
  const bar = document.createElement('div');
  bar.className = 'ckpt-prog done';
  bar.innerHTML =
    '<span class="ckpt-bar"><span class="ckpt-fill"></span></span>' +
    '<span class="ckpt-count">✓ 检查点就绪 · ' + pcEsc(modeTxt) +
    (result.snapshot_count ? ' · ' + result.snapshot_count + ' 个文件' : '') + '</span>';
  planCardEl.parentNode.insertBefore(bar, planCardEl.nextSibling);
  if (warn) {
    const w = document.createElement('div');
    w.innerHTML = warn;
    bar.parentNode.insertBefore(w.firstChild, bar.nextSibling);
  }
  pcScrollChat();
}

/** 回滚流程：清单 → inline 二次确认 → 执行 → 结果。 */
async function ckptRollbackFlow(taskId, host) {
  // host：浮层挂载容器（缺省=计划卡后；任务历史管理面板传自建容器）
  const anchor = (host && host.parentNode) ? host : planCardEl;
  let list = { files: [], mode: 'none' };
  try {
    const raw = await pcCall('checkpoint_list', [taskId], 15000);
    list = JSON.parse(raw || '{}');
  } catch (e) { /* 列表失败也允许尝试回滚 */ }
  if (!list.files || !list.files.length) {
    // git 锚点模式清单可能为空（reset 即恢复）——仍允许
    pcToast('检查点无文件清单（git 锚点模式将 reset 到任务前 HEAD）', 'info');
  }
  if (typeof document === 'undefined' || !anchor) return;
  const box = document.createElement('div');
  box.className = 'plan-card';
  box.style.marginTop = '10px';
  box.innerHTML =
    '<div class="plan-head"><span class="plan-badge pending">回滚确认</span>' +
    '<span class="plan-title">将恢复任务开始前的 ' + (list.files || []).length + ' 个文件（不可撤销）</span></div>' +
    '<div class="ckpt-list">' +
    (list.files || []).slice(0, 10).map(f =>
      '<div class="ckpt-row"><span class="f">' + pcEsc(f.path) + '</span><span class="s">待恢复</span></div>').join('') +
    ((list.files || []).length > 10 ? '<div class="ckpt-more">等 ' + (list.files || []).length + ' 个文件</div>' : '') +
    '</div>' +
    '<div class="plan-acts" id="rbActs">' +
      '<button class="pill-btn" id="rbCancel">取消</button>' +
      '<button class="pill-btn primary" id="rbConfirm">确认回滚</button>' +
    '</div>';
  anchor.parentNode.insertBefore(box, anchor.nextSibling);
  pcScrollChat();
  // 容器内查询（勿用全局 id——历史面板可能连续开多个回滚浮层）
  const cancel = box.querySelector('#rbCancel');
  if (cancel) cancel.onclick = () => box.remove();
  const confirm = box.querySelector('#rbConfirm');
  if (confirm) confirm.onclick = () => rbTwice(confirm, taskId, box, list.files || []);
}

function rbTwice(btn, taskId, box, files) {
  if (btn.dataset.armed) {
    if (btn._rbTimer) clearTimeout(btn._rbTimer);
    btn.textContent = '恢复中…';
    const rows = box.querySelectorAll('.ckpt-row');
    pcCall('checkpoint_rollback', [taskId], 60000)
      .then(raw => {
        let d = {};
        try { d = JSON.parse(raw || '{}'); } catch (e) {}
        const restored = d.restored || [];
        const failed = d.failed || [];
        rows.forEach((r, i) => setTimeout(() => {
          const p = r.querySelector('.f').textContent;
          const okHit = restored.some(x => String(x).indexOf(p) >= 0);
          const badHit = failed.some(x => String(x).indexOf(p) >= 0);
          if (okHit) { r.classList.add('restored'); r.querySelector('.s').textContent = '已恢复'; }
          else if (badHit) { r.classList.add('failed'); r.querySelector('.s').textContent = '失败'; }
        }, i * 120));
        setTimeout(() => {
          box.remove();
          if (failed.length && !restored.length) pcToast('回滚失败：' + failed[0], 'err');
          else if (failed.length) pcToast('部分恢复成功（' + failed.length + ' 个失败，当前版已备份 .rollback-bak）', 'warn');
          else pcToast('回滚完成 · 已恢复到任务开始前状态', 'ok');
        }, rows.length * 120 + 400);
      })
      .catch(e => {
        box.remove();
        pcToast('回滚请求失败：' + (e && e.message || e), 'err');
      });
    return;
  }
  btn.dataset.armed = '1';
  btn.textContent = '再次点击确认';
  btn.style.color = 'var(--err)';
  btn._rbTimer = setTimeout(() => {
    if (btn.dataset.armed) { btn.dataset.armed = ''; btn.textContent = '确认回滚'; btn.style.color = ''; }
  }, 3000);
}
