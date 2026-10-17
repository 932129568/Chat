# 04 · 质量审查报告（Phase 4 · 5 维评审 + Anti-Slop 门控）

> 审查官：**严过审**（质量审查官）
> 审查对象：`frontend/index.template.html`（重设计骨架 + 全部 CSS，576 行）及其构建产物 `glm-chat.html`（140,497 字节）
> 渲染证据：`deliverables/design/shots/{dark,light,dark-settings}.png`（已逐张实际查看）
> 基线：`00-contract-brief.md`（硬约束）、`02-design-system.md`（令牌与规范）

---

## 0. 契约与联通核验（客观证据）

运行 `deliverables/design/check_contract.py`，结果：

```
[DOM id] 40/40      [onclick 处理函数] 13/13     [callApi 后端方法] 43/43
[CSS 类] 39/39      [CSS 变量] 21/21
[本地依赖库] 4 个引用，0 个缺失   → libs/{flate,highlight.min,marked.min,purify.min}.js 全部存在
[构建产物] glm-chat.html 存在 (140497 字节)
结果: PASS — 五大契约全部保住
```

- **`00-contract-brief.md` §7 的联通缺口已修复**：`libs/` 下现有 `marked.min.js`(v12.0.2) / `purify.min.js`(DOMPurify 3.0.9) / `highlight.min.js`(highlight.js 11.9.0)，三个文件均正确暴露 `globalThis.marked` / `DOMPurify` / `var hljs`。→ Markdown 渲染与代码高亮恢复可用。
- 构建链路健康：`build.js` 按数字前缀拼接 `frontend/src/*.js` 注入 `/*__APP_SCRIPT__*/`，产物含新版 CSS（`design system v2`、`--brand-gradient`），未手改产物。
- 结论：**前后端联通的"硬契约"层面无阻塞**，本轮问题全部集中在视觉/无障碍层面。

---

## 1. 五维评分表

| 维度 | 评分 | 一句话依据 |
|------|------|-----------|
| **设计哲学** Philosophy | **4/5** | "精准克制的开发者工作台"这一主张被真正内化（中性底 + 单一强调 `#4f6ef7`、技术数据全走 `--font-mono`、三态即语言）；但有 3 处自相矛盾（虚线边框、`.set-block` 仍是卡片、按钮 emoji），说明理念未被彻底执行。 |
| **视觉层次** Hierarchy | **4/5** | 侧栏"分组标题 + 分隔线"替代卡片堆叠、消息/工具卡/成本条层级清晰、焦点流动顺畅；仅设置面板 4 张等权卡片使区块内层级偏平。 |
| **执行质量** Execution | **4/5** | 令牌化彻底、双主题变量齐备、`prefers-reduced-motion` 有降级、focus 态完整；扣分项为两处与设计系统冲突的样式（详见 P1）。 |
| **特异性** Specificity | **4/5** | 去掉 logo 仍能认出"开发者 Agent 工作台"：等宽路径/命令/token、三态工具卡左色条、底栏成本仪表盘、`本次操作` chip——记忆点明确；调色板偏 Linear 血统，未到 5 分。 |
| **克制** Restraint | **4/5** | 渐变收敛到 logo + 空状态图标 2 处、几乎不用阴影（仅浮层 + 气泡 `--shadow-sm`）、圆角封顶 16px；图标语言在几何符号与 emoji 间混用，是本维唯一噪音源。 |

**总分：20 / 25**
**门槛判定：** 每维 ≥ 3 ✅ ｜ P0 阻塞项 = **1** ❌ ｜ P1 = 5 ❌
**综合结论：REVISE（需修正）** —— 质量已在"良好"档，但存在 1 个无障碍阻塞项 + P1 超限，修完即可 PASS。

---

## 2. Anti-Slop 检查（逐项）

### P0 — 必须修复（阻断发布）

