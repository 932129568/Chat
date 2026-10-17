# GLM-Chat UI 重构 v3 · 质量审查报告（Phase 4）

> 审查人：质量审查官 **严过审（Yan）**
> 审查对象：Phase 3 产出的 v3 原型（`frontend/` 源码 + 构建产物 `glm-chat.html` + `deliverables/design/v3/` 预览页）
> 审查方式：契约脚本独立重跑 + 源码逐项抽查 + Playwright(Edge) 实机走查截图 + WCAG 对比度独立实测
> 审查日期：2026-10-15

---

## 0. 结论速览

| 门控 | 结果 |
|------|------|
| 契约复核（check_contract.py + 独立抽查） | ✅ 全 PASS |
| pytest 回归 | ✅ 31 passed |
| Anti-Slop 门控（02-design-system §E.1 + §E.2 逐条） | ✅ PASS（无 P0） |
| 5 维评分 | 21/25，每维 ≥4 ✅ |
| **最终判定** | **✅ PASS（附 1 项 P1 修复建议 + 5 项 P2）** |

---

## 1. 契约复核结果（独立重跑，未信任 Phase 3 自验）

### 1.1 check_contract.py（项目 venv 实跑）

```
[DOM id] 40/40          ← 静态模板口径；ctxMenu 由 JS 动态创建（脚本 L29 注明排除）
[onclick 处理函数] 13/13
[callApi 后端方法] 43/43
[CSS 类] 39/39
[CSS 变量] 21/21
[本地依赖库] 4 个引用，0 个缺失（flate/marked.min/purify.min/highlight.min 全 OK）
[构建产物] glm-chat.html 存在 (182079 字节)
结果: PASS — 五大契约全部保住
```

> 口径说明：需求 §5.3 标称 41 个 id，脚本按 40 静态 + 1 动态（ctxMenu）统计，两者一致，无遗漏。

### 1.2 pytest

```
31 passed in 16.48s
```

### 1.3 独立源码抽查（脚本之外逐项人工核验）

| 项 | 结果 | 证据 |
|----|------|------|
| 41 个 DOM id 全在 | ✅ 40 个在 `index.template.html`（id="..." 精确匹配逐一过），ctxMenu 由 `105-context-menu.js` 动态创建 | grep 全量比对 |
| 13 个 onclick 函数定义存在且签名不变 | ✅ 逐一 grep `function <name>(` 全命中；模板内联 onclick 23 处（原 13 组 + v3 新增 switchPanel/setTrendMetric/renderAnalytics，均已在 JS 定义） | 模板 L578-749 |
| v2 CSS 变量一个没删 | ✅ 21 个 v2 变量在 `:root` 与 `body.dark` 各出现 1 次（grep 计数均 =2） | 模板 L20-39 / L77-89 |
| **R1** select 全部 DOM 常驻 | ✅ 7 个 select（modelSelect/reasoningEffort/shotQuality/saverLevel/searchEngine/wsSel/toolMode）全部静态写在模板内；面板只用 `.panel.on` class 显隐（L298-299）；`initCustomSelect` 在 boot 一次性遍历（110-boot.js L14）+ `CS.syncAll()`（L127）；实机截图确认隐藏面板内的下拉已被正确包装渲染 | 模板 L635/643/657/664/703/836/850 |
| **R3** #tokenStat 未被图表复用 | ✅ 78-analytics.js 全文无 `tokenStat` 引用（仅注释声明不碰）；图表容器为全新 id（chartTrend/toolBars/toolRing/toolMs/statCards）；`#tokenStat` 仍在侧栏底部（模板 L609） | 78-analytics.js L5 |
| **R4** emptyState 重建结构未变 | ✅ `85-session-mgmt.js` L22-26 与契约逐字节一致 | 85-session-mgmt.js L22-26 |
| **R5** .sidebar.collapsed 折叠语义保留 | ✅ `.sidebar.collapsed{margin-left:calc(-1 * var(--sidebar-w));}`（模板 L183），`--sidebar-w:264px` 未动，`--rail-w:60px` 为独立常驻栏不参与折叠 | 模板 L177-183 |
| **R7** 层叠顺序 | ✅ `#auroraBg` fixed + z-index:-1（L127）；`#streamBar` z-index:10000（L143）；玻璃面板 z-index 10-20 居中 | 模板 L127/L143 |
| glm-chat.html 为构建产物非手改 | ✅ 连续两次 `node frontend/build.js` 重建，`cmp` 字节级完全一致（REPRODUCIBLE）；且用最新源码重建后重新生成预览页成功 | cmp OK |

