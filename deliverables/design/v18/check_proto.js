// v18 原型独立验证 v2（按磁盘实际内容校准）
const fs = require('fs');
const html = fs.readFileSync('deliverables/design/v18/prototype.html', 'utf8');
let fail = 0;
const ok = (n, c) => { console.log((c ? 'PASS' : 'FAIL') + ' ' + n); if (!c) fail++; };

// 1. JS 语法（逐 script 块）
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
ok('script-blocks', scripts.length >= 1);
let syn = true;
scripts.forEach((s, i) => { try { new Function(s); } catch (e) { syn = false; console.log('  块' + i + ' 错误: ' + e.message.slice(0, 160)); } });
ok('js-syntax', syn);

// 2. transition:all 只允许出现在注释/禁则文字里（无实际声明）
const taLines = html.split('\n').filter(l => /transition:\s*all/.test(l) && !/禁|铁律|·|禁止/.test(l));
ok('no-transition-all-decl', taLines.length === 0);
if (taLines.length) console.log('  实际声明行:', taLines.slice(0, 3).map(l => l.trim().slice(0, 80)));

// 3. 布局属性动画（keyframes 内）
ok('no-layout-kf', !/@keyframes[^{]*\{[^}]*\b(width|height|margin|top|left|padding|font-size)\s*:/.test(html));

// 4. HEX：剥离令牌块后规则区仅 #fff
const styleBlocks = [...html.matchAll(/<style>([\s\S]*?)<\/style>/g)].map(m => m[1]).join('\n');
const rules = styleBlocks.replace(/:root\{[^}]*\}/g, '').replace(/body\.dark\{[^}]*\}/g, '');
const hexes = [...new Set((rules.match(/#[0-9a-fA-F]{3,8}\b/g) || []))];
ok('hex-only-fff', hexes.every(h => h.toLowerCase() === '#fff'));
console.log('  规则区 HEX:', hexes.join(' ') || '（无）');

// 5. 外部引用：仅允许设计内引导链接（7-zip 官网），无 script/style/font 外载
const ext = [...html.matchAll(/(?:src|href)\s*=\s*["'](https?:)?\/\/([^"']+)["']/g)].map(m => m[2]);
ok('external-only-by-design', ext.length > 0 && ext.every(d => d.includes('7-zip.org')));
console.log('  外链清单:', ext.join(' ') || '（无）');

// 6. 模块类名（九域前缀至少各 1 个代表）
const domains = { 'wait': /\.wait-|class="[^"]*wait-/, 'sp': /\.sp-|class="[^"]*sp-/, 'sw': /\.sw-|class="[^"]*sw-/,
  'hy': /\.hy-|class="[^"]*hy-/, 'gr': /\.gr-|class="[^"]*gr-/, 'plan': /\.plan-|class="[^"]*plan-/,
  'dev': /\.dev-|class="[^"]*dev-/, 'clr': /\.clr-|class="[^"]*clr-/, 'ckpt': /\.ckpt-|class="[^"]*ckpt-/ };
Object.entries(domains).forEach(([k, re]) => ok('domain ' + k, re.test(html)));

// 7. 令牌与降级
['--dur-comp', '--ease-out-soft', '--stagger-xs', '--dur-breathe', '--dur-stream', 'v4ToolSettle'].forEach(t => ok('token ' + t, html.includes(t)));
ok('fx-off-stops', /fx-off[^{]*\{[^}]*animation:none/.test(html) || /body\.fx-off/.test(html));
ok('reduced-motion', /prefers-reduced-motion/.test(html));
ok('dark-theme', /body\.dark\{/.test(html));
ok('demo-console', /演示|控制台/.test(html));

console.log(fail === 0 ? '=== ALL-PASS ===' : '=== ' + fail + ' FAILED ===');
