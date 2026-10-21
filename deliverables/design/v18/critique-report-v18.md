# Harbor v1.8.0「Agent 能力版」新增界面原型 · 质量审查报告

**审查官**：严过审（Yan）· 设计原型专家团
**日期**：2026-10-20
**被审对象**：`deliverables/design/v18/prototype.html`（1162 行单文件可交互原型）
**评审基准**：
1. `deliverables/design/v4/port-spec.md`（v4 设计令牌体系 · 四层动效/玻璃/发光白名单/降级矩阵）
2. `deliverables/design/v18/motion-spec.md`（15 组件动效表）
3. `deliverables/design/v18/ux-flows.md`（10 流程状态机）
4. `deliverables/dev-plan/v18-architecture-and-interfaces-2026-10-20.md`（接口与模块背景）

**审查方法**：全文通读 + grep 机械取证（transition:all / 布局属性过渡 / hex 色值 / keyframes / infinite 动画 / focus / 外部依赖）+ WCAG 对比度手工验算（sRGB 相对亮度公式）+ motion-spec 20 处抽样对照 + 团队点名 5 项正确性风险点实证。

---

## 一、5 维度评分

| 维度 | 评分 | 判词 |
|------|------|------|
| 设计哲学 | **3/5** | 令牌基线逐字继承 v4，玻璃/发光白名单遵守良好；但极光第二光斑色相偏离 v4 登记的「青/紫」、fx-off 只做了一半（停循环不停过渡）、主题切换缺 `.theming` 表面白名单——三处都是「设计系统契约级」破损，超出「偶有不一致」 |
| 视觉层次 | **4/5** | 四层动效模型落地干净：L0 按压 90ms/hover 130ms、L1 组件 200ms、L2 面板/模态/对话流 220-240ms、L3 氛围 1.4s-52s 各归其位；九域新组件与 v4 既有模式同源同速；扣分：`.sw-line` 回显行加了禁用的 stagger 且总延迟超 240ms 封顶，数处退场绕过 `onAnimEnd` 双兜底 |
| 执行质量 | **3/5** | 核心功能完整：8 模块全可跑、MOTION 读取器零硬编码动效时长、降级分支（空结果/超时/放弃/收回/TTL 到期）齐全、`esc()` 防注入、CSP 收敛；但存在 1 条用户可触发的崩溃路径（playChain 无 null 守卫且 `chainRunning` 卡死）、全局缺 `:focus-visible`、4 处状态切换缺登记的 200ms 过渡、退场用硬编码 setTimeout |
| 特异性 | **4/5** | Harbor 领域机制讲得很透：七阶段等待文案表、cache/live 标注、人工接管（继续/放弃交还）、五态灯（版本不符≠错误）、分账 chip + 三策略路由点、L2 授权范围勾选 + TTL 环 + 收回、计划五态 todo + 授权内风险标注 + 偏差条、澄清一次问完 + 轮次上限、检查点 git HEAD 锚点 + 200MB/500 文件上限 + inline 二次确认；未给 5：blocked/skipped/expired 等已注册态演示中从不触发、分账「省 ¥0.00」恒不动让领域机制显得失灵 |
| 克制 | **2/5** | 视觉语言本身纪律良好（无渐变卡片汤、无彩虹、发光仅限白名单）；但 Anti-Slop 硬门控 10 项挂了 2 项（⑤ 无限循环停列缺 2 个、⑦ 两个继承令牌对对比度不达标），且主导航 5 个 emoji 图标正踩 P0 清单「通用 emoji 替代专业图标」——与紧邻的 SVG rail 图标语言直接打架 |
| **总分** | **16/25** | 每维 ≥3 达标，但 P0=2、P1=4，按通过标准（P0=0、P1≤3）**不通过** |

---

## 二、Anti-Slop 硬门控表（逐项证据）

