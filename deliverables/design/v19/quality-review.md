# 质量审查报告 —— Harbor v1.9.0 新界面原型集

> 审查官：严过审（critique-reviewer）｜日期：2026-10-23｜原文归档（未经主理人改动）
> 评审对象：deliverables/design/v19/prototypes/ 6 个 HTML（plan-intent-preview / checkpoint-dialog / browser-driver-panel / grant-budget / macos-adaptation / index）
> 评审基准：token-upgrade-plan.md（彩格调）+ frontend/index.template.html（v4 既有设计语言）+ master-plan-v19 §4 M2.3-2.8/M5/M6.10-6.12

## 一、5 维评分表

| 维度 | 评分 | 一句依据 |
|------|------|----------|
| 设计哲学 | **5/5** | 「授权驱动替代弹窗驱动」范式在每个原型中可验证：计划卡先行三钮链、L2 全 low 自动批准、预算超限升级任务授权而非续弹窗、检查点 inline 卡禁模态叠模态；信任状用 UNTRUSTED 三重编码（琥珀 45° 斜纹边+mono 来源+哈希链）与风险色条落地 |
| 视觉层次 | **5/5** | 五级字阶（display/title/body/caption/micro）严格按 token 使用；机器数据（eta/trace/sha256/预算）一律 mono+tabular-nums 与正文分离；卡内 head→files→steps→scope→prov→ctx→acts 的信息架构与模板 plan-card 范式一致 |
| 执行质量 | **4/5** | 令牌纪律优秀（新令牌 6 文件双主题齐全、MOTION 单一事实源、fx-off/reduced-motion/reduced-transparency 三重降级在位、纯增命名与方案 §2 逐一对应、零外部依赖零 emoji）；扣分点：3 处演示 dwell 内联字面量未收拢、--panel-gap 带 fallback 引用但未定义、2 个评审台文件 --content-w 用 1080 偏离 v4 令牌 920 |
| 特异性 | **5/5** | Harbor 辨识度明确：玻璃+极光+编辑部排印的底，「≈3 步·2 分钟」mono 徽标、3px 风险色条、dashed 边界声明双栏、sha256 审计链节点、mac traffic lights+App Menu+⌘ 双映射——均非通用模板语汇 |
| 克制 | **5/5** | 无 emoji 无廉价渐变（brand-gradient 仅限 logo，且为品牌蓝单色相）；glow 白名单严守两处 hover（批准钮/收回钮，用 --glow 不用 --glow-strong）；UI 动效全部 ≤240ms，无限循环仅环境层且 fx-off 即停 |

**总分：24/25** —— 通过标准为各维 ≥3 且无 P0：**达成**。

## 二、Anti-Slop 检查结果

**P0（必须修复）：0 项 —— 无**
- 紫/彩虹渐变背景：无（极光为 v4 既有语言，青/紫/品牌蓝三斑 radial，非横幅渐变）
- 编造数据/证言：无（审批 3/5、trace/sha256 均为页脚标注的演示示意数据）
- emoji 替代图标：无（grep 全量验证 0 emoji；图标全部内联 SVG；✓/✗ 用 CSS content 与模板 plan-step 同手法）
- 圆角卡+左侧彩条 AI 套路：不构成（.plan-riskbar 为方案 §2.1 规定的语义组件，取最高步骤风险色）
- 手绘 SVG 人物：无；破碎布局/溢出：无（720/960px 断点齐全，坍塌点均有 ellipsis/min-width:0 保护）
- 对比度 WCAG AA：抽验 text-3/text-2/warn/err/untrusted 在亮暗双主题全部 ≥4.5:1（最弱项 dark 模式 #8b909c on #2a2213 ≈ 5.1:1）
- 无响应式：不成立（6 文件均有断点）

**P1（建议修复）：2 项（≤3，达标）**
1. 新令牌「已定义未渲染」缺交付状态标注 → **已闭环**：彩格调已在 token-upgrade-plan.md 追加《v1.9 新令牌渲染状态表》
2. 方案文本与模板实况有 4 处不一致 → **已闭环**：彩格调已出 4 处勘误 + 勘误记录