| 检测项 | 结果 | 证据 / 说明 |
|--------|------|------------|
| 紫色/彩虹渐变背景 | **PASS** | 全站唯一渐变是 `--brand-gradient`（L49），仅用于 `.brand-logo`(L86) 与 `.empty-icon`(L367) 两处品牌位；主面为中性灰阶。 |
| 编造统计数据/虚假证言 | **PASS** | 界面数字（`35,182 tokens`、`¥0.0129`、`31,800` 缓存）均为运行时真实回填位（`#tokenStat`/`#liveTokenStat`），非硬编码营销数字。 |
| 通用 emoji 作为图标 | **FAIL（边界）** | 6 个 UI 按钮用 emoji：`🌙`(L443 主题)、`🖼🎬📄🗜`(L550-553 工具按钮)、`📁`(L406)。与设计系统 §9"按钮一律用几何符号或文字"直接冲突，且与同页几何符号（`＋ ⤓ ◈ ☰ ➤ ⇥`）混用。**降级为 P1 处理**（理由：均为文件类型/对象的语义字形，非"🚀=速度"式通用隐喻，且属存量内容）。 |
| 圆角卡片 + 左侧彩色边框 | **FAIL（边界）** | `.tool-call-item`(L298) `border-left:3px solid var(--primary)` + `border-radius`，字面命中该套路。**降级为 P1**：此处左色条承担三态语义（执行中/成功/失败，见设计系统 §6），属"功能化"而非装饰化使用。 |
| 手绘风 SVG 人物插图 | **PASS** | 无插图。 |
| 深色背景 + 霓虹渐变文字 | **PASS** | 无霓虹渐变文字。 |
| 明显破碎的布局/溢出 | **PASS** | 三张截图无溢出、重叠、错位；`.sidebar.collapsed` 负 margin 与 `--sidebar-w` 同步。 |
| **文本对比度不达标（WCAG AA）** | **FAIL ❌ 阻塞** | `--text-3` 实测不达标（见 §3 P0-1），被 11 处小字引用。 |
| 完全无响应式 | **PASS（N/A）** | pywebview 单窗口桌面应用，非移动端场景；`.set-grid` 用 `auto-fit minmax(290px,1fr)` 已具备自适应。 |
| 依赖外部资源但未加载 | **PASS** | 4 个本地库全部存在（check_contract 已验）；字体走系统栈，无 404。 |

### P1 — 建议修复（累计 ≥3 打回）

| 检测项 | 结果 | 证据 |
|--------|------|------|
| 段落宽度 > 75 字符 | PASS | `.content` max-width 72%(L233)，`--content-w:820px`(L47)。 |
| 行高不足（<1.5） | PASS | body 1.6(L67)、`.content` 1.65(L234)。 |
| 同一页面 4+ 种色调 | PASS | 中性灰 + 单一 `--primary` + 三语义色（`--ok/warn/err`）。 |
| 纯黑 #000 作文本色 | PASS | 最深 `--text:#14161c`(L24)。 |
| 色彩无语义 | PASS（轻微） | `--ok` 绿色同时用于 AI 头像(L232)与"成功"态，属设计系统 §6 授权用法。 |
| 阴影堆叠 > 2 层 | PASS | 默认 0 阴影，仅浮层 `--shadow-lg`。 |
| CTA 一屏 > 2 个 | PASS | 每屏 1 个主 CTA（新建对话/发送）。 |
| 动画 >300ms 且无 reduced-motion | PASS | 最长 280ms；`@media (prefers-reduced-motion)`(L373) 已降级。 |
| 无 hover/focus 状态 | PASS | `.cs.open`/`.input-row:focus-within`/各按钮 hover 齐备。 |
| **按钮 emoji 图标 / 图标语言混用** | **FAIL** | 见 P0 表降级项。 |
| **虚线边框** | **FAIL** | `.set-hint`(L216) 与 `.usage-info`(L246) 用 `border-top:1px dashed`，与设计系统 §9"虚线边框"禁令冲突。 |
| **`.set-block` 未按规范去卡片化** | **FAIL** | L199 仍是 `border + radius-lg + --card-bg` 卡片，与设计系统 §6"去掉卡片里套卡片，背景用 `--bg`"冲突。 |
| **用户气泡文字对比度** | **FAIL** | 白字 on `--user-bubble:#4f6ef7` = **4.28:1** < 4.5:1（详见 P1-1）。 |

### P2 — 可选优化