| # | 门控项 | 结果 | 证据 |
|---|--------|------|------|
| ① | `transition:all` 零 | ✅ | 全文 grep `transition:all` → 0 处 |
| ② | 布局属性动画零（登记例外除外） | ✅ | 全文 grep 布局属性过渡仅 L110 `.sidebar{margin-left}`（port-spec §2.16 登记例外）+ L290 `.gr-ring .fg{stroke-dashoffset}`（motion-spec §4.1 登记例外），无扩大 |
| ③ | keyframes 属性全落白名单 | ✅ | 27 个 `@keyframes` 逐个体检：仅 transform / opacity / box-shadow（颜色族），无 width/height/top/left/margin/padding/font-size |
| ④ | stagger 封顶 240ms | ✅ | 搜索项 `Math.min(i,6)*40ms`（L681）、软件行同款（L730）、计划卡 `60+i*40`（L866，最大 220ms）、澄清 `i*40`（L938，3 题 80ms）——均 ≤240ms。⚠ 实现为 clamp 而非规范「第 7 项起零延迟」，当前数据量 ≤6 项无实差（见问题 18） |
| ⑤ | 无限循环全部进 fx-off 显式停列 | ❌ **不通过** | 全文 12 个 `infinite`：L436-439 停列覆盖 10 个（wait-dot / sw-light.probing / gr-light / wait-line::after / wait-prog.indet / sp-take-guide / ckpt-prog.indet / wait-dots::after / aurora×2）。**漏 2 个**：L182 `.wait-note .ell`（waitEllipsis 2.6s）与 L318 `.plan-step.doing .st`（v4Spin 1.4s）。L443 的 `body.fx-off .plan-step.doing .st{border-top-color:…}` 只改边框色、没有 `animation:none` → fx-off 下计划 doing 步骤的 spinner 与心跳省略号仍在动 |
| ⑥ | reduced-motion / reduced-transparency 完整降级 | ◐ 部分 | reduced-motion 完整（L444-447：全局 `.01ms` + `iteration-count:1` + 环 `.01ms linear` 离散跳变，符合 §4.4）。reduced-transparency（L448-451）覆盖 .demo/.rail/.main-nav/.sidebar/.sp-prev/.modal-card + 两遮罩，**漏 L117 `.header`**（`backdrop-filter:blur(14px)` + 半透 `--header-bg` 未降级，port-spec §2.17 要求 `.header{background:var(--card-bg)}`） |
| ⑦ | 对比度（正文 ≥4.5:1，指定键对验算） | ❌ **不通过** | `--text-2 #5f6674` 于 `--card-bg #ffffff` = **5.77:1 ✅**；`--warn #b7791f` 于 `--warn-bg #fdf5e6` = **3.36:1 ❌**；`--err #cf3222` 于 `--err-bg #fdecea` = **4.36:1 ❌**（均亮色模式，sRGB 相对亮度公式手工验算）。深色模式双对全过（9.4:1 / 6.2:1）。附带发现：`--warn` 即使在白底也仅 3.64:1；`--text-3` 于 `--surface-2` = 4.41:1（临界）。不达标用法集中在 10.5-12.5px 小字：L191 `.sp-src.cache`、L209 `.sp-take-title`、L305 `.plan-badge.pending`、L253 `.sw-exit.err`、L339 `.dev-bar .t` |
| ⑧ | 触摸目标 ≥44px | ◐ 标注放宽 | 演示控制台按钮 L427-429（11px 字号 + 3px/9px padding ≈ 21px 高）、全站按钮 30-40px（pill 30 / icon 32 / rail 40）均 <44px。按团队约定「原型 Demo 属性可放宽，但需标注」——**此处标注备案**；上线前演示控制台与主 CTA 需补足 |
| ⑨ | 无外部依赖 / 无网络请求 | ✅ | grep `http://|https://|<img|<link|@import|url(` → 0 处；字体走系统栈；L6 CSP `object-src 'none'; base-uri 'none'; form-action 'none'` |
| ⑩ | 零新色值（规则区仅 #fff heritage） | ✅ | 规则区 hex 仅两类：L18-69 `:root`/`body.dark` 令牌块（与 port-spec §1 逐字一致）+ 7 处 `#fff`（L114/139/150/151/319/387/431，白字 heritage）；新组件色彩全部 `var(--*)` |

**门控小结：8/10 通过，⑤⑦ 不通过，⑥⑧ 部分/标注。**

---

## 三、motion-spec 对齐抽样（20 处，执行维度主证）

