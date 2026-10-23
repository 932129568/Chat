/* ================= v1.9.0 · 平台探测与 macOS 适配层（69-platform.js） =================
 * M6.10：get_platform_info 后端接口未就绪（B 类移交项）——本模块以
 * navigator.platform 近似探测先行落地 UI 壳：body[data-platform] 根类驱动
 * 全部平台差异化（字体/滚动条/圆角/焦点环/键位），后端就绪后仅换数据源。
 *
 * 差异化注入策略（token-upgrade-plan §2.5）：一套 v4 令牌，平台差异全部走
 * body[data-platform="mac"] 下的令牌重定义——零 if 分支成本。
 * 纯增：新 DOM（mac 徽标）与 data-platform 属性；UI 契约零改动。
 */

(function () {
  if (typeof document === 'undefined') return;

  /** 平台探测（近似：后端 get_platform_info 就绪后优先用其返回）。 */
  function platformDetect() {
    if (window.__platformInfo && window.__platformInfo.os) return window.__platformInfo.os;
    const p = (navigator.platform || '').toLowerCase();
    if (p.indexOf('mac') >= 0) return 'mac';
    if (p.indexOf('win') >= 0) return 'win';
    if (p.indexOf('linux') >= 0) return 'linux';
    return 'win';
  }

  function platformInit() {
    const os = platformDetect();
    document.body.setAttribute('data-platform', os);
    if (os === 'mac') {
      document.body.classList.add('mac');
      // Cmd 键位提示钩子：快捷键帮助里 Ctrl 展示位替换为 ⌘（72-shortcuts 消费）
      window.__isMac = true;
      macBadgeMount();
    }
  }

  /** 设置区「连接与模型」块头部的平台徽标（caption 级，不抢视觉）。 */
  function macBadgeMount() {
    const head = document.querySelector('.cm-head');
    if (!head || document.getElementById('macBadge')) return;
    const badge = document.createElement('span');
    badge.id = 'macBadge';
    badge.className = 'mac-badge';
    badge.textContent = 'macOS 模式 · Cmd 已映射';
    head.appendChild(badge);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', platformInit);
  } else platformInit();
})();
