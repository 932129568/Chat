/* ================= UX-4 设置面板锚点导航（v1.4 → v4 设置窗口化重设计） =================
 * 设置窗口左竖排分组导航：按钮与 set-block 一一对应 → 点击 scrollIntoView 平滑滚动；
 * 滚动监听当前 section 高亮（rAF 节流，滚动容器 = .set-content）。
 * v4 重设计（2026-10-20）：顶部 sticky pills → 左分组列表（WorkBuddy 设置同款布局），
 * 带分组头（data-group）+ 图标（标题关键词映射）；动态注入块（software/hybrid/grant）
 * 无 data-group 时按标题关键词归组。DOM/CSS 纯新增（UI 契约只增不改）。
 */

let _setNavBound = false;

/* 分组归置：模板块用 data-group；动态块按标题关键词推断 */
const SET_NAV_GROUPS = ['模型与端点', '对话', '数据', '系统'];
function _groupOf(blk, title) {
  const g = blk.dataset && blk.dataset.group;
  if (g) return g;
  if (/软件|混合|路由|端点|模型|连接/.test(title)) return '模型与端点';
  if (/授权|白名单|同步|WebDAV|数据/.test(title)) return '数据';
  if (/Token|参数|角色|联网|搜索/.test(title)) return '对话';
  return '系统';
}
/* 标题关键词 → 内联 SVG（stroke=currentColor 1.7 圆帽圆角，与 rail 同图标语言） */
const SET_NAV_ICONS = {
  '连接': '<path d="M9 7H7a5 5 0 0 0 0 10h2M15 7h2a5 5 0 0 1 0 10h-2M8 12h8"/>',
  'Token': '<path d="M13 2L4.5 13H11l-1 9 8.5-11H12l1-9z"/>',
  '参数': '<path d="M4 6h10M8 12h8M4 18h10"/><circle cx="17" cy="6" r="2"/><circle cx="15" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  '角色': '<path d="M12 2a4 4 0 0 1 4 4c0 2-2 3.5-4 4-2-.5-4-2-4-4a4 4 0 0 1 4-4z"/><path d="M5 21c0-3.5 3-6 7-6s7 2.5 7 6"/>',
  '同步': '<path d="M21 12a9 9 0 0 1-15.5 6.4M3 12a9 9 0 0 1 15.5-6.4"/><path d="M18 3v5h-5M6 21v-5h5"/>',
  '更新': '<path d="M12 3v12M6 11l6 6 6-6"/><path d="M4 21h16"/>',
  '外观': '<circle cx="12" cy="12" r="9"/><circle cx="8.5" cy="10" r="1.2" fill="currentColor"/><circle cx="12" cy="7.5" r="1.2" fill="currentColor"/><circle cx="15.5" cy="10" r="1.2" fill="currentColor"/><path d="M8.5 15c1 1.5 4.5 1.5 5.5 0"/>',
  '打扰': '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 8-3 8h18s-3-1-3-8"/><path d="M4 4l16 16"/>',
  'MCP': '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>',
  '沙箱': '<path d="M21 8v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l2 3h5a2 2 0 0 1 2 2z"/><path d="M10 12h4M12 12v3"/>',
  '软件': '<rect x="3" y="4" width="8" height="8" rx="1.5"/><rect x="13" y="4" width="8" height="8" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/><rect x="13" y="13" width="8" height="8" rx="1.5"/>',
  '授权': '<path d="M12 2l8 3v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V5z"/><path d="M9 12l2 2 4-4"/>'
};
function _iconOf(title) {
  for (const k of Object.keys(SET_NAV_ICONS)) {
    if (title.indexOf(k) >= 0) {
      return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ' +
        'stroke-linecap="round" stroke-linejoin="round">' + SET_NAV_ICONS[k] + '</svg>';
    }
  }
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="8"/></svg>';
}

function buildSetNav() {
  const nav = document.getElementById('setNav');
  if (!nav) return;
  const blocks = Array.from(document.querySelectorAll('#settingsPanel .set-block'));
  if (!blocks.length) return;
  nav.innerHTML = '';
  let lastGroup = null;
  blocks.forEach((blk, i) => {
    const titleEl = blk.querySelector('.set-title');
    const label = titleEl ? titleEl.textContent.trim() : ('分区 ' + (i + 1));
    // 修复 56（三轮）：自动编号避开已有 id
    if (!blk.id) {
      let n = i;
      while (document.getElementById('setSec' + n)) n++;
      blk.id = 'setSec' + n;
    }
    const group = _groupOf(blk, label);
    if (group !== lastGroup) {
      const gh = document.createElement('div');
      gh.className = 'set-nav-group';
      gh.textContent = group;
      nav.appendChild(gh);
      lastGroup = group;
    }
    const btn = document.createElement('button');
    btn.className = 'set-nav-btn';
    btn.type = 'button';
    btn.title = label;
    btn.innerHTML = _iconOf(label) + '<span>' + label.replace(/（.*?）/g, '').trim() + '</span>';
    btn.dataset.target = blk.id;
    btn.onclick = () => {
      blk.scrollIntoView({ behavior: 'smooth', block: 'start' });
      _highlightSetNav(blk.id);
    };
    nav.appendChild(btn);
  });
  if (!_setNavBound) {
    _setNavBound = true;
    // 滚动监听：设置内容列滚动时高亮当前 section（rAF 节流）
    let raf = 0;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        let best = null, bestTop = -Infinity;
        for (const blk of document.querySelectorAll('#settingsPanel .set-block')) {
          const r = blk.getBoundingClientRect();
          if (r.top <= 90 && r.top > bestTop) { bestTop = r.top; best = blk.id; }
        }
        if (best) _highlightSetNav(best);
      });
    };
    const sc = document.querySelector('#settingsPanel .set-content');
    if (sc) sc.addEventListener('scroll', onScroll, { passive: true });
    // 兜底：极端情况下内容列不可滚（外层滚）
    const panel = document.getElementById('settingsPanel');
    if (panel && panel !== sc) panel.addEventListener('scroll', onScroll, { passive: true });
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
