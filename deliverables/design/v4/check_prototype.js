// 原型独立抽检（主理人验证用，不轻信自报）
const fs = require('fs');
const html = fs.readFileSync('deliverables/design/v4/prototype.html', 'utf8');
let fail = 0;
const ok = (name, cond) => { console.log((cond ? 'PASS' : 'FAIL') + ' ' + name); if (!cond) fail++; };

// 1. JS 语法
const m = html.match(/<script>([\s\S]*)<\/script>/);
ok('js-syntax', !!m && (() => { try { new Function(m[1]); return true; } catch (e) { console.log('  ' + e.message); return false; } })());

// 2. 禁项 grep
ok('no-transition-all', !/transition:\s*all/.test(html));
ok('no-layout-keyframes', !/@keyframes[^{]*\{[^}]*\b(width|height|margin|top|left)\s*:/.test(html));
const ext = html.match(/(?:src|href)\s*=\s*["'](?:https?:)?\/\//g);
ok('no-external-refs', !ext);

// 3. v4 关键令牌在位
['--dur-press', '--dur-micro', '--dur-comp', '--dur-panel', '--dur-ambient', '--dur-sheen',
 '--ease-out-soft', '--ease-spring', '--stagger-xs', '--shift-panel', '--aurora-blur',
 '--glass-saturate'].forEach(v => ok('token ' + v, html.includes(v + ':')));

// 4. v4 关键规则/组件
['v4AuroraA', 'v4Stream', 'v4PanelInFwd', 'v4PanelOutBack', 'v4MsgIn', 'v4ToastIn',
 'v4ModalOut', 'v4CtxIn', 'v4CsIn', 'v4SetIn', 'v4AttachIn', 'v4ToolBreathe',
 'v4ToolSettle', 'v4TipIn', 'chat-container.batch', 'swapping', 'theming',
 'prefers-reduced-transparency', 'fx-off'].forEach(k => ok('rule ' + k, html.includes(k)));

// 5. au-3 品红光斑退役（不得有活跃动画引用）
ok('au-3-retired', /\.au-3\{display:none/.test(html) || !html.includes('au-3'));
// 6. v2 令牌值未动（抽检）
ok('v2-primary', html.includes('--primary:#4f6ef7'));
ok('v2-bg', html.includes('--bg:#f6f7f9'));
ok('dark-primary', html.includes('--primary:#6b84ff'));
// 7. 双主题
ok('dark-theme-block', /body\.dark\{/.test(html));
// 8. MOTION 常量表
ok('motion-table', html.includes('const MOTION') && html.includes('onAnimEnd'));
// 9. 演示控制台
ok('demo-console', /演示|控制台/.test(html));

console.log(fail === 0 ? '=== ALL-PASS ===' : '=== ' + fail + ' FAILED ===');
process.exit(fail === 0 ? 0 : 1);
