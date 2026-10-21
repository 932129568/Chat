// UI 审计三轮：按压缩放/:active 覆盖、dark 硬编码色、四面板交互态、focus 环
const fs = require('fs');
const html = fs.readFileSync('frontend/index.template.html', 'utf8');
const styles = [...html.matchAll(/<style>([\s\S]*?)<\/style>/g)].map(m => m[1]).join('\n');

// A) :active 反馈覆盖（昨晚补了 transition，:active scale 只有少数类有）
const hoverCls = [...new Set([...styles.matchAll(/\.([a-zA-Z0-9_-]+):hover/g)].map(m => m[1]))];
const noActive = hoverCls.filter(c => !new RegExp('\\.' + c.replace(/-/g, '\\-') + ':active').test(styles));
console.log('=== A 有 hover 无 :active（按压无反馈）: ' + noActive.length + ' 个 ===');
console.log('  ' + noActive.join(', '));

// B) body.dark 下硬编码色（新补 CSS 若用非 var 色会破暗色——排除设计内例外）
const darkBlock = styles.slice(styles.indexOf('body.dark'));
const hardInDark = [...new Set([...darkBlock.matchAll(/(?:color|background|border-color|fill|stroke)\s*:\s*(#[0-9a-fA-F]{3,8})/g)].map(m => m[1]))];
console.log('\n=== B body.dark 内硬编码色（设计内例外除外）: ' + hardInDark.length + ' 个 ===');
console.log('  ' + hardInDark.slice(0, 20).join(', '));

// C) 四面板内容类的动效/交互覆盖
for (const d of ['session-', 'chart-', 'ws-', 'notify-', 'mcp-']) {
  const rules = (styles.match(new RegExp('\\.' + d.replace('-', '\\-') + '[a-zA-Z0-9_-]*', 'g')) || []);
  const withMotion = (styles.match(new RegExp('\\.' + d.replace('-', '\\-') + '[a-zA-Z0-9_-]*[^{}]*\\{[^}]*(?:transition|animation)', 'g')) || []);
  const withHover = (styles.match(new RegExp('\\.' + d.replace('-', '\\-') + '[a-zA-Z0-9_-]*:hover', 'g')) || []);
  console.log(`域 ${d}: ${rules.length} 处 / 动效 ${withMotion.length} / hover ${withHover.length}`);
}

// D) focus 环覆盖（全局 vs 仅设置窗口）
console.log('\n=== D focus 样式 ===');
console.log('全局 input:focus:', /(?:^|[,\s])input:focus/.test(styles.replace(/\.settings-panel input:focus/g, '')));
console.log(':focus-visible 存在:', /focus-visible/.test(styles));
console.log('按钮 focus-visible:', /\.(?:pill-btn|ghost-btn|modal-btn|rail-btn|msg-ic):focus-visible/.test(styles));

// E) 三态（空/加载/错误）覆盖盘点
console.log('\n=== E 三态类 ===');
for (const t of ['empty', 'loading', 'error', 'fail', 'skeleton']) {
  const n = (styles.match(new RegExp('\\.' + t + '[a-zA-Z0-9_-]*', 'g')) || []).length;
  console.log(`  ${t}: ${n} 个类`);
}