**契约复核：全 PASS。**

---

## 2. 视觉走查（Playwright / Edge 实机）

截图留档：`deliverables/design/v3/shots/`（1440×900 @1.5x）

| 截图 | 走查点 | 结果 |
|------|--------|------|
| `light-chat.png` / `dark-chat.png` | 对话面板默认态 | ✅ 工具三态卡（执行中 spinner / 成功 / 失败红）状态一眼可辨；极光渗透极克制；等宽数据对齐 |
| `light-analytics.png` / `dark-analytics.png` | 分析面板 | ✅ 4 张汇总卡 + 趋势图（真实聚合形状：首会话峰值后回落）+ 工具条形图 + 89% 成功率环形 + 耗时条全部渲染；双主题坐标轴/图例可读 |
| `light-workspace.png` | 工作区面板 | ✅ 自定义下拉在 display:none 面板中被正确初始化（R1 实证）；⚠️ 发现 P1 排版 bug（见 §5） |
| `light-settings.png` | 设置浮层 | ✅ 5 组 set-block + 新增「外观与特效」fxToggle 块 |
| `light-sessions.png` | 会话面板 | ✅ 列表渲染、选中态左侧竖条 |
| `light-tooltip.png` | rail tooltip | ✅ hover 弹出「分析 · 成本与工具统计」，玻璃底深字 |
| 行为脚本（无截图） | 特效开关 | ✅ `#fxToggle` 取消勾选 → `body.fx-off` 生效 → 实测极光 `animation:none`、扫光 `display:none`、工具卡脉冲停止；`initFx()` 从 `localStorage['glm_fx']` 恢复（110-boot.js L15） |
| 行为脚本 | `prefers-reduced-motion: reduce` | ✅ 模拟后实测：极光 `animation:none`、工具卡扫光 `display:none`、stream-bar 去发光——与 §D.1 降级矩阵一致 |

**对比度独立实测**（按 WCAG 2.1 相对亮度公式，Python 手算）：

- **实现实际模型**（极光被不透明 `--glass-fallback` 与 88% `--main-veil` 阻隔，面板内文字几乎不受极光影响）：浅色正文 ≈15.9:1、次级 ≈5.3:1；深色正文 ≈11.8:1、次级 ≈4.6:1 —— **全部 ≥4.5 ✅**
- **极限压力模型**（假设极光青 `#22d3ee` 以满 12% 直接叠在文字底上，比实际渲染严苛得多）：浅 text 16.1 / text-2 5.15 / err 4.54 全过；**深色 text-2 = 4.27:1**，略低于 4.5（见 P2-1）。
- 结论：实际渲染达标；B.7 宣称的 4.9:1 在极限压力模型下不成立，建议修正文档口径（P2-1）。

---

## 3. 五维评分