**P2（可选优化）：11 项**（均不阻断）
1. 演示 dwell 内联字面量未收进 DEMO 对象（checkpoint autoFlow 1400/3000、browser runRound 120、plan replayApprove 120）→ 收拢保持单一事实源自洽
2. plan-intent-preview fx-off 块含 `.brw-pulse` 死选择器（本文件无该组件）→ 删或注释说明
3. grant-budget `.grant-grid` 用 `var(--panel-gap,16px)` 但本文件未定义 → 补 `--panel-gap:16px`（模板 L127 有该令牌，值为 16，fallback 恰好一致，属软引用）
4. macos-adaptation 演示控制条用内联样式而非 .demo-ctl 类（其余 5 文件均为类）→ 统一
5. macos-adaptation/index 的 `--content-w:1080px` 偏离 v4 令牌 920px → 加注释「评审台加宽值，非产品值」
6. 移植对齐：.plan-title 用 --fs-title(13.5px) vs 模板现值 13px；.pill-btn 高 30 vs 模板 32 → 移植时以模板现值为准或同步升档并记录
7. index 页脚「41 DOM id」与契约口径 40（master-plan §9）不符 → 订正
8. checkpoint #cancelLink 为无 href 的 `<a>`，键盘不可聚焦 → 改 `<button type="button">`
9. macos plat-seg 用 role="tab" 但无 tabpanel/aria-controls → 改 role="group"+aria-pressed 或补齐 tab 语义
10. plat-table td 未列 theming 白名单（th 列了）→ 补齐
11. brw-mode-opt/plat-seg-opt 无 hover 态 → 补 primary-soft 配色（与 pill-btn 一致）

## 三、7 项偏离逐项裁决（全部采纳）

| # | 偏离 | 裁决与理由 |
|---|---|---|
| 1 | 暗态 --aurora-bg-opacity：方案 .56 vs 原型保留 .62 | 【采纳】模板现行值即 .62（2026-10-21 夜态沉浸已上调约 25%），原型与产品现状一致优先；方案表述滞后 → 已勘误 |
| 2 | --radius-ctrl 按 Win 6 / mac 8 实现 | 【采纳】mac 控件圆角略大的平台惯例，Win 6 与既有 --radius-sm:6px 对齐 → 已勘误为显式表述 |
| 3 | --scrollbar-w：Win 沿用 10px，mac 0 + hover 显形 8px | 【采纳】方案「12px」无出处（模板 L212 现行 10px 可证），mac 0+8 与 WKWebView 行为一致 → 已勘误 |
| 4 | aurora-5 以 3 可见斑实现（au-1/au-2/au-5） | 【采纳】模板 au-3 品红已退役（display:none），实为 2 可见斑；2 既有+1 品牌蓝=3 斑是最优和解 → 已勘误 |
| 5 | skylight 令牌已定义未渲染 | 【采纳（留待移植绑定）】本集不含聊天区容器原型，强行渲染失真；同族未渲染还有 --bg-deep（原生窗口外圈）/--edge-hi-strong（模态白名单，本集禁模态叠模态）/--untrusted-bg（建议 prov-strip 内芯启用）→ 已入渲染状态表 |
| 6 | 演示 dwell 常量（stepDwell 900/autoDwell 3000/restoreDwell 1200/primDwell 650）非动效令牌 | 【采纳（判定正确）】演示节奏 ≠ UI 动效时长，不进 MOTION 正确；MOTION 读的 8 个令牌全部走 var() 无硬编码。P2-1：另将 3 处内联字面量收拢进 DEMO 对象 |
| 7 | .plan-badge 交叉淡入需 transition 增 opacity 项 | 【采纳（移植提示正确）】模板 L1258 现行 transition 仅 background-color/color；移植时在 index.template.html 追加「,opacity var(--dur-micro-out) var(--ease-out-soft)」，纯增属性不改选择器权重 |

## 四、最终裁决

**通过 / PASS（P0=0，P1=2≤3，五维 24/25 且全部 ≥3）——进入导出。**

移植时需带 3 件备忘：
1. `.plan-badge` 增 opacity 过渡项（纯增属性）
2. 新令牌渲染状态表随交付
3. 演示 dwell 与动效令牌的边界（DEMO 对象 ≠ MOTION）

功能语义完备性核对 master-plan §4 通过——Intent Preview 字段（步骤/eta/风险条/边界声明/累计上下文）齐全、检查点三态+六军规脚注齐全、六原语行齐全、审批预算+超限升级+一键收回齐全、macOS 双映射/overlay 滚动条/双环焦点/mac-badge/switch/traffic lights 齐全；UI 契约纯增立场在原型中保持良好（新类名与方案 §2 命名一一对应）。