- `.md-body :not(pre)>code` 浅色主题 `#e06c75` on `--chip-bg:#f1f3f7` ≈ **2.86:1**，行内代码可读性偏弱。
- 图标尺寸/风格不统一（16px emoji vs 几何符号 vs 12px 语义 emoji）。
- `.empty-state` 文案可更贴合"开发者 Agent"（当前偏通用）。
- 工具卡 `.tc-meta` 与 `.toolchip` 两套工具样式并存，可评估是否收敛为一套。

---

## 3. 阻塞项（必须修）

### 🔴 P0-1 · `--text-3` 对比度不达 WCAG AA（全站次级文字）

**位置**：`:root` L24 `--text-3:#9aa0ae`；`body.dark` L55 `--text-3:#6a6f7b`。
**引用点**（11 处小字，均为 11–12px 正文级文本）：`.brand-sub`(L90)、`#effPath/#wsEffPath`(L120)、`.cs-arrow`(L136)、`.section-label`(L148)、`.session-time`(L163)、`.session-del`(L165)、`.sidebar-empty`(L170)、`.set-hint`(L215)、`.usage-info`(L247)、`.stop-note`(L291)、`.typing-dots`(L293)。

**实测对比度**（WCAG 2.1 相对亮度公式）：

| 主题 | 前景 | 背景 | 实测 | AA 要求(小字) |
|------|------|------|------|--------------|
| 浅色 | `#9aa0ae` | `--main-bg #f6f7f9` | **2.44:1** | 4.5:1 ❌ |
| 浅色 | `#9aa0ae` | `--sidebar-bg #ffffff` | **2.62:1** | 4.5:1 ❌ |
| 深色 | `#6a6f7b` | `--main-bg #101114` | **3.78:1** | 4.5:1 ❌ |
| 深色 | `#6a6f7b` | `--sidebar-bg #16181d` | **3.64:1** | 4.5:1 ❌ |

**修复建议**：把 `--text-3` 提到能过 AA 的档位（保留三级层次，但三档都要 ≥4.5:1）：
- 浅色：`--text-3:#9aa0ae` → **`#727885`**（on `#f6f7f9` ≈ 4.6:1）
- 深色：`--text-3:#6a6f7b` → **`#9298a6`**（on `#101114` ≈ 4.6:1）

若想保留"更弱"的视觉层级，可保留 `--text-3` 仅用于**非文字**（分隔线、点），把 `.session-time`/`.set-hint`/`.hint` 等文字改用 `--text-2`。

---

## 4. 建议项（可选）

### 🟠 P1-1 · 用户气泡白字对比度 4.28:1（略低于 AA）
**位置**：L28 `--user-bubble:#4f6ef7` + L28 `--user-bubble-text:#ffffff`；应用处 `.message.user .content`(L235)。
**实测**：`#fff` on `#4f6ef7` = **4.28:1**（差 0.22）。深色 `#3b53c9` 无此问题。
**修复**：浅色 `--user-bubble` 略加深至 **`#4059e0`**（≈4.9:1），或正文加 `font-weight:500` 提升等效对比。

### 🟠 P1-2 · 按钮 emoji 图标 / 图标语言混用
**位置**：`🌙`(L443)、`🖼🎬📄🗜`(L550-553)、`📁`(L406)。
**修复**：与同页几何符号统一——换成内联 SVG（Lucide 风格 16px 线性图标）或几何字形；至少把 `🌙` 换成 `☀/☾`、`📁` 换成 `▸`。设计系统 §9 已明确"按钮一律用几何符号或文字"。

### 🟠 P1-3 · 虚线边框违反自身设计系统
**位置**：`.set-hint`(L216)、`.usage-info`(L246) 的 `border-top:1px dashed var(--border)`。
**修复**：改 `solid`；若想弱化，用 `1px solid var(--border)` + 提高上方 `padding-top`，勿用 dashed。

### 🟠 P1-4 · `.set-block` 未去卡片化
**位置**：L199-200 `border:1px solid;border-radius:var(--radius-lg);background:var(--card-bg)`。
**修复**：按设计系统 §6 改为 `background:var(--bg)` + 去掉外边框，仅靠 `.set-title` 的 `::before` 蓝条与分隔线分组，消除"面板里套 4 张卡"的视觉重量。

