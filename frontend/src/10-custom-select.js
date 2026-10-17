/* ================= 自定义下拉组件 ================= */
const CS = { reg: new Map() };
function initCustomSelect(sel) {
  if (!sel || CS.reg.has(sel)) return;
  try {
    const wrap = document.createElement('div'); wrap.className = 'cs';
    const trigger = document.createElement('div'); trigger.className = 'cs-trigger';
    trigger.innerHTML = '<span class="cs-label"></span><span class="cs-arrow">▼</span>';
    const menu = document.createElement('div'); menu.className = 'cs-menu';
    wrap.appendChild(trigger); wrap.appendChild(menu);
    sel.parentNode.insertBefore(wrap, sel);
    sel.classList.add('cs-src');
    CS.reg.set(sel, { wrap, trigger, menu });
    trigger.addEventListener('click', (e) => {
      e.preventDefault();          // 阻止外层 label 把点击转发给隐藏的 select
      e.stopPropagation();
      const willOpen = !wrap.classList.contains('open');
      closeAllCS();
      if (willOpen) { CS.sync(sel); wrap.classList.add('open'); }
    });
    menu.addEventListener('click', (e) => {
      const opt = e.target.closest('.cs-opt'); if (!opt) return;
      e.stopPropagation();
      sel.value = opt.dataset.value;
      CS.sync(sel);
      closeAllCS();
      sel.dispatchEvent(new Event('change'));
    });
    CS.sync(sel);
  } catch (e) {
    sel.classList.remove('cs-src');   // 兜底:直接用原生 select
  }
}
CS.sync = function (sel) {
  const st = CS.reg.get(sel); if (!st) return;
  st.menu.innerHTML = '';
  Array.from(sel.options).forEach(o => {
    /* v4：分组标题项（option[data-group]）只渲染标题，不可选 */
    if (o.dataset && o.dataset.group) {
      const g = document.createElement('div');
      g.className = 'cs-group';
      g.textContent = o.dataset.group;
      st.menu.appendChild(g);
      return;
    }
    const d = document.createElement('div');
    d.className = 'cs-opt' + (o.value === sel.value ? ' on' : '');
    d.dataset.value = o.value;
    const t = document.createElement('span');
    t.className = 'cs-opt-t';
    t.textContent = o.textContent;
    d.appendChild(t);
    /* v4：ctx 徽标（option[data-badge]，本地系模型窗口 32k/128k） */
    const badge = (o.dataset && o.dataset.badge) ? String(o.dataset.badge) : '';
    if (badge) {
      const b = document.createElement('span');
      b.className = 'cs-badge';
      b.textContent = badge;
      d.appendChild(b);
    }
    st.menu.appendChild(d);
  });
  const cur = sel.options[sel.selectedIndex];
  st.trigger.querySelector('.cs-label').textContent = cur ? cur.textContent : (sel.value || '未选择');
};
CS.syncAll = function () { CS.reg.forEach((st, sel) => CS.sync(sel)); };
/* v4：下拉退场——open 的 wrap 加 .hiding 播 v4CsOut（140ms in-soft），
   动画结束（MOTION.onAnimEnd 双兜底）后移除 .open/.hiding；
   hiding 中重复调用直接返回（防重入）；Esc/外部点击路径不变 */
function closeAllCS() {
  CS.reg.forEach((st) => {
    const wrap = st.wrap;
    if (!wrap.classList.contains('open')) return;
    if (wrap.classList.contains('hiding')) return;   // 防重入：退场中不重复触发
    wrap.classList.add('hiding');
    const done = () => { try { wrap.classList.remove('open', 'hiding'); } catch (e) {} };
    if (typeof MOTION !== 'undefined' && !MOTION.instant()) {
      MOTION.onAnimEnd(st.menu, 'animationend', MOTION.compOut()).then(done);
    } else { done(); }
  });
}
document.addEventListener('click', (e) => {
  if (e.target && e.target.closest && e.target.closest('.cs')) return;
  closeAllCS();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const anyOpen = [...CS.reg.values()].some(st => st.wrap.classList.contains('open'));
    if (anyOpen) { closeAllCS(); return; }
    // 修复 ㉟：模态（确认框/输入框/审计查看器）打开时，Esc 只关模态，不再误 abort 流式生成
    const modal = document.getElementById('modalRoot');
    if (modal) {
      const cancel = modal.querySelector('.modal-cancel');
      if (cancel) cancel.click();          // 走模态自身的取消路径（uiConfirm/uiPrompt 会正常 resolve）
      else if (typeof _closeModal === 'function') _closeModal();
      return;
    }
    if (typeof abortController !== 'undefined' && abortController) abortController.abort();
  }
  if ((e.ctrlKey || e.metaKey) && (e.key === 'n' || e.key === 'N')) {
    e.preventDefault();
    if (typeof newSession === 'function') newSession();
  }
});