| 维度 | 评分 | 说明 |
|------|:---:|------|
| **设计哲学** | **5/5** | 「氛围可以炫，内容必须稳」被字面级执行：极光锁在 z-index:-1 + 88% veil 之后；玻璃必有 `linear-gradient(var(--glass-bg),var(--glass-bg)),var(--glass-fallback)` 不透明兜底（L174/L308/L468）；三态语义色一字未动（L414-424）；每个视觉决定都能回溯到 02-design-system 的令牌。无 "无主之笔"。 |
| **视觉层次** | **4/5** | rail（7 入口 + tooltip + 选中发光）→ 面板标题 + 一句话说明 → 内容的动线清晰；成本状态经侧栏底部 `#tokenStat` 在**任意面板**常驻可见（符合 §3.2 第 3 条）；数据卡片 → 大图 → 双图的 F 型布局合理。扣 1 分：设置以「浮层」而非「面板」存在（rail 设置按钮无 data-panel、无选中态），导航模型 slightly 混合，新用户可能找不到"设置在哪"的对应关系（P2-4）。 |
| **执行质量** | **4/5** | 动画全部 transform/opacity/dashoffset（无重排属性）；E1-E10 逐条落地且实测降级正确；R1-R8 全部规避；图表空态友好、口径与 60-agent-loop 一致（error/skip 判定 L33-38）；构建可字节级复现。扣 1 分：`.ws-btn` 内联 SVG（display:block）与文字垂直堆叠的排版 bug（P1-1）；make_preview_v3.py mock 会把 `glm_fx` 强制写回 '1'，导致预览页无法演示"特效关"持久化（仅工具链问题，产品代码无此问题，P2-3）。 |
| **特异性** | **4/5** | 「极光玻璃皮肤 × 等宽技术数据 × 三态工具卡 × 前端聚合仪表」的组合有辨识度，不会与通用 AI 落地页混淆；玻璃只用 62-80% 半透 + 兜底，不是烂大街的 full-bleed 磨砂。扣 1 分：玻璃 + 微光 + 极光的语言本身在 2025-26 已属常见范式，特异性主要靠"工具三态卡 + 真数据仪表"两个灵魂组件撑起——好在它们确实是全页最强识别点。 |
| **克制** | **4/5** | 强发光同屏仅选中 rail 项 + 焦点环两处；极光内容区渗透实测远低于 12% 上限；卡片默认无阴影（shadow 只在 tooltip/浮层）；无玻璃叠玻璃（cs-menu 按规范 C.5 用 glass-bg-2 + 兜底）；图表零硬编码、空态不造假。扣 1 分：`85-session-mgmt.js` L76-86 的工具摘要前缀仍是 emoji（📖📂📝⚡📷），与 v3 全 SVG 图标语言不一致（P2-2，v2 遗留非本次引入）。 |

**总分：21/25（全部 ≥3 → 过）**

---

## 4. Anti-Slop 门控（§E.1 + §E.2 逐条）

| 检查项 | 结果 | 证据 |
|--------|:---:|------|
| 全屏彩虹/高饱和渐变铺满内容区 | ✅ 无 | 极光仅 3 个 90px 模糊光晕在 z-index:-1，内容区被 88% veil 压到近不可见 |
| 玻璃叠玻璃 | ✅ 无 | 玻璃只用于 rail/侧栏/卡片/浮层单层；嵌套用 `--surface-2` 或 `--glass-bg-2`+兜底 |
| 动效无节制持续全屏动画 | ✅ 无 | 极光 26s/40s 双周期慢速；`will-change:transform` 仅极光层；特效可关 + reduced-motion 降级实测生效 |
| 纯黑 #000 / 纯白 #fff 大面积对撞 | ✅ 无 | 深 `#101114/#171a21`、浅 `#f6f7f9/#f4f6fb` |
| 圆角 >16px 胶囊卡片堆叠 | ✅ 无 | 最大 `--radius-xl:16px`（仅输入行/空态图标） |
| emoji 作为主要图标语言 | ⚠️ 边缘 | 主 UI（rail/按钮/工具条）全部 1.7px 线性 SVG ✅；但 85-session-mgmt.js L76-86 摘要前缀 emoji 为 v2 遗留 → P2-2，不构成"主要图标语言"，判 PASS 带备注 |
| 每个卡片都带阴影 | ✅ 无 | `.g-card` 默认无阴影；阴影仅 tooltip/cs-menu/ctx-menu/sys-tip |
| 为炫牺牲"一眼看懂" | ✅ 无 | 所有面板一级入口、无隐藏手势；面板标题带一句话说明 |
| 发光滥用 / 彩虹渐变按钮 / 发光当边框 | ✅ 无 | 强发光同屏 ≤2；CTA 只发光不换色；先 1px 实边再叠光 |
| 极光色进入正文 UI | ✅ 无 | 极光四色只在 `#auroraBg`、图表系列色、选中光晕 |
| 图表假数据撑场面 | ✅ 无 | 78-analytics.js 全部从 `sessions/messages` 聚合（L16-53）；预览 mock 数据仅存在于标注"仅视觉走查"的预览页，不参与打包 |
| 动效 >280ms 用于常规交互 | ✅ 无 | 面板 200ms / hover 260ms / 只有图表绘制 900ms（属数据叙事，合理） |
| 编造统计/虚假证言 | ✅ 无 | — |
| 手绘 SVG 人物插图 | ✅ 无 | — |
| 文本对比度不达标（WCAG AA） | ✅ 实测通过 | 见 §2 实测 |
| 明显破碎布局/溢出 | ⚠️ 1 处 | `.ws-btn` 图标与文字堆叠（P1-1），非崩溃性但可见 |