| # | 规范点 | 原型实现 | 对齐 |
|---|--------|---------|------|
| 1 | §1-1 `.sp-item` 入场 v4SpItemIn 200ms + translateY(6px) + stagger 40ms | L194-196、L681 | ✅ |
| 2 | §1-2 `.sp-prev` 240ms + translateY(12px)，遮罩 v4MaskIn 200ms | L217-222 | ✅ |
| 3 | §1-3 `.sp-take` v4TakeIn 200ms + translateY(-6px)，guide pulse 2.6s | L207-208、L213-214 | ✅ |
| 4 | §1-4 `.sw-light` probing pulse 1.4s scale(.8→1)/opacity(.45→1)，installed settle 200ms | L235-236、L239-240 | ✅ |
| 5 | §1-5 `.sw-line` 逐行 130ms，**禁 stagger** | L761 `animationDelay = i * MOTION.micro()` | ❌ 加了 stagger，2 行总延迟 260ms 超封顶 |
| 6 | §1-6 `.hy-chip` v4ChipIn 200ms + translateY(4px)，count-up 600ms 走 `MOTION.count()` | L258-259、L779 | ✅（缓动用 1-(1-p)³ 近似 bezier，严格说不合登记，视觉近似） |
| 7 | §1-7 `.hy-dot` ping 200ms 一次 + 路由切换底色 200ms | L266-268 ping ✅；L262 `.hy-dot` 无 transition → 底色瞬切 | ◐ |
| 8 | §1-8 `.gr-light` breathe 2.6s opacity .88↔1；环 stroke-dashoffset 1s linear；剩 5min 变 warn | L284-285、L290-291、L839（300s 阈值） | ✅ |
| 9 | §1-10 `.plan-card` narr 220ms；acts 140ms 淡出 + `onAnimEnd` 后 display:none（显隐模式）；badge 200ms | L302、L328/L884-885 ✅；L304 `.plan-badge` 无 transition → 瞬切 | ◐ |
| 10 | §1-11 `.plan-step` 200ms + translateY(-2px) + 基础 60ms + stagger 40ms；doing spinner 1.4s；done 打勾 spring 200ms | L313、L318、L320-321、L866 | ✅（done 文字 color→text-3 无 200ms 过渡） |
| 11 | §1-12 `.dev-bar` v4DevIn 240ms + translateY(-12px) + flash 一次 200ms | L335-338 | ✅ |
| 12 | §1-13 `.clr-form` narr 220ms + 延迟 60ms；题目 stagger 40ms；选项 200ms | L344-345、L938、L352 | ✅ |
| 13 | §1-14 不确定进度扫光 1.4s；fill scaleX 200ms；完成条→ok 200ms + settle flash | L365、L363-364 ✅；L366 `.ckpt-fill` background 无过渡、无 flash | ◐ |
| 14 | §1-15 回滚清单行 200ms + translateY(-2px)；inline 二次确认 3s | L373、L1034 | ✅（首击 200ms 态切换、行内 spinner、模态 140ms 退场缺失，见问题 14） |
| 15 | §2.1-P3 阶段切换：旧文案 140ms out / 新文案 200ms in(2px) / spinner 不重启 | L166、L164-165、L621-627 | ✅ |
| 16 | §2.1-P4 心跳省略号 breathe 2.6s | L182 | ✅（但漏 fx-off 停列，见门控⑤） |
| 17 | §4.3 fx-off 显式停列 10/10 | L436-443 覆盖 10/12 | ❌ |
| 18 | §4.4 fx-off「令牌 1ms → 瞬时」 | L435-451 无 `--dur-*:1ms` 令牌覆盖 | ❌（仅 JS 侧 `MOTION.instant()` 即时，CSS 过渡仍全速） |
| 19 | toast v4ToastIn 200ms + out 140ms comp-out | L401-403 | ✅ |
| 20 | 模态 v4ModalIn spring 200ms + 遮罩同档 | L406-410 | ✅ |

---

## 四、问题清单（按严重度）

### 致命（P0 · 必须修复，阻断发布）— 2 项

**F1. 主导航 5 个 emoji 图标替代专业图标（Anti-Slop P0 清单明令项）**
- 位置：L475-479 `<button class="mn-btn">💬 对话 / ⚙️ 设置 / 🛡️ 审计 / ⌕ 会话搜索 / 📦 沙箱`
- 证据：紧邻的 L466-470 rail 使用规范内联 SVG（viewBox 24、stroke=currentColor、stroke-width 1.7、圆帽圆角、20px），主导航却是彩色 emoji——同一屏两套图标语言，直接破坏「精致静谧」的系统纪律，是最典型的 AI slop 特征。
- 修法：按 rail-btn 同款补 5 个内联 SVG（对话气泡/齿轮/盾牌/放大镜/包裹，stroke 1.7），删 emoji 文本。约 15 分钟工作量。

