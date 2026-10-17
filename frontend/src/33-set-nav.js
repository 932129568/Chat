/* ================= UX-4 设置面板锚点导航（v1.4） =================
 * 设置浮层顶部导航条：按钮与 set-block 一一对应 → 点击 scrollIntoView 平滑滚动；
 * 滚动监听当前 section 高亮（sticky 导航条始终可见）。
 * DOM/CSS 纯新增（UI 契约只增不改）；set-block 未打 data 锚点时按出现顺序自动编号。
 */

let _setNavBound = false;

function buildSetNav() {
  const nav = document.getElementById('setNav');
  if (!nav) return;
  const blocks = Array.from(document.querySelectorAll('#settingsPanel .set-block'));
  if (!blocks.length) return;
  nav.innerHTML = '';
  blocks.forEach((blk, i) => {
    const titleEl = blk.querySelector('.set-title');
    const label = titleEl ? titleEl.textContent.trim() : ('分区 ' + (i + 1));
    if (!blk.id) blk.id = 'setSec' + i;   // 幂等：重复构建不换 id
    const btn = document.createElement('button');
    btn.className = 'set-nav-btn';
    btn.type = 'button';
    btn.textContent = label;
    btn.dataset.target = blk.id;
    btn.onclick = () => {
      blk.scrollIntoView({ behavior: 'smooth', block: 'start' });
      _highlightSetNav(blk.id);
    };
    nav.appendChild(btn);
  });
  if (!_setNavBound) {
    _setNavBound = true;
    // 滚动监听：设置浮层滚动时高亮当前 section（rAF 节流）
    const panel = document.getElementById('settingsPanel');
    let raf = 0;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        let best = null, bestTop = -Infinity;
        for (const blk of document.querySelectorAll('#settingsPanel .set-block')) {
          const r = blk.getBoundingClientRect();
          if (r.top <= 80 && r.top > bestTop) { bestTop = r.top; best = blk.id; }
        }
        if (best) _highlightSetNav(best);
      });
    };
    if (panel) panel.addEventListener('scroll', onScroll, { passive: true });
    // 兜底：某些环境 settingsPanel 自身不滚动（外层 .panel-scroll 滚）
    const sc = document.querySelector('#panelChat .panel-scroll') || panel;
    if (sc && sc !== panel) sc.addEventListener('scroll', onScroll, { passive: true });
  }
  _highlightSetNav(blocks[0].id);
}

function _highlightSetNav(id) {
  const nav = document.getElementById('setNav');
  if (!nav) return;
  for (const b of nav.querySelectorAll('.set-nav-btn')) {
    b.classList.toggle('on', b.dataset.target === id);
  }
}