**Anti-Slop 门控：PASS（0 条 P0 命中）。**

---

## 5. 问题清单（P0/P1/P2，均带文件:行号与修复建议）

### P0（必须修复，阻断发布）

**无。**

### P1（建议修复，影响品质）— 1 项

- **P1-1 · 工作区「浏览…」按钮图标与文字垂直堆叠**
  - 证据：`frontend/index.template.html` L211-214（`.ws-btn` 无 `display:flex`）+ L478-479（`.ws-btn svg{display:block}`）→ L838 按钮内的 SVG 独占一行、文字被挤到下一行（截图 `shots/light-workspace.png` 可见图标悬在文字上方）。
  - 修复建议：`.ws-btn` 补 `display:flex;align-items:center;justify-content:center;gap:5px;`（与 `.ghost-btn` L197-200 同款写法），一行 CSS 修复。

### P2（可选优化）— 5 项

- **P2-1 · B.7 对比度表在极限压力模型下不成立（深色 text-2 = 4.27:1 < 宣称 4.9:1）**
  - 证据：独立按 WCAG 公式复算——若极光青以满 12% 直接叠加，`#8b909c` 对复合底 ≈ 4.27:1。实际实现中极光被 `--glass-fallback`（不透明）与 `--main-veil`（88%）双重阻隔，实测真实渲染 ≥4.6:1 达标；此问题属**文档口径**而非实现缺陷。
  - 修复建议：① `02-design-system.md` B.7 注明测量口径（"极光经 veil/fallback 阻隔后的实际渗透"）；② 顺手把深色 `--text-2` 提亮一档（如 `#949aa8`）或深色 `--aurora-bg-opacity` 由 `.60` 降至 `.50`（`index.template.html` L100），让极限模型也 ≥4.5。
- **P2-2 · 工具摘要前缀 emoji 与 v3 图标语言不一致**
  - 证据：`frontend/src/85-session-mgmt.js` L76-86（`'📖 '+'📂 '+'📝 '+'⚡ '+'📷 '`）。v2 遗留代码，v3 未引入但也未清理。
  - 修复建议：替换为对应线性 SVG（复用模板已有图标）或去掉前缀仅留文字，与三态卡 `tc-dot` 语言统一。
- **P2-3 · 预览脚本 mock 覆盖 `glm_fx`，无法演示特效关持久化**
  - 证据：`deliverables/design/make_preview_v3.py` MOCK 段 `localStorage.setItem('glm_fx','1')`——用户在预览页关特效后刷新会被 mock 强制改回。
  - 修复建议：改为 `localStorage.getItem('glm_fx')===null && localStorage.setItem('glm_fx','1')`（仅首次预置）。产品源码（16-panel-fx.js + 110-boot.js）本身正确，无需改动。
- **P2-4 · rail「设置」按钮无选中态，导航模型混合**
  - 证据：`index.template.html` L582（无 `data-panel`，onclick 为 `switchPanel('chat');toggleSettings()`）——设置是浮层非面板，rail 上永远看不到"设置被选中"。
  - 修复建议：可接受（v2 语义如此）；若要打磨，可在 toggleSettings 时给该按钮加/去 `.on`。
- **P2-5 · 耗时条被离群值压扁**
  - 证据：`frontend/src/78-analytics.js` L239-258——`run_command` 平均 12480ms 把其他 60-210ms 的条压到不可见宽度。
  - 修复建议：对 `avgMs` 取对数刻度，或在 barW 上限后于数值区展示真实 ms（当前数值区已展示真实值，仅视觉压扁；优先级低）。

---

## 6. 判定

**PASS** —— 契约全保（41 id / 13 onclick / 43 callApi / 39 CSS 类 / 21 变量 ×2 主题 / 4 libs，构建字节级可复现，pytest 31 passed），Anti-Slop 零 P0，5 维 21/25 全部 ≥4。

建议转交筑原型处理 1 项 P1（`.ws-btn` 一行 CSS）与 P2-2/P2-3 两项低成本清理，可在 Phase 5 导出前顺手完成，不阻塞交付。

---

*审查证据：`deliverables/design/v3/shots/`（9 张截图）；对比度复算脚本与输出见 §2；契约抽查命令与输出已在 §1.1/1.3 记录。*