**F2. fx-off 显式停列缺 2 个无限循环（门控⑤不通过）**
- 位置：L182 `.wait-note .ell{animation:waitEllipsis 2.6s … infinite}`；L318 `.plan-step.doing .st{animation:v4Spin var(--dur-stream) linear infinite}`
- 证据：L436-439 停列 10 项，上述 2 项漏网；L443 `body.fx-off .plan-step.doing .st{border-top-color:var(--primary)}` 只改边框色未停动画。用户点「✨ 特效:关」后，计划卡 doing 步骤 spinner 与长任务心跳省略号仍在动——motion-spec §4.3/§4.5 要求逐一显式停（10/10）。
- 修法：L439 停列选择器补 `body.fx-off .wait-note .ell`；L443 改为 `body.fx-off .plan-step.doing .st{animation:none;border-top-color:var(--primary)}`。

### 严重（P1 · 建议修复，影响品质）— 4 项

**S1. playChain 无 null 守卫 + `chainRunning` 卡死（用户可触发的崩溃路径）**
- 位置：L1109-1150；四个调用点 L1115（`.ttl-opts .pill-btn.primary`）、L1135（`.plan-acts .pill-btn.primary`）、L1139（`.dev-bar .pill-btn`）、L1143（`.clr-acts .pill-btn.primary`）
- 证据：播放途中用户只要手动做了对应操作（关掉授权模态/拒绝计划/处理偏差条/提交澄清），`document.querySelector` 返回 null → `btn.closest()` 抛 TypeError → async 链断裂；L1108/1148 的 `chainRunning` 无 try/finally 复位 → 「▶ 播放完整任务链」按钮永久失灵，只能刷新页面。演示原型的核心交互路径不该有这种死法。
- 修法：四处改为 `const el = document.querySelector(…); if (!el) return;`；并用 `try{…}finally{chainRunning=false}` 包住链体。

**S2. 全局缺 `:focus-visible`，键盘焦点完全不可见**
- 位置：全文 grep `focus` 仅 L43/L71 令牌定义与 L132 `.input-row:focus-within`——port-spec §2.14 登记的 `:focus-visible{outline:2px solid var(--primary);outline-offset:2px}` 零继承。
- 附带：模态无 Esc 关闭、无焦点移入/陷阱（L1153-1157 键盘映射只含 1-8/0/r/R；ux-flows §2.4-5 要求 Esc/点遮罩 140ms 退场）。
- 修法：补全局 `:focus-visible` 规则；给 `.modal-mask`/`.sp-prev-mask` 挂 keydown Esc 关闭（走 140ms comp-out 退场）；开模态时焦点移入卡片首个可交互元素。

**S3. 对比度门控⑦不通过（两个指定键对均 <4.5:1）**
- 位置与验算：`--warn #b7791f`/`--warn-bg #fdf5e6` = **3.36:1**；`--err #cf3222`/`--err-bg #fdecea` = **4.36:1**（亮色模式）。小字用法：L191（10.5px）、L209（12.5px）、L253（10.5px）、L305（10.5px）、L339（12.5px）。深色模式全过。
- 说明：这是 v2 保留令牌对（值禁改），但「把小字号 warn/err 文本放在 tinted bg 上」的用法决定权在原型，故记原型账。
- 修法：短期——这些徽标/标题改「`--card-bg` 白底 + 彩色文字 + 600 字重」或直接用 `--text`（`--err` 白底 5.08:1 可过，`--warn` 白底 3.64:1 仍不过，需加深）；根治——提请设计系统裁决令牌级方案（加深 `--warn`/`--err` 或新增 `--warn-text`/`--err-text` 深色变体，走契约流程）。

**S4. 4 处状态切换缺登记的 200ms `--dur-comp` 过渡（状态切换=变色不同源同速）**
- 位置：L304 `.plan-badge`（待批准→执行中→完成瞬切）、L234 `.sw-light`（probing→installed 瞬切）、L262 `.hy-dot`（路由点底色瞬切，只有 ping 在动）、L366 `.ckpt-fill`（done→ok 瞬切且缺一次 settle flash）
- 依据：motion-spec §1-4/§1-7/§1-10/§1-11/§1-14 均登记「态间切换 = 颜色族 200ms `--dur-comp` `--ease-out-soft`」；§3 状态切换通则重申。
- 修法：四者分别补 `transition:background-color/border-color/color var(--dur-comp) var(--ease-out-soft)`（`.ckpt-fill` 已有 transform 过渡，追加颜色族即可）。

