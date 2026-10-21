// UI/动效审计：交互类无过渡、infinite 动画未进 fx-off 停列、新域动效缺失
const fs = require('fs');
const html = fs.readFileSync('frontend/index.template.html', 'utf8');
const styles = [...html.matchAll(/<style>([\s\S]*?)<\/style>/g)].map(m => m[1]).join('\n');
const issues = [];
const ok = (c) => console.log((c ? 'PASS' : 'FAIL') + ' ' + (c ? '' : ''));

// 1) 有 :hover 的交互类，其基规则无 transition（按钮/可点元素反馈生硬）
const hoverClasses = [...styles.matchAll(/\.([a-zA-Z0-9_-]+):hover/g)].map(m => m[1]);
const seen = new Set();
for (const cls of hoverClasses) {
  if (seen.has(cls)) continue;
  seen.add(cls);
  // 找基规则 .cls{...}（允许跨行）
  const re = new RegExp('\\.' + cls.replace(/-/g, '\\-') + '\\s*\\{[^}]*\\}', 'g');
  const m = styles.match(re);
  if (!m) continue;
  const hasTrans = m.some(r => /transition|animation/.test(r));
  if (!hasTrans) issues.push(`交互类 .${cls} 有 :hover 但基规则无 transition/animation`);
}
console.log('=== 交互类无过渡（生硬反馈）: ' + issues.length + ' 项 ===');
issues.slice(0, 25).forEach(i => console.log('  - ' + i));

// 2) infinite 动画清单 vs fx-off 显式停列
const infs = [...styles.matchAll(/@keyframes\s+([a-zA-Z0-9_-]+)/g)].map(m => m[1]);
const infUsed = [];
for (const name of infs) {
  const uses = [...styles.matchAll(new RegExp('animation:\\s*[^;}]*(?:infinite|alternate)[^;}]*', 'g'))].map(m => m[0]);
  for (const u of uses) if (u.includes(name) && !infUsed.includes(name)) infUsed.push(name);
}
// 另一种：animation 简写含 infinite 但 keyframes 名在别处——直接找 animation:x ... infinite 的行
const infRules = [...styles.matchAll(/animation:\s*([a-zA-Z0-9_-]+)\s+[^;}]*infinite/g)].map(m => m[1]);
const allInf = [...new Set([...infUsed, ...infRules])];
// fx-off 停列
const fxBlock = (styles.match(/body\.fx-off[^{]*\{[\s\S]*?\}\s*\}/g) || []).join('\n');
const fxStopped = [...fxBlock.matchAll(/\.([a-zA-Z0-9_-]+)/g)].map(m => m[1]);
console.log('\n=== infinite 动画清单: ' + allInf.join(', '));
console.log('=== fx-off 停列覆盖类: ' + [...new Set(fxStopped)].join(', '));
// 每个 infinite 的宿主类是否在停列里（粗查：宿主类名出现在 fxBlock）
const infHosts = [...styles.matchAll(/\.([a-zA-Z0-9_-]+)[^{}]*\{[^}]*animation:[^;}]*(?:infinite|alternate)/g)].map(m => m[1]);
const infHosts2 = [...styles.matchAll(/([a-zA-Z0-9_.#-]+)[^{}]*\{[^}]*animation:[^;}]*infinite/g)].map(m => m[1]);
console.log('infinite 宿主类:', [...new Set([...infHosts, ...infHosts2])].join(', '));

// 3) prefers-reduced-motion / reduced-transparency 存在性
console.log('\n=== 降级块 ===');
console.log('prefers-reduced-motion:', /prefers-reduced-motion/.test(styles));
console.log('prefers-reduced-transparency:', /prefers-reduced-transparency/.test(styles));
console.log('fx-off 变量级覆盖:', /body\.fx-off\{[^}]*--dur-/.test(styles));

// 4) 新域类清单（v1.8.0 后面板域）与动效存在性
for (const d of ['mem-', '69-', 'sw-', 'gr-', 'hy-']) {
  const rules = (styles.match(new RegExp('\\.' + d.replace('-', '\\-') + '[a-zA-Z0-9_-]*', 'g')) || []);
  const anim = (styles.match(new RegExp('\\.' + d.replace('-', '\\-') + '[a-zA-Z0-9_-]*[^{]*\\{[^}]*(?:transition|animation)', 'g')) || []);
  console.log(`域 ${d}: ${rules.length} 处引用 / ${anim.length} 处带动效`);
}

// 5) 对比度抽查（v4 令牌手工值，亮色）
const lum = (hex) => {
  const c = hex.replace('#', '').match(/../g).map(h => parseInt(h, 16) / 255)
    .map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const ratio = (a, b) => { const [l1, l2] = [lum(a), lum(b)].sort((x, y) => y - x); return (l1 + 0.05) / (l2 + 0.05); };
console.log('\n=== 对比度抽查（亮色，v2 令牌绑定值） ===');
[['--text-2 #5f6674', '--card-bg #ffffff'], ['--warn #b7791f', '--warn-bg #fdf5e6'],
 ['--err #cf3222', '--err-bg #fdecea'], ['--ok #1a7f4e', '--ok-bg #e8f6ee'],
 ['--text-3 #6a7180', '--card-bg #ffffff'], ['--primary #4f6ef7', '--primary-soft #eef1fe']]
  .forEach(([a, b]) => {
    const ca = a.match(/#[0-9a-f]{6}/)[0], cb = b.match(/#[0-9a-f]{6}/)[0];
    const r = ratio(ca, cb);
    console.log(`${a} on ${b}: ${r.toFixed(2)}:1 ${r >= 4.5 ? 'PASS' : (r >= 3 ? '大字可用' : 'FAIL')}`);
  });