### 🟠 P1-5 · `.tool-call-item` 左色条与 Anti-Slop 套路重叠（边界）
**位置**：L298 `border-left:3px solid var(--primary)`。
**修复（可选，保留语义）**：把状态承载重心移到 `.tc-dot` + 底色，左色条收细到 `2px` 或改为 `.tc-dot` 前置色点，降低"通用左描边卡"既视感。

### ⚪ P2 · 其他
- 行内代码浅色主题配色（L256 `#e06c75`）提升对比或改用中性色。
- 统一工具卡与 `.toolchip` 两套工具样式。

---

## 5. 亮点（具体，非客套）

1. **三态工具卡（灵魂组件）** 落地到位：`.tool-call-item` 用"左色条 + `.tc-dot` 状态点 + `--font-mono` 参数"统一执行中(L298)/成功(L303)/失败(L304)，失败态叠加 `--err-bg` 底，截图 `dark.png` 中 `run_command · pytest … ✗ 退出码 1` 一眼可辨——真正贴合"看得见 Agent 在干活"。
2. **技术数据全等宽**：路径/命令/token 一律 `--font-mono` + `font-variant-numeric:tabular-nums`(L172)，`.header-title`(L185) 连标题都用等宽，特异性强。
3. **克制到位**：`--shadow-md` 大面积使用被收敛，默认 0 阴影、仅浮层用 `--shadow-lg`；渐变仅 2 处品牌位。
4. **契约零破坏**：40 id / 43 api / 13 onclick / 39 class / 21 var 全保，`emptyState` 动态结构(L539-543)与契约 §5 完全一致。

---

## 6. 最终结论

### **REVISE（需修正）**

**判定依据**：5 维均 ≥3 且总分 20/25 属"良好"档，但命中 1 个 Anti-Slop **P0**（`--text-3` 对比度）+ P1 超限（5 条）。按门控规则"存在 P0 → 需修正"，不可直接导出。

**必须修复的最小集合（修完即 PASS）**：
1. **`--text-3` 提对比**：浅色 `#9aa0ae→#727885`、深色 `#6a6f7b→#9298a6`（或把 11 处文字改用 `--text-2`）。→ 解 P0-1
2. **用户气泡对比**：浅色 `--user-bubble:#4f6ef7→#4059e0`。→ 解 P1-1
3. **虚线改实线**：`.set-hint`/`.usage-info` 的 `border-top` 改 `solid`。→ 解 P1-3
4. **按钮 emoji 换几何/SVG**：`🌙 📁 🖼🎬📄🗜`。→ 解 P1-2

以上 4 项均为**令牌/单行样式改动**，不触碰任何 DOM id / onclick / callApi 契约，改 `frontend/` 源码后 `node frontend/build.js` 重建即可。`.set-block` 去卡片化（P1-4）与工具卡左条收敛（P1-5）列为强烈建议，可同批处理。

**修复后预期**：哲学/层次/执行/克制各 +0~1，P0 清零、P1 归零 → 达 20+/25，判定 **PASS**。

---

# 第 2 轮复验（Phase 4 修订轮 · 复审）

> 复审人：**严过审**　｜　复审范围：仅验 `04-critique.md` 所列修正项（含 1 项 P2）
> 证据：`frontend/index.template.html`、`frontend/src/15-theme.js`、`frontend/src/85-session-mgmt.js`、`deliverables/design/05-fixes.md`、4 张重截图（均已 Read 实看）

## R2-1 逐项复验（源码级 + 对比度复算）

