/* ================= Toast 通知与模态确认（v1.2 R3 + R2 载体） =================
 * toast：三态（ok/warn/err）视觉分离、队列纵向堆叠不重叠、可手动关闭、自动消失（err 停留更久）。
 * uiConfirm / uiPrompt：alert()/confirm() 的应用内替代品（R3），也是 R2 破坏性操作确认框。
 * 纯新增模块，不改动任何既有 DOM id / CSS 类 / callApi 契约。
 */

/* ---- Toast ---- */
const _toastBox = (() => {
  let box = null;
  return () => {
    if (!box || !document.body.contains(box)) {
      box = document.createElement('div');
      box.id = 'toastBox';
      document.body.appendChild(box);
    }
    return box;
  };
})();

/**
 * toast(msg, type='info', opts={stay, detail})
 *  type: 'ok' | 'warn' | 'err' | 'info'
 */
function toast(msg, type, opts) {
  type = type || 'info';
  opts = opts || {};
  const box = _toastBox();
  // v4：队列溢出优先让最旧的走退场动画（无 close 句柄才直接移除）
  while (box.children.length >= 5) {
    const old = box.firstChild;
    if (old && old.close) old.close();
    else if (old) box.removeChild(old);
    else break;
  }
  const t = document.createElement('div');
  t.className = 'toast toast-' + type;
  const icon = type === 'ok' ? '✓' : type === 'warn' ? '△' : type === 'err' ? '✕' : 'ℹ';
  t.innerHTML = '<span class="toast-ico">' + icon + '</span>' +
    '<span class="toast-msg"></span>' +
    (opts.detail ? '<button class="toast-more">明细</button>' : '') +
    '<button class="toast-close">✕</button>';
  t.querySelector('.toast-msg').textContent = String(msg);
  // v4：__closing 去重 + MOTION.onAnimEnd 双兜底（.out 的 140ms 过渡结束即拆；
  //   桩环境无事件监听时 setTimeout 兜底，instant 降级立即拆）
  const close = () => {
    if (t.__closing) return;
    t.__closing = true;
    t.classList.add('out');
    if (typeof MOTION !== 'undefined' && !MOTION.instant()) {
      MOTION.onAnimEnd(t, 'transitionend', MOTION.compOut()).then(() => { try { t.remove(); } catch (e) {} });
    } else { try { t.remove(); } catch (e) {} }
  };
  t.querySelector('.toast-close').onclick = close;
  if (opts.detail) {
    t.querySelector('.toast-more').onclick = () => {
      let d = t.querySelector('.toast-detail');
      if (!d) { d = document.createElement('div'); d.className = 'toast-detail'; d.textContent = opts.detail; t.appendChild(d); }
      else d.style.display = d.style.display === 'none' ? '' : 'none';
    };
  }
  box.appendChild(t);
  const ttl = opts.pinned ? Infinity : (opts.stay ? 60000 : (type === 'err' ? 9000 : type === 'warn' ? 6500 : 4500));   // 修复 ㊵：pinned 永不自动消失（下载/更新等长流程进度）
  if (isFinite(ttl)) setTimeout(close, ttl);
  t.close = close;   // 修复 ㊵：暴露关闭句柄供调用方在流程结束时收尾
  return t;
}

/* ---- 模态层 ---- */
let _uiConfirmResolve = null;   // 修复 S22：当前挂起确认的兜底 resolve（模态被外部关闭时按「取消」收尾）
let _uiPromptResolve = null;    // 修复 W22（二轮）：uiPrompt 的兜底 resolve（原其 Promise 永不 settle）
let _uiConfirmQueue = Promise.resolve();   // 修复 S22：全局串行队列——并发确认依次弹窗，不再互相覆盖

