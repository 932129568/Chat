// 阴影海拔 + 入场编排审计（避免 shell 转义问题，文件方式运行）
const fs = require('fs');
const html = fs.readFileSync('frontend/index.template.html', 'utf8');
const styles = [...html.matchAll(/<style>([\s\S]*?)<\/style>/g)].map(m => m[1]).join('\n');
console.log('=== 阴影令牌 ===');
for (const m of styles.matchAll(/--shadow-[a-z]+\s*:\s*([^;}]+)/g)) console.log('  ' + m[0]);
const uses = [...styles.matchAll(/\.([a-zA-Z0-9_-]+)[^{}]*\{[^}]*box-shadow:\s*var\(--(shadow-[a-z]+)\)/g)];
const byShadow = {};
uses.forEach(m => { (byShadow[m[2]] = byShadow[m[2]] || []).push(m[1]); });
for (const [k, v] of Object.entries(byShadow)) console.log(k + ' (' + v.length + '): ' + [...new Set(v)].slice(0, 14).join(', '));
const hoverUp = [...styles.matchAll(/\.([a-zA-Z0-9_-]+):hover[^{]*\{[^}]*box-shadow/g)].map(m => m[1]);
console.log('=== hover 阴影变化: ' + [...new Set(hoverUp)].join(', '));
console.log('=== 列表入场覆盖 ===');
for (const d of ['sw-row','mm-row','gg-rule-row','tm-row','session-item','ws-card','mcp-row','mcp-tool-row','notify-item','cs-opt','sp-item','eff-row','search-hit','chart-empty']) {
  const has = new RegExp('\\.' + d.replace(/-/g,'\\-') + '[^{]*\\{[^}]*(v4LineIn|v4PlanStepIn|v4MsgIn)').test(styles);
  console.log('  ' + d + ': ' + (has ? 'Y' : '-'));
}
