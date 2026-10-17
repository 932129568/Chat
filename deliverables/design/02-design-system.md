# GLM-Chat 设计系统（Phase 2 · 设计令牌）

> 产出人：**主理人代行**（设计系统专家 彩格调 连续 2 次调度失败于基础设施 500 错误，按失败兜底规则由主理人代行，已向用户如实说明）
> 依据：`01-requirements.md`（方向 A：专业开发工具）+ `design-systems` 知识库（Modern Minimal × Tech Utility 混合）

---

## 1. 视觉主题

**哲学：精准克制的开发者工作台。**
不是聊天软件，是一台"看得见 Agent 在干活、算得清花了多少钱"的桌面仪器。

**三条设计原则**
1. **中性为底，单一强调**——界面 95% 由中性灰阶构成，`#4f6ef7` 蓝紫只用在"当前焦点"与"可操作"上。
2. **技术数据用等宽**——路径、命令、token 数、耗时一律 `--font-mono`，让数字对齐、让代码可读。
3. **状态即语言**——执行中/成功/失败/警告用统一的色 + 形（点、边、底），不靠文字解释。

---

## 2. 候选与选定

| 候选 | 特征 | 适配性 |
|------|------|--------|
| **Linear**（选定） | 中性灰阶 + 单一蓝紫强调、极细边框、紧凑密度、克制的圆角、等宽承载技术数据 | ★★★★★ 与"开发者长时间盯屏 + 高密度 + 品牌蓝紫"完全同构；且能自然承接现有 `#4f6ef7` |
| Vercel | 黑白极致对比、强几何、弱圆角 | ★★★★ 很"工具"，但黑白二分对"执行中/成功/失败"多状态表达不够柔；深色偏纯黑，长时盯屏略刺 |
| Raycast | 大留白、柔和中性、命令面板感 | ★★★☆ 优雅但密度偏低，与"一屏看全权限/成本/工具状态"的诉求冲突 |

**借鉴**：从 Vercel 借「边框即分隔、几乎不用阴影」的克制；从 Raycast 借「空状态与快捷键提示」的友好度。

---

## 3. 色彩（浅色 / 深色两套）

设计要点：
- `--text-2` 由 `#8b8e99` 提升到 `#6b7180`（浅色）/ `#8b909c`（深色），修复现有**次级文字对比度不足**的问题（护眼诉求）。
- `--user-bubble` 由渐变改为**纯色**（收敛品牌渐变面积，渐变只保留在 logo 与空状态图标 1 处品牌位）。
- 新增 `--surface-2`（次级面）、`--border-strong`（强调边框）、`--text-3`、`--primary-soft`、`--user-bubble-text`，用于组件规范化。

**可直接抄进 CSS：**

```css
:root{
  /* 面 */
  --bg:#f6f7f9; --sidebar-bg:#ffffff; --main-bg:#f6f7f9; --header-bg:rgba(255,255,255,.78);
  --card-bg:#ffffff; --surface-2:#f1f3f7;
  /* 线 */
  --border:#e4e6ec; --border-strong:#d2d6e0;
  /* 字 */
  --text:#14161c; --text-2:#6b7180; --text-3:#9aa0ae;
  /* 强调 */
  --primary:#4f6ef7; --primary-hover:#3d5ae6; --primary-soft:#eef1fe;
  /* 气泡 */
  --user-bubble:#4f6ef7; --user-bubble-text:#ffffff; --ai-bubble:#ffffff;
  /* 交互面 */
  --hover:#f1f3f7; --active:#eef1fe; --chip-bg:#f1f3f7;
  /* 语义 */
  --ok:#1a7f4e; --warn:#b7791f; --err:#cf3222;
  --ok-bg:#e8f6ee; --warn-bg:#fdf5e6; --err-bg:#fdecea;
  /* 深度 */
  --shadow-sm:0 1px 2px rgba(16,18,28,.06);
  --shadow-md:0 2px 8px rgba(16,18,28,.08);
  --shadow-lg:0 12px 28px rgba(16,18,28,.14);
  /* 圆角 */
  --radius-xs:4px; --radius-sm:6px; --radius-md:9px; --radius-lg:12px; --radius-xl:16px; --radius-full:999px;
  /* 字体 */
  --font-sans:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei","Noto Sans SC",sans-serif;
  --font-mono:"JetBrains Mono","Cascadia Code",Consolas,"SFMono-Regular",Menlo,monospace;
  /* 动效 */
  --dur-fast:120ms; --dur-base:180ms; --dur-slow:280ms;
  --ease:cubic-bezier(.4,0,.2,1); --ease-out:cubic-bezier(.16,1,.3,1);
  /* 尺寸 */
  --sidebar-w:264px; --content-w:820px;
}
body.dark{
  --bg:#101114; --sidebar-bg:#16181d; --main-bg:#101114; --header-bg:rgba(22,24,29,.78);
  --card-bg:#1a1c22; --surface-2:#212429;
  --border:#272a32; --border-strong:#343843;
  --text:#e6e7ea; --text-2:#8b909c; --text-3:#6a6f7b;
  --primary:#6b84ff; --primary-hover:#8098ff; --primary-soft:#1d2337;
  --user-bubble:#3b53c9; --user-bubble-text:#ffffff; --ai-bubble:#1a1c22;
  --hover:#212429; --active:#232a3f; --chip-bg:#212429;
  --ok:#4ade80; --warn:#fbbf24; --err:#f87171;
  --ok-bg:#12251b; --warn-bg:#2a2213; --err-bg:#2b1618;
  --shadow-sm:0 1px 2px rgba(0,0,0,.4);
  --shadow-md:0 2px 10px rgba(0,0,0,.45);
  --shadow-lg:0 16px 40px rgba(0,0,0,.6);
}
```

