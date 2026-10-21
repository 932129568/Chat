/* ================= v1.8.0 · 快捷键与命令帮助（72-shortcuts.js） =================
 * 入口：header 帮助钮（?）+ 键盘 ?（Shift+/，输入框聚焦时不触发）。
 * 内容：键盘快捷键 + 斜杠命令 + 流式控制，全部实接（非宣传文案）。
 * sc-* 纯新增类；浮层复用 v4 模态动效；Esc/点遮罩/× 三路关闭。
 */

const SC_SHORTCUTS = [
  { keys: ['Enter'], desc: '发送消息' },
  { keys: ['Shift', 'Enter'], desc: '输入框内换行' },
  { keys: ['Esc'], desc: '关闭浮层（设置 / 搜索面板 / 模态 / 图片查看）' },
  { keys: ['Ctrl', 'N'], desc: '新建会话（macOS 为 ⌘N）' },
  { keys: ['?'], desc: '打开本帮助' }
];
const SC_COMMANDS = [
  { cmd: '/plan <任务>', desc: '计划模式：先生成计划卡，批准后执行（自动建检查点）' },
  { cmd: '/compact', desc: '压缩当前会话历史为纪要（省 token）' }
];
const SC_MOUSE = [
  { desc: '生成中点发送钮（■）停止' },
  { desc: '点 header 放大镜打开浏览器搜索面板（可折叠）' },
  { desc: '搜索结果点击标题看原文预览浮层' }
];

function scOpen() {
  if (typeof document === 'undefined') return;
  scClose();
  const mask = document.createElement('div');
  mask.className = 'modal-mask sc-mask';
  const card = document.createElement('div');
  card.className = 'modal-card sc-card';
  card.setAttribute('role', 'dialog');
  card.setAttribute('aria-modal', 'true');
  const kbd = ks => ks.map(k => '<kbd class="sc-kbd">' + String(k).replace(/</g, '&lt;') + '</kbd>').join('<span class="sc-plus">+</span>');
  card.innerHTML =
    '<h3>快捷键与命令</h3>' +
    '<div class="sub">键盘、斜杠命令与流式控制（全部实接）</div>' +
    '<div class="sc-sec">键盘</div>' +
    SC_SHORTCUTS.map(x =>
      '<div class="sc-row"><span class="sc-keys">' + kbd(x.keys) + '</span>' +
      '<span class="sc-desc">' + x.desc + '</span></div>').join('') +
    '<div class="sc-sec">斜杠命令（输入框输入）</div>' +
    SC_COMMANDS.map(x =>
      '<div class="sc-row"><span class="sc-keys"><code class="sc-cmd">' + x.cmd + '</code></span>' +
      '<span class="sc-desc">' + x.desc + '</span></div>').join('') +
    '<div class="sc-sec">鼠标操作</div>' +
    SC_MOUSE.map(x => '<div class="sc-row"><span class="sc-desc only">· ' + x.desc + '</span></div>').join('') +
    '<div class="modal-acts"><button class="modal-btn primary sc-ok">知道了</button></div>';
  mask.appendChild(card);
  document.body.appendChild(mask);
  mask.addEventListener('click', e => { if (e.target === mask) scClose(); });
  card.querySelector('.sc-ok').onclick = scClose;
  document.addEventListener('keydown', scEsc);
  setTimeout(() => { const b = card.querySelector('.sc-ok'); if (b) b.focus(); }, 60);
}
function scEsc(e) {
  if (e.key === 'Escape') { e.stopPropagation(); scClose(); }
}
function scClose() {
  const mask = document.querySelector('.sc-mask');
  if (mask) mask.remove();
  document.removeEventListener('keydown', scEsc);
}

/** ? 键打开（输入框/文本区聚焦时不抢键；与 Ctrl+N 不冲突）。 */
function shortcutsInit() {
  if (typeof document === 'undefined') return false;
  document.addEventListener('keydown', (e) => {
    if (e.key !== '?') return;
    const tag = (e.target && e.target.tagName) || '';
    if (tag === 'INPUT' || tag === 'TEXTAREA' || e.ctrlKey || e.metaKey || e.altKey) return;
    e.preventDefault();
    scOpen();
  });
  return true;
}