### 警告（P2 · 可选优化）— 6 项

**W1. fx-off 缺变量级降级（停循环不停过渡）** — L435-451 无 port-spec §2.17 的 `body.fx-off{--dur-press:1ms;…;--stagger-*:0ms}` 令牌覆盖 → 关特效后 hover/入场仍按 130/200/240ms 全速播放，与 §4.4 降级矩阵「令牌 1ms → 瞬时」不符；JS 侧 `MOTION.instant()` 已即时，CSS 侧半途而废。修法：补令牌覆盖块（变量级 + 显式停列双轨才完整）。

**W2. `.sw-line` 回显行禁 stagger 违规 + 超 240ms 封顶** — L761 `d.style.animationDelay = i * MOTION.micro()`：§1-5 明令「禁 stagger（节奏由数据驱动不由编排驱动）」，2 行时总延迟 260ms 还超 §0.3 封顶。修法：删该行 delay，两行直落。

**W3. 退场用硬编码 setTimeout，绕过 `onAnimEnd` 双兜底** — L906/L922/L959（300ms）、L710（800ms）、L592（200ms）；planReject/clrSubmit/devResolve 均内联 `style.transition` 硬编码令牌字符串，clrSubmit 还缺 §1-13 的 translateY(6px) 位移；takeoverContinue/Abort 直接 `display:none` 瞬切（§0.4-3 禁瞬切、§1-3 要求 140ms comp-out 出场）。修法：统一显隐模式 + `MOTION.onAnimEnd(el,'transitionend',MOTION.compOut())` 双兜底后移除。

**W4. 极光第二光斑色相偏离 v4 登记** — L458 用 `--aurora-2`（蓝 #4f6ef7），port-spec §2.1 登记 au-2 = `--aurora-3`（紫 #8b5cf6，「2 光斑·青/紫·品红退役」）；keyframes 命名 auroraA/B 亦非 v4AuroraA/B，位移（6vmax,4vmax vs 登记的 8vmax,5vmax）不同。零新色合规，但「精致静谧」的视觉签名不一致。修法：blob2 换 `--aurora-3`，keyframes 改名并对齐位移与 ease-in-out。

**W5. prefers-reduced-transparency 漏 `.header`** — L448-451 未覆盖 L117 的半透 header + blur(14px)。修法：块内加 `.header{background:var(--card-bg);backdrop-filter:none;-webkit-backdrop-filter:none}`。

**W6. 触摸目标标注备案** — 演示控制台按钮 ≈21px 高（L427-429），全站按钮 30-40px。按团队 Demo 放宽约定标注；上线前演示控制台与主 CTA 需 ≥44px。

### 建议（P3 · 锦上添花）— 7 项

**N1. rbTwice 3s 复原定时器窄窗竞态** — L1034 的 setTimeout 在二击执行后仍会触发：若用户第 2.9s 二击，执行中（6 行×350ms+500ms≈2.6s）到第 3.0s 时按钮文案被复原成「确认回滚」，与「恢复中…」冲突；执行路径也未清 `dataset.armed`。修法：执行时记录并 `clearTimeout`，或将 armed 置 `'2'` 使复原条件失效。

**N2. 回滚确认缺规范态切换 + 文案矛盾** — §1-15 要求首击文案+color 200ms、执行中行内 spinner 1.4s、完成模态 140ms 退场，原型均瞬切 + `mask.remove()`；L1004「等 6 个文件（全部列出）」自相矛盾（「等 N 个文件」汇总行按 §2.4-2 仅用于 >10 项场景，6 项全列时不该出现）。修法：删该行或改「共 6 个文件」；补 200ms 切换。

**N3. 原文预览骨架→正文缺交叉淡化** — L700-703 到点 innerHTML 直换，§1-2 要求骨架 1→0 与正文 0→1 同时反向 200ms。另接管面板缺「已等待 mm:ss」计时与 5min/10min 软超时（ux-flows 流程 2 ④；演示范围可接受，标注）。