---

## 4. 排版

| 角色 | 字号 | 字重 | 行高 | 用途 |
|------|------|------|------|------|
| display | 22px | 600 | 1.3 | 空状态标题 |
| h1 / 标题 | 16px | 600 | 1.4 | 面板标题、品牌名 |
| h2 | 14px | 600 | 1.45 | 区块标题 |
| body | 14px | 400 | 1.65 | 消息正文 |
| ui | 13px | 500 | 1.5 | 按钮、下拉、会话标题 |
| meta | 12px | 400 | 1.5 | 时间、次级说明 |
| micro | 11px | 500 | 1.45 | 徽章、路径、token 数 |
| **mono** | 12.5px | 400 | 1.6 | 代码块、路径、命令、token 数字 |

- 正文 `--font-sans`；**所有路径 / 命令 / token 数字 / 代码 / 工具参数 → `--font-mono`**。
- 数字统一 `font-variant-numeric:tabular-nums`（现有 `.usage-info span b` 已用，扩展到成本仪表盘）。
- 中文正文 `letter-spacing:0`；微标签（`.set-title` 等）`letter-spacing:.02em` + `text-transform:uppercase` 仅用于英文。

---

## 5. 间距与栅格

间距阶梯（4 基数）：`2 4 6 8 10 12 14 16 20 24 32`
- 侧栏宽度：**264px**（原 272px，略收，换取主区内容空间）；折叠态 `margin-left:-264px`。
- 内容最大宽度：**820px**（原 860px），聊天气泡 `.content` max-width 由 76% 收到 **72%**。
- 面板内边距：`16px`；卡片内边距：`12px`；控件垂直节奏：`8px`。
- 侧栏分组之间用 `1px var(--border)` 分隔 + `12px` 上下留白，取代现状的"卡片叠卡片"。

---

## 6. 组件规范

### 按钮
- **主按钮**（新建对话）：实心 `--primary`，圆角 `--radius-md`，高 34px，字 13px/600，**去掉渐变与 translateY 位移**，hover 只变 `--primary-hover`。
- **次按钮**（导出/余额/设置 pill）：透明底 + `1px --border`，hover `--hover` 底 + `--border-strong` 边。
- **幽灵按钮**（虚线）：改**实线** `--border` + `--text-2`，hover 变 `--primary`。虚线是"未完成"的隐喻，工具界面不该用。
- **图标按钮**：32×32，圆角 `--radius-sm`，默认 `--text-2`，hover `--hover` + `--text`。

### 输入框 / 下拉
- 输入框：高 36px，`1px --border`，圆角 `--radius-md`，focus 时 `--primary` 边 + `0 0 0 3px var(--primary-soft)` 光晕。
- 自定义下拉 `.cs-*`：`cs-trigger` 高 36px；`cs-menu` 圆角 `--radius-lg`，`--shadow-lg`，选项 hover `--hover`、选中 `--primary-soft` + `--primary` 字。
- **原生 `<select>` 若被 `initCustomSelect` 包装失败，必须回退可用**（现有兜底逻辑保留）。

### 卡片 / 面板
- 统一 `--card-bg` + `1px --border` + `--radius-lg`，**默认无阴影**（借 Vercel 的克制）；仅浮层（下拉/右键菜单）用阴影。
- 设置面板 `.set-block`：去掉"卡片里套卡片"，改为**分组标题 + 分隔线 + 字段**，背景用 `--bg` 而非再套一层卡。

### 徽章 `.header-badge`
`--primary-soft` 底 + `--primary` 字，圆角 `--radius-full`，11px/500，高 20px。

### 工具调用卡片（灵魂组件）
三态统一用"左色条 + 状态点 + 等宽参数"：
- **执行中**：左条 `--primary`，`.tool-spinner` 保留，底色 `--surface-2`，卡片带轻微呼吸动画（透明度 0.85↔1，2s）。
- **成功**：左条 `--ok`，状态点 `●` `--ok`。
- **失败**：左条 `--err`，底色 `--err-bg`，状态点 `●` `--err`。
- 参数（路径/命令）用 `--font-mono` 12px，超长省略号截断，`title` 给全文。
- 工具名与参数之间用 `·` 分隔，不用 emoji 堆叠（现状 `📖 📂 📝` 保留语义但缩小到 12px 并降低饱和度）。

