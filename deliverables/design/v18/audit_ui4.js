// UI 审计四轮：光影（glow/阴影/渐变）覆盖 + 明暗双模对比度精确计算
const fs = require('fs');
const html = fs.readFileSync('frontend/index.template.html', 'utf8');
const styles = [...html.matchAll(/<style>([\s\S]*?)<\/style>/g)].map(m => m[1]).join('\n');

// 令牌提取（亮/暗两块）
function tokens(block) {
  const t = {};
  for (const m of block.matchAll(/--([a-z0-9-]+)\s*:\s*([^;}]+)/g)) t[m[1]] = m[2].trim();
  return t;
}
const lightBlock = styles.slice(0, styles.indexOf('body.dark') > 0 ? styles.indexOf('body.dark') : styles.length);
const darkBlock = styles.slice(styles.indexOf('body.dark'));
const L = tokens(lightBlock), D = tokens(darkBlock);
const lum = (hex) => {
  const c = hex.replace('#', '').match(/../g).map(h => parseInt(h, 16) / 255)
    .map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const ratio = (a, b) => { const [l1, l2] = [lum(a), lum(b)].sort((x, y) => y - x); return (l1 + 0.05) / (l2 + 0.05); };
const hexOf = (v) => (v.match(/#[0-9a-fA-F]{6}/) || [null])[0];

console.log('=== 亮色对比度（正文阈值 4.5 / UI 组件 3.0） ===');
[['text-2', 'card-bg'], ['text-3', 'card-bg'], ['warn', 'warn-bg'], ['err', 'err-bg'],
 ['ok', 'ok-bg'], ['primary', 'primary-soft'], ['text-2', 'surface-2'], ['text-3', 'surface-2']]
  .forEach(([f, b]) => {
    const fa = hexOf(L[f] || ''), ba = hexOf(L[b] || '');
    if (!fa || !ba) { console.log(`  ${f} on ${b}: 令牌缺`); return; }
    const r = ratio(fa, ba);
    console.log(`  --${f} on --${b}: ${r.toFixed(2)} ${r >= 4.5 ? 'PASS' : (r >= 3 ? 'UI-only' : 'FAIL')}`);
  });
console.log('=== 暗色对比度 ===');
[['text-2', 'card-bg'], ['text-3', 'card-bg'], ['warn', 'warn-bg'], ['err', 'err-bg'],
 ['ok', 'ok-bg'], ['primary', 'primary-soft']]
  .forEach(([f, b]) => {
    const fa = hexOf(D[f] || L[f] || ''), ba = hexOf(D[b] || L[b] || '');
    if (!fa || !ba) { console.log(`  ${f} on ${b}: 令牌缺`); return; }
    const r = ratio(fa, ba);
    console.log(`  --${f} on --${b}: ${r.toFixed(2)} ${r >= 4.5 ? 'PASS' : (r >= 3 ? 'UI-only' : 'FAIL')}`);
  });

// 光影覆盖：glow/box-shadow/gradient 在交互元素上的分布
console.log('\n=== 光影覆盖 ===');
const shadowCls = [...new Set([...styles.matchAll(/\.([a-zA-Z0-9_-]+)[^{}]*\{[^}]*box-shadow/g)].map(m => m[1]))];
const glowCls = [...new Set([...styles.matchAll(/\.([a-zA-Z0-9_-]+)[^{}]*\{[^}]*--glow|drop-shadow|0 0 \d/g)].map(m => m[1]))];
console.log('box-shadow 类: ' + shadowCls.join(', '));
console.log('glow/drop-shadow 类: ' + glowCls.join(', '));
// 品牌面（应有光影的记忆点）
[['brand-logo', 'glow'], ['empty-icon', '呼吸+glow'], ['plan-badge', '无'], ['gg-light', '无'],
 ['sw-light', 'probed 光环'], ['msg-ic:hover', '背景'], ['ob-logo', '无']].forEach(([c, want]) => {
  const has = new RegExp('\\.' + c.replace(/[:]/g, '\\:').replace(/-/g, '\\-') + '[^{]*\\{[^}]*(box-shadow|glow|drop-shadow)').test(styles);
  console.log(`  ${c}: 光影=${has ? '有' : '无'}（期望 ${want}）`);
});