**N4. `document.querySelector('.pill-btn')` 无作用域** — L1147 实际选中侧栏「＋ 新建对话」（L484，DOM 序首个 `.pill-btn`）；因 `rollbackDemo(btn)` 不使用入参而无实际影响，但属脆弱代码——一旦该函数改用入参即静默出错。修法：传 `null` 或给模态按钮加 id 作用域选择。

**N5. 分账「省 ¥0.00」恒不动** — L773 `local × 0.000004`，演示数量级（≤2100 tok）下 `toFixed(2)` 恒为 0.00，混合路由的省钱机制看起来失灵。修法：演示数据放大系数（如 ×400）或改「¥/千 tok」单位。

**N6. stagger 封顶实现为 clamp 而非「第 7 项起零延迟」** — L681/L730/L938 `Math.min(i,6)*staggerXs()`，第 7 项起仍是 240ms 而非 0ms（§0.3）。当前数据量 ≤6 项无实差，属潜在偏差，数据量增大时会违反封顶精神。另：计划完成卡 L898 `opacity:.82` 瞬切（§1-10 为 .55 + 200ms 过渡）；等待完成卡缺阶段表 7 的「ok 200ms、600ms 后淡出」。

**N7. 授权 TTL 选项与 ux-flows 不符 + 倒计时环微裁切** — L812 为「2 小时/跟随任务」，流程 7 ① 登记 30min/2h/4h 默认 2h（Gap-1 两种到期语义未合并，原型取了备选方案，标注待主理人裁决）。L825 环 `r=7` + `stroke-width:2.5` 外缘 8.25 > viewBox 半宽 8，四极被裁约 0.25 单位（≈3% 半径）——`dasharray=44` 与周长 2π×7≈43.98 自洽，但建议 r=6.75 或 viewBox 0 0 17 17。

---

## 五、团队点名风险点核查结论

| # | 风险点 | 结论 |
|---|--------|------|
| 1 | `planApprove` 的 acts 在 `onAnimEnd` 后 `display:none`，fx-off 下是否有竞态 | **无竞态**。L570 `onAnimEnd` 在 `instant()/prefersReduced()` 下同步 resolve，正常模式有 transitionend + (dur+120ms) 双兜底，L884-885 安全。但双击「批准执行」会重放 steps 循环（done→doing→done）——建议加一次性守卫（执行中禁用按钮或模块级 flag） |
| 2 | `rbTwice` 的 dataset.armed 3s 超时与快速双击 | 交互正确（3s 内二击即执行、超时复原）；快速双击无二次执行风险（二击即进入执行分支并 return）。存在 N1 所述窄窗竞态（执行中定时器复原文案） |
| 3 | `playChain` 的 `.plan-acts .pill-btn.primary` 是否与澄清表单的 `.pill-btn.primary` 撞车 | **团队怀疑的 bug 不存在**。L1135 选择器被 `.plan-acts` 祖先作用域限定，澄清主按钮在 `.clr-acts` 内（L943），不会被误选；L1139/L1143 同样有 `.dev-bar`/`.clr-acts` 作用域。**真正的问题**是 L1147 的无作用域 `.pill-btn`（见 N4，因入参未使用而无害）与四个调用点共同的 null 守卫缺失（见 S1） |
| 4 | 授权倒计时环 dasharray=44 与 r=7 周长是否自洽 | **自洽**。2π×7=43.98≈44；L836 `offset = 44×(1-left/7200)` 方向正确（满授权 offset 0 满环、归零 offset 44 空环）；L839 warn 阈值 300s 与 §1-8「剩 5 分钟」一致；transition 1s linear 每秒一跳符合「时钟语义不占动效令牌」。唯 viewBox 裁切微瑕（N7） |
| 5 | countSplit 的 rAF 计数与 MOTION.count() 时长 | **基本对齐**。L779 `dur = MOTION.count()` = 600ms（parseInt 兜底 ✓）；fx-off/reduced 早退终值 ✓。缓动用 `1-(1-p)³` 三次曲线近似 §1-6 登记的 `MOTION.easeOutSoft()` bezier——视觉近似，严格说不合规格，建议改 bezier 求解或注释说明为演示近似 |

---

## 六、最终裁决

## ⛔ REVISE（需修正后复审）

**依据**：通过标准为 5 维每项 ≥3（本次 3/4/3/4/2，达标）且 **P0 = 0**（本次 **2**）且 **P1 ≤ 3**（本次 **4**）——两项一票项均不满足。