### 成本仪表盘 `.token-stat` / `#liveTokenStat`
- 底栏 `.token-stat`：`--surface-2` 底 + 上边框，数字等宽，`token` / `缓存命中` / `¥` 三段用 `·` 分隔。
- 超预算时：数字变 `--err` + 前置 `⛔`；接近（>80%）变 `--warn`。
- 输入区下方 `#liveTokenStat` 保持单行等宽，去掉冗长中文，压缩为 `1.2k tok · 命中 42% · ¥0.0031`。

### 消息气泡
- 用户：`--user-bubble` 纯色 + `--user-bubble-text`，圆角 `--radius-lg`（右下角 `--radius-xs` 收角）。
- AI：`--ai-bubble` + `1px --border`，圆角 `--radius-lg`（左下角收角）。
- 头像：36×36 → **32×32**，圆角 `--radius-md`；用户 `--primary` 实心，AI 保留绿色语义但改为 `--ok` 系实心（去渐变）。
- 代码块：底色 `#0e1015`（浅色主题下也保持深底，符合"终端"隐喻），圆角 `--radius-md`，右上角语言标签 + 复制按钮。

### 会话列表项
高 44px，圆角 `--radius-sm`，hover `--hover`，active `--active` + 左侧 2px `--primary` 竖条；标题 13px/500，时间 11px `--text-3`；删除按钮 hover 才显形（现状保留）。

### 滚动条
宽 8px → **10px 轨道透明 + 8px 滑块**，滑块 `--border-strong`，hover `--text-3`。

---

## 7. 圆角与深度

| 阶梯 | 值 | 用途 |
|------|-----|------|
| xs | 4px | 气泡收角、微标签 |
| sm | 6px | 列表项、图标按钮、chip |
| md | 9px | 按钮、输入框、头像 |
| lg | 12px | 卡片、面板、下拉菜单 |
| xl | 16px | 空状态图标、浮层容器 |

深度：**默认 0 阴影**（用边框分层）；`--shadow-sm` 仅消息气泡；`--shadow-lg` 仅浮层（下拉/右键菜单/系统提示）。现状的 `--shadow-md` 大面积使用要收敛。

---

## 8. 动效

| 场景 | 时长 | 缓动 |
|------|------|------|
| hover / focus 变色 | 120ms | `--ease` |
| 面板展开、下拉出现 | 180ms | `--ease-out` |
| 消息入场 | 220ms | `--ease-out`（位移 6px，原 8px） |
| 侧栏折叠 | 240ms | `--ease` |
| 流式进度条 | 1.4s | `ease-in-out`（保留） |

`prefers-reduced-motion: reduce` 时全部动效降为 0.01ms。

---

## 9. 注意事项 / Anti-Slop 反面清单

**禁止**：
- 大面积极彩渐变（渐变仅允许 1 处品牌位：logo / 空状态图标）
- 彩色气泡、彩色边框堆叠（`#f0f5ff` 底 + `#1677ff` 字的工具行属于此类，需改为中性底 + 状态色）
- 圆角 > 16px 的"胶囊化"卡片；虚线边框
- emoji 作为主要图标语言（保留极少量语义 emoji，但按钮一律用几何符号或文字）
- 每个卡片都带阴影
- 纯黑 `#000` 与纯白 `#fff` 大面积对撞（深色底用 `#101114` 而非纯黑）

---

## 10. Agent 实施指南（交给原型构建师）

1. **红线优先**：必须保留 **40 个 DOM id**、**43 个 callApi 方法名**、**全部内联 onclick 及签名**、**全部 JS 动态使用的 CSS 类名**（清单见 `00-contract-brief.md` §3/§4/§5）。`emptyState` 的动态重建结构不可变。
2. **变量不删**：本文件第 3 节给出的 `:root` / `body.dark` 是**超集**，旧变量名一个都不能少（JS 里有 `var(--primary)` / `var(--chip-bg)` / `var(--err)` 内联引用）。
3. **只改 `frontend/` 源码**，改完 `node frontend/build.js`；**绝不手改根目录 `glm-chat.html`**。
4. **两套主题都要验**：浅色与深色下逐一检查对比度（正文 ≥ 4.5:1，次级 ≥ 3:1）。
5. **改造顺序建议**：变量层 → 侧栏 → 头部/设置面板 → 消息渲染（含工具卡片、代码块、成本信息）→ 输入区 → 空状态与浮层。
6. **`--sidebar-w` / `--content-w` 用了变量，记得同步 `.sidebar.collapsed` 的负 margin**。