function _settlePendingModal(reason) {
  // 修复 W22（二轮）：兜底取消集中处理 + toast 提示（原静默 deny，用户不知情）
  if (_uiConfirmResolve) {
    const r = _uiConfirmResolve; _uiConfirmResolve = null;
    try { toast('确认框被其它窗口接管，本次操作按取消处理' + (reason ? '（' + reason + '）' : ''), 'warn'); } catch (e) {}
    r({ ok: false, checked: undefined });
  }
  if (_uiPromptResolve) {
    const r = _uiPromptResolve; _uiPromptResolve = null;
    try { toast('输入框被其它窗口接管，本次输入已取消', 'warn'); } catch (e) {}
    r(null);
  }
}

function _modalRoot() {
  let m = document.getElementById('modalRoot');
  // v4：已存在的 root 带 .closing（正在退场）→ 立即 remove 再创建新的，
  // 保证「每次开弹=新元素」的计数语义，且旧 root 的延迟拆 DOM 不会误杀新模态
  if (m && m.classList && m.classList.contains('closing')) { try { m.remove(); } catch (e) {} m = null; }
  if (m) {
    // 修复 S22：模态被复用（重绘 innerHTML）时，挂起中的确认兜底按「取消」收尾，避免 Promise 永不 settle
    _settlePendingModal('modal-reuse');
    return m;
  }
  m = document.createElement('div');
  m.id = 'modalRoot';
  document.body.appendChild(m);
  return m;
}
function _closeModal() {
  const m = document.getElementById('modalRoot');
  // 修复 S22：模态 DOM 被移除而确认仍挂起时，兜底 resolve {ok:false}（防 Promise 永不 settle 卡死应用）。
  // v4：兜底逻辑保持同步（先 settle 再走退场动画拆 DOM）——S22/W22 测试依赖同步收尾。
  _settlePendingModal('modal-closed');
  if (!m) return;
  if (typeof MOTION !== 'undefined' && !MOTION.instant()) {
    // v4：.closing 类驱动遮罩/卡片退场（140ms in-soft），动画结束（+超时双兜底）后拆 DOM
    m.classList.add('closing');
    MOTION.onAnimEnd(m, 'animationend', MOTION.compOut()).then(() => { try { m.remove(); } catch (e) {} });
  } else { try { m.remove(); } catch (e) {} }
}

/**
 * uiConfirm({title, body, danger, okText, cancelText, checkboxLabel, checkboxLabel2})
 * → Promise<{ok:boolean, checked?:boolean, checked2?:boolean}>
 *   checked  = 第一勾选（本会话内不再提示）；checked2 = 第二勾选（永久信任，UX-2 v1.4）
 */