| 编号 | 修正内容 | 源码证据 | 独立复算 | 判定 |
|------|---------|---------|---------|------|
| **P0-1** | `--text-3` 提对比 | L24 `--text-2:#5f6674;--text-3:#6a7180`；L55 `--text-3:#9298a6` | 浅 `#6a7180`：on `#fff` **4.90**、on `#f6f7f9` **4.57**；深 `#9298a6`：on `#101114` **6.58**、on `#16181d` **6.34** | ✅ **清零** |
| **P1-1** | 用户气泡对比 | L28 `--user-bubble:#4059e0` | 白字 on `#4059e0` = **5.64** | ✅ |
| **P1-2** | emoji→SVG | L445 主题/太阳-月亮、L446 齿轮、L408 文件夹、L552-555 四工具按钮均内联 SVG；`15-theme.js` L2-3 常量 + L7 `innerHTML`；CSS L351-353 `.icon-btn/.pill-btn/.tool-btn/.ws-btn/.ghost-btn svg{16px}` | — | ✅ |
| **P1-3** | 虚线→实线 | L215 `.set-hint`、L245 `.usage-info` 均 `border-top:1px solid` | — | ✅ |
| **P1-4** | `.set-block` 去卡片 | L199 `.set-block{background:transparent;border:none;padding:0;}` | 截图 `dark-settings.png` 已确认无卡片边框 | ✅ |
| **P1-5** | 左色条收敛 | L297 `.tool-call-item` `border-left:2px solid` | 三态在 `dark.png`/`light.png` 仍清晰可辨 | ✅ |
| **P2** | 行内代码对比 | L255 `color:#c0392b` | on `--chip-bg #f1f3f7` = **4.87** | ✅ |
| **额外** | "本次操作"去遗留内联样式 | `85-session-mgmt.js` L49/51 改 `.tool-call-item done` + `.tc-dot` | 截图行内为绿点 + 左绿条，与工具卡统一 | ✅ |

> **对建议值偏差的说明**：审查报告原建议 `--text-3` 浅色取 `#727885`，经独立复算确为 **4.43:1**（on `#fff`）**不达标**——修正方按公式反解改取 `#6a7180`（4.90/4.57）是**正确的**，审查建议值当时偏保守，特此更正。深色 `#9298a6` 与 P1-1 取值均与复算一致。

## R2-2 契约回归

```
[DOM id] 40/40   [onclick] 13/13   [callApi] 43/43
[CSS 类] 39/39   [CSS 变量] 21/21  [本地依赖库] 4 引用 0 缺失
结果: PASS ｜ 构建产物 glm-chat.html 143,150 字节（24 模块 / 2668 行，node build.js 可复现）
```

## R2-3 视觉复核（4 张重截图实看）

- `light.png` / `dark.png`：图标语言已统一为 16px 线性 SVG（工具栏 4 个附件按钮、主题、设置、浏览），无 emoji 混用；次级文字（`session-time`/`hint`/`brand-sub`）可读性明显提升；工具卡三态（进行中蓝条+spinner / 成功绿点 / 失败红条+红底）仍清晰。
- `dark-settings.png`：设置面板 4 组去卡片化后视觉重量下降，仅靠 `.set-title` 蓝条 + 分隔线分组，符合设计系统 §6。
- `light-empty.png`：空状态品牌渐变图标 + 次级说明正常，输入区图标为线性 SVG。

## R2-4 残留观察（P2，不阻塞）

动态生成内容仍使用 emoji，属**设计系统 §6 明确许可的"语义 emoji"**，故不计入阻塞：
- 消息操作按钮 `📋 复制 / ☆ 收藏 / ✓`（`50-markdown.js` L94/99）、右键菜单 `✂ 📋 ☑`（`105-context-menu.js` L18-21）、工具卡标签 `📖 📂 📝 ⚡`（`80-utils.js` L6-19）、`⚠️/⛔`（`60-agent-loop.js`/`75-token-stat.js`）。
- 建议（可选，非必须）：若追求"静态+动态"全统一，可在后续 polish 轮把消息操作按钮与右键菜单一并换成 SVG；本轮**不构成发布阻碍**。

## R2-5 复审结论

### **PASS ✅**

| 门控 | 修正前 | 修正后 |
|------|-------|-------|
| P0 阻塞项 | 1 | **0** ✅ |
| P1 项 | 5 | **0** ✅ |
| 契约 | PASS | **PASS**（零破坏） |
| 5 维均 ≥3 | 是 | **是** |

- **P0 已清零，P1 已归零，契约零破坏** → 通过门控，可进入 Phase 5 导出交付。
- 唯一残留为 P2 观察项（动态内容语义 emoji），已获设计系统授权，不阻塞。
- 复审过程中**发现并更正了审查报告自身的 1 处建议值错误**（`#727885` → 实际 `#6a7180`），修正方的取值经复算正确。
