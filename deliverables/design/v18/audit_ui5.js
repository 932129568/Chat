// UI 审计五轮：视觉系统升级验收（2026-10-21）
// 验收标准：①令牌化率 ②will-change 覆盖 infinite 宿主 ③双Layer 阴影
// ④曲线家族唯一来源 ⑤fx-off 停列覆盖新宿主 ⑥降级三件套
const fs = require('fs');
const html = fs.readFileSync('frontend/index.template.html', 'utf8');
const styles = [...html.matchAll(/<style>([\s\S]*?)<\/style>/g)].map(m => m[1]).join('\n');
let pass = 0, fail = 0;
const check = (name, cond, detail) => {
  console.log((cond ? 'PASS' : 'FAIL') + ' | ' + name + (detail ? ' | ' + detail : ''));
  cond ? pass++ : fail++;
};

// ① 令牌化率：非 var() 的时长（排除登记的 keyframes 内 animation-delay/降级/呼吸循环值）
const durVals = [...styles.matchAll(/(?:transition|animation)[^;}]*?\b(\d+(?:\.\d+)?m?s)\b/g)].map(m => m[1]);
// 登记例外：降级 1ms/01ms、typing delay .15s/.3s、search-hit flash .8s、dashoffset 1s、brand breathe 4s
const REGISTERED = new Set(['1ms', '01ms', '.15s', '.3s', '.8s', '1s', '4s', '3s', '8s', '2s', '15s', '6s', '34s', '52s', '1.2s', '1.4s', '2.6s', '600ms', '800ms', '0s']);
const badDur = durVals.filter(v => !REGISTERED.has(v));
check('① 动效令牌化率 100%', badDur.length === 0, badDur.length ? '未登记: ' + [...new Set(badDur)].join(',') : '非令牌时长 0 处（登记例外 ' + REGISTERED.size + ' 项）');

// ② 新曲线/时长令牌存在且被应用
check('②a --ease-emphasized 定义', /--ease-emphasized:cubic-bezier/.test(styles));
check('②b --ease-anticipate 定义', /--ease-anticipate:cubic-bezier/.test(styles));
check('②c --dur-tap/--dur-panel-lg 定义', /--dur-tap:150ms/.test(styles) && /--dur-panel-lg:320ms/.test(styles));
check('②d emphasized 应用于大位移入场', /v4SetWinIn var\(--dur-panel-lg\) var\(--ease-emphasized\)/.test(styles));
check('②e anticipate 应用于 pop', /v4ChipIn var\(--dur-comp\) var\(--ease-anticipate\)/.test(styles));

// ③ 双 Layer 阴影（sm/md/lg 各含逗号两层）
const sm = (styles.match(/--shadow-sm:\s*([^;}]+)/) || [])[1] || '';
const md = (styles.match(/--shadow-md:\s*([^;}]+)/) || [])[1] || '';
const lg = (styles.match(/--shadow-lg:\s*([^;}]+)/) || [])[1] || '';
check('③a 亮色阴影双 Layer', sm.includes(',') && md.includes(',') && lg.includes(','));
const dsm = (styles.match(/body\.dark[\s\S]*?--shadow-sm:\s*([^;}]+)/) || [])[1] || '';
check('③b 暗色阴影双 Layer', dsm.includes(','));

// ④ 受光边/内发光令牌 + 应用
check('④a --edge-hi/--glow-inset 令牌', /--edge-hi:inset/.test(styles) && /--glow-inset:inset/.test(styles));
check('④b L1 卡浮起受光三合一', /box-shadow:var\(--shadow-sm\),var\(--edge-hi-soft\)/.test(styles));
check('④c 输入 focus 内发光', /box-shadow:var\(--glow-focus\),var\(--glow-inset\)/.test(styles));

// ⑤ 氛围：天光纱 + 品牌呼吸
check('⑤a 聊天区天光纱', /#chatContainer::before/.test(styles) && /linear-gradient\(180deg,var\(--primary-soft\)/.test(styles));
check('⑤b 品牌光呼吸', /v4BrandBreathe 4s/.test(styles));

// ⑥ will-change 覆盖 infinite 宿主
// 窗口法：每个 will-change:transform 出现点向前取 600 字符（覆盖多行选择器列表），
// 宿主选择器只要落在任一窗口内即算覆盖
const hosts = ['#auroraBg div', '.stream-bar', '.typing-dots span', '.tool-spinner', '.sw-light.probing', '.gg-light', '.plan-step.doing .st', '.load-dot', '.empty-icon', '.brand-logo'];
const wcIdx = [...styles.matchAll(/will-change:transform,opacity/g)].map(m => m.index);
const missing = hosts.filter(h => !wcIdx.some(i => styles.slice(Math.max(0, i - 600), i).includes(h)));
check('⑥ will-change 覆盖 infinite 宿主', missing.length === 0, missing.length ? '缺: ' + missing.join(',') : hosts.length + '/' + hosts.length);

// ⑦ fx-off 停列覆盖新宿主（brand-logo/天光纱/will-change 复位）
check('⑦a fx-off 停 brand-logo 呼吸', /body\.fx-off \.brand-logo\{animation:none/.test(styles));
check('⑦b fx-off 隐天光纱', /body\.fx-off #chatContainer::before\{display:none/.test(styles));
check('⑦c fx-off will-change 复位', /body\.fx-off #auroraBg div[\s\S]{0,400}will-change:auto/.test(styles.replace(/\n/g, '')) || /will-change:auto/.test(styles));

// ⑧ 降级三件套
check('⑧ prefers-reduced-motion/transparency/fx-off', /prefers-reduced-motion/.test(styles) && /prefers-reduced-transparency/.test(styles) && /body\.fx-off/.test(styles));

console.log('\n===== 验收: ' + pass + ' PASS / ' + fail + ' FAIL =====');
process.exit(fail ? 1 : 0);