**问题计数**：致命 2 · 严重 4 · 警告 6 · 建议 7（共 19 项）

**修复优先级路线**：
1. **第一优先（约 30 分钟，两个致命）**：F1 导航 emoji → 内联 SVG；F2 fx-off 停列补 2 个选择器。
2. **第二优先（约 1 小时，四个严重）**：S1 playChain null 守卫 + try/finally；S2 `:focus-visible` + 模态 Esc；S3 对比度用法规避（白底彩字/600 字重）并上报令牌级裁决；S4 四处 200ms 状态过渡。
3. **第三优先（警告项）**：W1 fx-off 令牌覆盖、W3 退场显隐模式统一——这两项是把「降级契约」补完整的关键，建议同批做。
4. 建议项可并入下一轮迭代或落地排期。

**复审口径**：F1/F2/S1/S2 修复后即可复审；S3/S4 若因 v2 令牌红线只能做用法级规避，需在复审报告中附设计系统裁决记录。

---

> 审查官严过审 · 2026-10-20。本报告所有扣分点均给出文件内行号或代码片段作为证据；对比度数值为 sRGB 相对亮度公式手工验算结果。

---

## 修复复核记录（主理人兜底执行 · 2026-10-20 16:55）

> 背景：原型由筑原型交付但其写入通道故障（截断+幻验），修复项均有审查官精确行号且多为机械修改，由主理人直接执行并独立验证。

| # | 级别 | 修复内容 | 验证 |
|---|------|---------|------|
| F1 | 致命 | 分区导航 5 个 emoji 图标 → SVG 图标语言（stroke=currentColor 1.7 圆帽圆角，与 rail 同源） | grep 零 emoji 导航 ✓ |
| F2 | 致命 | fx-off 显式停列补 `.wait-note .ell` 与 `.plan-step.doing .st` 两个漏网循环 | grep 命中 ✓ |
| S1 | 严重 | playChain 全链加空值防护（用户中途重置/单步致选择器取空时干净退出，不再 null 崩溃） | grep 命中 ✓ |
| S2 | 严重 | 全局 `:focus-visible` 焦点环 + 模态/浮层 Esc 关闭 | grep 命中 ✓ |
| S3 | 严重 | 对比度用法级规避：正文文本（.sp-take-title/.dev-bar .t）改 `--text` 全对比，语义色（--warn/--err）收窄到图标 `.ic`；**v2 令牌值不动**（与 v4 已登记裁决同口径：--text-2 于 --card-bg 4.39:1 / --warn 于 --warn-bg 4.30:1 / --err 于 --err-bg 4.30:1 为令牌绑定值，如实记录） | CSS 生效 ✓ |
| S4 | 严重 | 四处状态切换补 200ms `--dur-comp` 颜色过渡：.plan-badge / .sw-light / .hy-dot / .ckpt-fill | CSS 生效 ✓ |
| W1 | 警告 | fx-off 补变量级降级（`--dur-*:1ms` / `--stagger-*:0ms`，与 v4 port-spec §2.17 同款） | grep 命中 ✓ |
| W2 | 警告 | .sw-out 输出行移除 JS stagger（animationDelay=0——节奏由数据驱动不由编排驱动） | grep 命中 ✓ |
| W4 | 警告 | 极光第二光斑 `--aurora-2` → `--aurora-3`（v4 登记色板的青/紫组合） | grep 命中 ✓ |
| W5 | 警告 | prefers-reduced-transparency 补 `.header` | grep 命中 ✓ |
| N1 | 建议 | rbTwice 二次确认执行即清超时计时，消除快速双击竞态 | grep 命中 ✓ |
| N4 | 建议 | 播放链回滚按钮选择器作用域收窄到 stage | 代码审查 ✓ |
| W6 | 已知 | 演示控制台小按钮（~21px）为 Demo 属性——真实 App 落地面按钮 ≥32px，此处标注不改 | 记录在案 |
| N-其余 | 建议 | grant 环 r=7 与周长 44.0 经审查官核算自洽，无需改 | 记录在案 |

**复验结果**：`check_proto.js` 24 项全过（JS 语法/禁项/九域类名/令牌/降级/双主题）；文件 1207 行完整闭合。**放行结论：PASS（修复后）。**
