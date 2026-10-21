// UI 审计第二轮：暗色破坏者(硬编码色)/非令牌时长/可点无 hover/输入无 focus/空态一致性
const fs = require('fs');
const html = fs.readFileSync('frontend/index.template.html', 'utf8');
const styles = [...html.matchAll(/<style>([\s\S]*?)<\/style>/g)].map(m => m[1]).join('\n');
const issues = [];
const warn = (m) => issues.push(m);

// A) 硬编码颜色（非 var()/transparent/inherit/currentColor/#fff heritage）——暗色主题破坏者
// 只查规则块内的 color/background/border/fill/stroke 属性值
const colorProps = /(?:^|[;{\s])((?:color|background(?:-color)?|border(?:-color)?|fill|stroke|box-shadow))\s*:\s*([^;}]+)/g;
const VAL_OK = /^(var\(|transparent|inherit|currentColor|none|#fff\b|#ffffff\b|0\s|rgba?\(255,\s*255,\s*255)/;
let m;
const seenColor = new Set();
while ((m = colorProps.exec(styles)) !== null) {
  const val = m[2].trim();
  if (VAL_OK.test(val)) continue;
  if (/gradient|url\(/.test(val)) continue;
  // rgba(16,18,28,.45) 这类遮罩是明暗通用设计值（深色遮罩两层都用），登记豁免
  if (/rgba\(16,\s*18,\s*28/.test(val)) continue;
  const key = m[1] + ':' + val.slice(0, 40);
  if (seenColor.has(key)) continue;
  seenColor.add(key);
  warn('硬编码颜色 ' + m[1] + ': ' + val.slice(0, 60));
}

// B) 非令牌时长（transition/animation 里硬编码 ms/s，非 var(--dur-*)）
const durRe = /(transition|animation)[^;}]*\b(\d+(?:\.\d+)?m?s)\b/g;
const seenDur = new Set();
while ((m = durRe.exec(styles)) !== null) {
  const v = m[2];
  if (v === '0s' || v === '0ms') continue;
  if (seenDur.has(v)) continue;
  seenDur.add(v);
  // 上下文（前 60 字符）辅助定位
  const ctx = styles.slice(Math.max(0, m.index - 70), m.index).replace(/\s+/g, ' ').slice(-55);
  warn('非令牌时长 ' + v + '（上下文: …' + ctx + '）');
}

// C) 可点元素（button/a/input/select/textarea 的类）无 :hover 且无 :focus 样式
const interactive = new Set();
for (const mm of html.matchAll(/<(?:button|a|input|select|textarea)\b[^>]*class="([^"]+)"/g)) {
  mm[1].split(/\s+/).forEach(c => { if (c) interactive.add(c); });
}
const noHover = [];
for (const cls of interactive) {
  const hasHover = new RegExp('\\.' + cls.replace(/-/g, '\\-') + ':hover').test(styles);
  const hasFocus = new RegExp('\\.' + cls.replace(/-/g, '\\-') + ':focus').test(styles);
  if (!hasHover && !hasFocus) noHover.push(cls);
}

// D) 输入类无 :focus 高亮（表单反馈）
const inputs = [...interactive].filter(c => /input|field|search|key/.test(c));
const noFocus = inputs.filter(c => !new RegExp('\\.' + c.replace(/-/g, '\\-') + ':focus').test(styles));

// E) 空态类清单（一致性参考）
const empties = [...new Set([...styles.matchAll(/\.([a-z-]*(?:empty|no-|zero)[a-z-]*)\s*\{/g)].map(x => x[1]))];

console.log('=== A 硬编码颜色（暗色破坏者）: ' + issues.filter(i => i.startsWith('硬编码')).length + ' 项 ===');
issues.filter(i => i.startsWith('硬编码')).slice(0, 15).forEach(i => console.log('  - ' + i));
console.log('\n=== B 非令牌时长: ' + issues.filter(i => i.startsWith('非令牌')).length + ' 项 ===');
issues.filter(i => i.startsWith('非令牌')).slice(0, 15).forEach(i => console.log('  - ' + i));
console.log('\n=== C 可点类无 hover/focus 反馈: ' + noHover.length + ' 个 ===');
console.log('  ' + noHover.join(', '));
console.log('\n=== D 输入类无 focus 样式: ' + noFocus.length + ' 个 ===');
console.log('  ' + noFocus.join(', '));
console.log('\n=== E 空态类（一致性参考）: ' + empties.length + ' 个 ===');
console.log('  ' + empties.join(', '));