function uiConfirm(opts) {
  opts = opts || {};
  // 修复 S22：串行化——同一批并发工具触发多个确认时依次弹窗，杜绝单例模态互相覆盖
  const run = () => new Promise(resolve => {
    const m = _modalRoot();   // 修复 S22 追加：先取模态再登记兜底——若先登记，模态残留时
    // （上个确认被兜底取消但 DOM 未拆/外部查看器占用）新确认会被自己的兜底瞬间自我取消
    _uiConfirmResolve = (v) => { _uiConfirmResolve = null; resolve(v); };   // 修复 S22：登记兜底 resolve
    m.innerHTML =
      '<div class="modal-mask"></div>' +
      '<div class="modal-card" role="dialog" aria-modal="true">' +
      '<div class="modal-title"></div>' +
      '<div class="modal-body"></div>' +
      (opts.checkboxLabel ? '<label class="modal-check"><input type="checkbox" id="modalChk"><span></span></label>' : '') +
      (opts.checkboxLabel2 ? '<label class="modal-check"><input type="checkbox" id="modalChk2"><span></span></label>' : '') +
      '<div class="modal-btns">' +
      '<button class="modal-btn modal-cancel"></button>' +
      '<button class="modal-btn modal-ok"></button>' +
      '</div></div>';
    m.querySelector('.modal-title').textContent = opts.title || '确认';
    const body = m.querySelector('.modal-body');
    if (opts.bodyHtml) body.innerHTML = opts.bodyHtml;
    else body.textContent = opts.body || '';
    if (opts.checkboxLabel) m.querySelector('#modalChk').nextElementSibling.textContent = opts.checkboxLabel;
    if (opts.checkboxLabel2) {
      const lbl2 = m.querySelector('#modalChk2').nextElementSibling;
      lbl2.textContent = opts.checkboxLabel2;
      lbl2.style.color = 'var(--warn)';   // 修复 UX-2（v1.4）：永久信任勾选视觉差异化（高风险语义）
    }
    m.querySelector('.modal-ok').textContent = opts.okText || '确定';
    m.querySelector('.modal-cancel').textContent = opts.cancelText || '取消';
    m.querySelector('.modal-ok').classList.add(opts.danger ? 'danger' : 'primary');
    const done = (ok) => {
      const chk = m.querySelector('#modalChk');
      const chk2 = m.querySelector('#modalChk2');
      const checked = chk ? chk.checked : undefined;
      const checked2 = chk2 ? chk2.checked : undefined;
      if (_uiConfirmResolve) _uiConfirmResolve({ ok, checked, checked2 });   // 先 resolve（清兜底句柄）再拆 DOM
      _closeModal();
    };
    m.querySelector('.modal-ok').onclick = () => done(true);
    m.querySelector('.modal-cancel').onclick = () => done(false);
    m.querySelector('.modal-mask').onclick = () => done(false);
    setTimeout(() => m.querySelector('.modal-ok').focus(), 30);
  });
  // 修复 S22：确认串行入队——前一个确认收尾后才弹下一个
  const p = _uiConfirmQueue.then(run, run);
  _uiConfirmQueue = p.then(() => {}, () => {});
  return p;
}

/**
 * uiPrompt({title, body, placeholder, value, type})
 * → Promise<string|null>  （prompt 的替代；取消返回 null）
 */
function uiPrompt(opts) {
  opts = opts || {};
  // 修复 W22（二轮）：uiPrompt 复用全局模态队列——与 uiConfirm 并发时不再互相覆盖
  //（原绕过队列直开模态，可把挂起中的 uiConfirm 兜底吞掉）
  const run = () => new Promise(resolve => {
    _uiPromptResolve = (v) => { _uiPromptResolve = null; resolve(v); };   // 修复 W22：登记兜底
    const m = _modalRoot();
    m.innerHTML =
      '<div class="modal-mask"></div>' +
      '<div class="modal-card" role="dialog" aria-modal="true">' +
      '<div class="modal-title"></div>' +
      '<div class="modal-body"></div>' +
      '<input class="modal-input" id="modalInput">' +
      '<div class="modal-btns">' +
      '<button class="modal-btn modal-cancel">取消</button>' +
      '<button class="modal-btn modal-ok primary">确定</button>' +
      '</div></div>';
    m.querySelector('.modal-title').textContent = opts.title || '输入';
    m.querySelector('.modal-body').textContent = opts.body || '';
    const input = m.querySelector('#modalInput');
    input.placeholder = opts.placeholder || '';
    if (opts.value != null) input.value = opts.value;
    input.type = opts.type || 'text';
    const done = (v) => { if (_uiPromptResolve) _uiPromptResolve(v); _closeModal(); };   // 修复 W22：先消费兜底句柄再拆 DOM（不双发）
    m.querySelector('.modal-ok').onclick = () => done(input.value);
    m.querySelector('.modal-cancel').onclick = () => done(null);
    m.querySelector('.modal-mask').onclick = () => done(null);
    input.onkeydown = (e) => { if (e.key === 'Enter') done(input.value); };
    setTimeout(() => { input.focus(); input.select && input.select(); }, 30);
  });
  const p = _uiConfirmQueue.then(run, run);
  _uiConfirmQueue = p.then(() => {}, () => {});
  return p;
}
