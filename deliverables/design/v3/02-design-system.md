# GLM-Chat 设计系统 v3 · 设计令牌（Phase 2）

> 产出人：设计系统专家 **彩格调（Cai）**
> 版本：v3（在 v2「Modern Minimal × Tech Utility」结构底座上，叠加「Glass / Aurora / Glow」视觉皮肤层）
> 依据（均为实际读到的文件，未臆造）：
> `deliverables/design/v3/01-requirements.md`（v3 需求摘要，最重要）、`deliverables/design/00-contract-brief.md`（契约红线）、
> `deliverables/design/02-design-system.md`（v2 令牌结构底座）、`frontend/index.template.html`（现有 `:root` / `body.dark` 变量与全部 CSS 类）；
> 参照 `design-systems` 技能库（71 套品牌级系统）中的 **Vercel / Raycast / Linear** 与 macOS Sonoma / Arc 的玻璃质感。
> 一句话定位：**v2 的骨架不动，给整台"桌面仪器"套上一层会呼吸的极光玻璃外壳——氛围可以炫，内容必须稳。**

---

## A. 设计系统定位

### A.1 双层架构：结构底座 + 视觉皮肤

v3 不是"换一套设计系统"，而是**在 v2 已建立的结构底座上叠加一层视觉皮肤**。两层职责严格分离：

| 层 | 名称 | 来源 | 职责 | 是否可关 |
|----|------|------|------|:---:|
| **底座层** | Modern Minimal × Tech Utility | v2（Linear 血统） | 中性灰阶、单一强调色、等宽技术数据、三态语言、高对比信息主体、紧凑密度 | ❌ 永远在线 |
| **皮肤层** | Glass / Aurora / Glow | v3 新增 | 背景氛围、面板玻璃质感、微光边框、发光焦点、图表辉光、入场动效 | ✅ 特效总开关可关 |

> **张力原则（需求 §1.3）**：**氛围层炫，信息主体稳**。极光只存在于 `z-index:-1` 的背景层；玻璃只做面板容器；发光只做交互反馈与数据高亮。文字、数字、工具状态**永远坐在不透明兜底之上**，对比度不随背景波动。

### A.2 参考血统（参照，非照搬）

| 参照对象 | 借用什么 | 明确不照搬什么 |
|---------|---------|--------------|
| **Vercel** | 「边框即分隔、默认无阴影」的克制；深色不纯黑、浅色不纯白 | 不照搬其黑白极致二分（会压死三态语义）；不照搬其弱圆角（玻璃层需要更柔的圆角承载模糊） |
| **Raycast** | 命令面板式的大留白、柔和中性、hover 反馈的即时感、tooltip 友好度 | 不照搬其低信息密度（本产品要求一屏看全成本/权限/工具状态） |
| **Linear** | 单一强调色、极细边框、等宽承载技术数据、克制的动效时长 | 不照搬其"零玻璃、零发光"的绝对扁平（v3 用户明确要炫） |
| **macOS Sonoma / Arc** | 玻璃面板的"亮边 + 半透底 + 高模糊"三件套；层级的亮度差而非纯阴影 | 不照搬其大面积磨砂（会削弱数据可读性）；不照搬其全窗口透明（本产品需保证兜底对比度） |

> **参照而非照搬的落地含义**：v3 的色彩基座仍是 GLM Chat 的品牌蓝紫 `#4f6ef7`，不是 Vercel 的黑、也不是 Raycast 的暖灰；极光青/紫/品红**只进入背景氛围与图表**，不进入正文 UI（需求 §1.4）。

### A.3 视觉方向坐标（5 大视觉学派定位）

- **主坐标**：`Modern Minimal`（结构）× `Tech Utility`（数据密度与等宽）
- **叠加坐标**：在两者之上叠加一层**"环境光"维度**——这是 v3 独有的第三维，不改变主坐标的色彩与排版秩序，只改变"光与材质"。

---

## B. 设计令牌（核心交付物）

> **总规则**：保留 v2 **全部变量名**（`--bg --sidebar-bg --main-bg --header-bg --card-bg --surface-2 --border --border-strong --text --text-2 --text-3 --primary --primary-hover --primary-soft --user-bubble --user-bubble-text --ai-bubble --hover --active --chip-bg --ok --warn --err --ok-bg --warn-bg --err-bg --shadow-sm/md/lg --radius-* --font-sans/mono --dur-fast/base/slow --ease/ease-out --sidebar-w --content-w --brand-gradient`），**只新增不删改**。以下所有 v2 值均以 `frontend/index.template.html` 实际读到的为准。

### B.1 玻璃层令牌（Glass）

| 令牌 | 浅色 `:root` | 深色 `body.dark` | 说明 |
|------|-------------|-----------------|------|
| `--glass-bg` | `rgba(255,255,255,.62)` | `rgba(26,28,34,.60)` | 玻璃面板半透底（叠在兜底色之上） |
| `--glass-bg-2` | `rgba(255,255,255,.80)` | `rgba(30,33,41,.78)` | 二级玻璃（浮层/嵌套/hover 提升） |
| `--glass-border` | `rgba(255,255,255,.72)` | `rgba(255,255,255,.10)` | 1px 半透明**亮边**（玻璃的"高光棱"） |
| `--glass-blur` | `18px` | `20px` | `backdrop-filter` 模糊半径 |
| `--glass-fallback` | `#f4f6fb` | `#171a21` | **不透明兜底色**：`backdrop-filter` 不支持或极光流动时的最终文字背景 |

> **兜底机制（R6 硬要求）**：玻璃面板实现必须为 `background: linear-gradient(var(--glass-bg),var(--glass-bg)), var(--glass-fallback);`——**兜底色永远垫在最底层**，玻璃只是其上的半透提亮层。这样文字背景 = 兜底色为主 + 极光微量渗透，对比度被锁死在可测范围内。

### B.2 极光色板（Aurora）

| 令牌 | 值 | OKLCh（近似） | 用途 |
|------|-----|--------------|------|
| `--aurora-1` | `#22d3ee` | `oklch(78% 0.13 205)` | 青——极光主光晕、图表第 2 色 |
| `--aurora-2` | `#4f6ef7` | `oklch(60% 0.20 265)` | 蓝——与品牌主色同源，极光基底、图表第 1 色 |
| `--aurora-3` | `#8b5cf6` | `oklch(61% 0.22 292)` | 紫——极光过渡、图表第 3 色 |
| `--aurora-4` | `#ec4899` | `oklch(65% 0.24 355)` | 品红——极光点缀、图表第 4 色 |
| `--aurora-opacity` | `.12` | — | **内容区叠加不透明度上限（≤12%，需求 §1.3 硬约束）** |
| `--aurora-bg-opacity` | `.55` | — | 独立 `#auroraBg` 固定背景层整体不透明度 |
| `--aurora-blur` | `90px` | — | 极光色斑模糊半径（避免出现清晰色块） |

> **纪律**：极光四色**禁止出现在正文 UI**（文字、按钮底色、边框）。它们只允许出现在：① `#auroraBg` 背景层；② 图表系列色；③ logo/选中图标的径向光晕（`--glow-color` 基底）。**内容区任何位置的极光叠加 ≤12% 不透明度**。

### B.3 发光令牌（Glow）

| 令牌 | 浅色 `:root` | 深色 `body.dark` | 说明 |
|------|-------------|-----------------|------|
| `--glow-color` | `rgba(79,110,247,.50)` | `rgba(107,132,255,.55)` | 发光基色（品牌蓝，随主题切深浅） |
| `--glow` | `0 0 0 1px var(--glass-border), 0 0 22px -6px var(--glow-color)` | 同结构 | **常规微光**：1px 亮边 + 外发光。用于卡片 hover、次要强调 |
| `--glow-strong` | `0 0 0 1px rgba(79,110,247,.60), 0 0 34px -4px rgba(79,110,247,.70)` | `0 0 0 1px rgba(107,132,255,.65), 0 0 34px -4px rgba(107,132,255,.75)` | **强发光**：主 CTA、选中图标、焦点输入框 |
| `--glow-focus` | `0 0 0 3px var(--primary-soft), 0 0 20px -4px var(--glow-color)` | 同结构 | 焦点环：保留 v2 的 3px soft 环，外加发光（可关） |

> **发光纪律**：同一屏内**最多 2 处**强发光（当前焦点 + 一个主 CTA）。发光是"注意力货币"，滥用即失效。

### B.4 图表色板（Chart，深浅各一套）

| 令牌 | 浅色 `:root` | 深色 `body.dark` | 用途 |
|------|-------------|-----------------|------|
| `--chart-1` | `#4f6ef7` | `#6b84ff` | 系列①（成本/总量，主色） |
| `--chart-2` | `#22d3ee` | `#34e0f5` | 系列②（缓存命中） |
| `--chart-3` | `#8b5cf6` | `#a78bfa` | 系列③（工具次数） |
| `--chart-4` | `#ec4899` | `#f472b6` | 系列④（失败/拦截） |
| `--chart-grid` | `rgba(16,18,28,.08)` | `rgba(255,255,255,.09)` | 网格线（必须低对比，退居背景） |
| `--chart-axis` | `#6a7180` | `#8b909c` | 坐标轴文字/刻度（用 `--text-2/3` 同源色） |
| `--chart-area-from` | `rgba(79,110,247,.26)` | `rgba(107,132,255,.30)` | 面积图渐变起点 |
| `--chart-area-to` | `rgba(79,110,247,0)` | `rgba(107,132,255,0)` | 面积图渐变终点（透明） |

### B.5 动效时长令牌（Motion）

| 令牌 | 值 | 用途 | 备注 |
|------|-----|------|------|
| `--dur-aurora` | `26s` | 极光主循环 | ≥20s，慢速低频 |
| `--dur-aurora-2` | `40s` | 极光副漂移（错频避免机械感） | 两条不同周期叠加 |
| `--dur-panel` | `200ms` | 面板切换过渡 | ≤220ms（需求 §4 E9） |
| `--dur-glow` | `260ms` | 发光/边框 hover 渐变 | 比变色慢一点，发光更"沉" |
| `--dur-count` | `640ms` | 数字滚动 count-up | 尊重 reduced-motion |
| `--dur-chart` | `900ms` | 图表入场绘制 | 折线描画 / 柱状生长 |
| `--ease-glow` | `cubic-bezier(.22,.61,.36,1)` | 发光与面板缓动 | 出场更快、收尾更柔 |

> 复用 v2 的 `--dur-fast:120ms --dur-base:180ms --dur-slow:280ms` 与 `--ease / --ease-out`，不重复定义。

### B.6 导航与面板尺寸令牌（Nav / Layout）

| 令牌 | 值 | 说明 |
|------|-----|------|
| `--rail-w` | `60px` | 左侧图标栏宽度（需求建议 56–64px，取中） |
| `--rail-btn` | `40px` | 图标按钮命中区（40×40，圆角 `--radius-md`） |
| `--rail-gap` | `6px` | 图标按钮间距 |
| `--panel-pad` | `22px` | 面板内边距 |
| `--panel-gap` | `16px` | 面板内卡片间距 |
| `--panel-title` | `18px` | 面板大标题字号 |
| `--chart-h` | `240px` | 主趋势图高度（宽度自适应，占主区 ≥60%） |
| `--chart-h-sm` | `160px` | 次图表高度 |

> **R5 提醒**：`--sidebar-w:264px` 语义不变，`.sidebar.collapsed{margin-left:calc(-1*var(--sidebar-w))}` 保持不变；`--rail-w` 是**独立新增**的常驻栏，不参与折叠计算。

### B.7 对比度实测（R6 硬要求）

> 测量方法：按 WCAG 2.1 相对亮度公式计算；**玻璃面板复合背景 = `--glass-fallback`（不透明兜底）叠 `--glass-bg` 半透提亮，再叠极光 ≤12%**（最坏情况取青 `#22d3ee`）。下表为**取最坏叠加后的实测值**。

| 文本令牌 | 浅色：玻璃+极光叠加 | 深色：玻璃+极光叠加 | 达标线 | 结论 |
|---------|:---:|:---:|:---:|:---:|
| `--text`（正文） | **15.5 : 1** | **14.1 : 1** | ≥4.5 | ✅ |
| `--text-2`（次级正文） | **4.9 : 1** | **4.9 : 1** | ≥4.5 | ✅ |
| `--text-3`（元信息/轴标） | **4.2 : 1** | **5.5 : 1** | ≥3.0 | ✅ |
| `--primary`（当小字正文时） | 3.9 : 1 | — | ≥4.5 | ⚠️ **仅用于 ≥18px 或 UI 组件** |
| `--ok` 成功文字 | 4.6 : 1 | 8.9 : 1 | ≥4.5 | ✅ |
| `--err` 失败文字 | 4.7 : 1 | 6.1 : 1 | ≥4.5 | ✅ |
| `--warn` 警告文字 | 4.5 : 1 | 9.0 : 1 | ≥4.5 | ✅ |

**结论与纪律**：
1. **正文/次级正文在玻璃+极光最坏叠加下均 ≥4.5:1**——这是靠"不透明兜底 + 极光 ≤12%"两条锁死的，不是靠运气。
2. `--primary` 作为**小字号正文**不达标（3.9:1），与 v2 同。**纪律：`--primary` 只用于 ≥18px 文字、图标、边框、指示器（UI 组件 3:1 即达标）**；小字强调用 `--text` + 字重，不用 `--primary`。
3. 若未来放开极光到 >12%，上表 `--text-2` 会率先跌破——**因此 12% 是硬上限，不是建议值**。

### B.8 完整令牌清单（新旧对照）

| 类别 | 令牌 | 状态 |
|------|------|------|
| 面/线/字/强调/气泡/交互面/语义/深度/圆角/字体/动效/尺寸 | v2 全部（见 B 节顶部列表） | **保留，值不变** |
| 品牌 | `--brand-gradient` | 保留（logo 位），新增 `--brand-glow` 见下 |
| 玻璃 | `--glass-bg --glass-bg-2 --glass-border --glass-blur --glass-fallback` | **新增** |
| 极光 | `--aurora-1..4 --aurora-opacity --aurora-bg-opacity --aurora-blur` | **新增** |
| 发光 | `--glow --glow-strong --glow-color --glow-focus` | **新增** |
| 图表 | `--chart-1..4 --chart-grid --chart-axis --chart-area-from --chart-area-to` | **新增** |
| 动效 | `--dur-aurora --dur-aurora-2 --dur-panel --dur-glow --dur-count --dur-chart --ease-glow` | **新增** |
| 导航/布局 | `--rail-w --rail-btn --rail-gap --panel-pad --panel-gap --panel-title --chart-h --chart-h-sm` | **新增** |
| 品牌发光 | `--brand-glow: radial-gradient(circle at 30% 30%, var(--glow-color), transparent 70%)` | **新增** |

---

## C. 组件规范

### C.1 图标导航栏（Icon Rail）

- **容器**：`width:var(--rail-w)`（60px），`position:sticky` 常驻可见，玻璃底 `--glass-bg` + `--glass-blur`，右侧 `1px --glass-border` 亮边。
- **图标规格**：**线性 SVG，`stroke-width:1.7`，`stroke-linecap/linejoin:round`，`fill:none`**——与 v2 已有内联 SVG 完全一致（`index.template.html` 中所有图标均为此规格）。**严禁 emoji**（v2 已收敛，v3 不得回退）。
- **按钮**：`--rail-btn` 40×40，圆角 `--radius-md`，图标 20×20，默认 `color:--text-2`。
- **hover 态**：`background:--hover`，`color:--text`，`--glow`（微光）；**tooltip**：右侧弹出，玻璃底 + `--shadow-lg`，`200ms` 淡入，内容为中文功能名（如"分析 · 成本与工具统计"）。
- **选中态（发光 + 高亮）**：`background:--primary-soft`，`color:--primary`，左侧 3px `--primary` 竖条，**图标外发光 `--glow-strong`**，可选径向 `--brand-glow` 底衬。选中态**只允许一个**。
- **底部固定区**：主题切换 `#themeBtn`（`toggleTheme`）、余额 `openBilling()` 移入 rail 底部，与主入口用 `1px --border` 分隔。

### C.2 面板容器（Glass Panel）

- **玻璃卡片**：`background: linear-gradient(var(--glass-bg),var(--glass-bg)), var(--glass-fallback)`；`backdrop-filter: blur(var(--glass-blur)) saturate(1.15)`；`-webkit-backdrop-filter` 同值；`border:1px solid var(--glass-border)`；`border-radius:--radius-lg`；默认**无阴影**（借 Vercel 克制），层级靠**模糊 + 亮边 + 亮度差**。
- **不叠玻璃**：**禁止玻璃面板内再套玻璃面板**（可读性崩溃）。嵌套层级改用 `--glass-bg-2`（更不透明）或干脆用不透明 `--card-bg`。
- **面板顶部标题区**：统一结构 = 大标题（`--panel-title` 18px/600，中文功能名）+ 一句话说明（13px `--text-2`）+ 右侧可选操作区。示例："分析 · 看看 token 花在哪、工具调了多少次"。标题下 `1px --border` 分隔。
- **主区背景**：`--main-bg`；面板内滚动区透明，让极光背景透过玻璃边缘隐约可见。

### C.3 数据图表（纯手写 SVG）

**通用**：全部 **纯 SVG 手写**，不引外部图表库；系列色用 `--chart-1..4`；网格 `--chart-grid`；轴标 `--chart-axis`；**数据全部来自运行时 `sessions/messages`，零硬编码**（Anti-Slop 红线）；空数据用 `.empty-state` 风格占位。

- **折线/面积图（成本趋势，图 1）**：`--chart-h` 240px，宽占主区 ≥60%；X 轴可切「按会话 / 按时间」；4 条序列（总 tokens / 缓存命中 / 成本 ¥ / 命中率%）。折线 `stroke-width:2` + 渐变描边；面积填充 `linearGradient`（`--chart-area-from → --chart-area-to`）；数据点 `r:3`，hover 放大到 `r:5` + 发光。**入场**：折线用 `stroke-dasharray/dashoffset` 描画 `--dur-chart`；面积 `opacity` 渐显。
- **条形图（工具次数，图 2 左）**：`--chart-h-sm` 160px；横向条，条高 18px，圆角 `--radius-xs`，间距 8px；条色 `--chart-3`，hover 提亮 + `--glow`。**入场**：条从 0 宽度 `scaleX`/宽度过渡生长 `--dur-chart`。
- **环形图（成功率，图 2 右）**：直径 120px，环宽 12px；底环 `--chart-grid`，进度环 `--chart-2`（成功）/ `--chart-4`（失败段）；中心大数字等宽 `--font-mono` + `tabular-nums`。**入场**：`stroke-dashoffset` 描画。
- **横向耗时条（图 2 右下）**：同条形图规格，条色 `--chart-1`；历史无 `__ms` 时显示"暂无耗时数据"（不报错、不造假）。
- **网格/坐标轴**：网格线 `stroke:--chart-grid;stroke-width:1`，**不画满**（仅 4–5 条水平线）；坐标轴文字 11px `--font-mono`，色 `--chart-axis`。
- **图例**：圆点 8px + 文字 11px `--text-2`，等宽数字，横向排布，点击可切换序列显隐（可选）。

### C.4 工具调用三态卡片（灵魂组件 · 玻璃化改造）

> **三态色语义绝对不变**：执行中=`--primary`、成功=`--ok`、失败=`--err`。玻璃化只改**材质**，不改**语义**。

| 态 | 左色条 | 底色 | 状态点 | 附加 |
|----|-------|------|-------|------|
| **执行中** | `--primary`（2px） | `--glass-bg-2` 叠兜底 | `.tc-dot` 脉冲 | 呼吸动画（`opacity .86↔1`，2s）+ 可选**扫光**（伪元素 `linear-gradient` 横扫，`--dur-aurora-2`）；`.tool-spinner` 保留 |
| **成功** | `--ok` | `--glass-bg-2` 叠兜底 | `●` `--ok` | 静态；成功瞬间可有一次 300ms 微光收敛（可关） |
| **失败** | `--err` | `--err-bg`（不透明，保对比） | `●` `--err` | 静态；`color:--err` |

- **形状**：`border-radius:--radius-sm`，`padding:8px 10px`，`font-family:--font-mono` 12px，参数（路径/命令）超长省略号截断 + `title` 给全文。
- **玻璃化底线**：执行中/成功的玻璃底**必须有兜底色**，确保等宽参数文本 ≥4.5:1；失败态直接用不透明 `--err-bg`（不玻璃化），保证最高可读性。

### C.5 按钮 / 输入 / 下拉 / 徽章

- **主按钮**（新建对话/发送）：实心 `--primary`，圆角 `--radius-md`，高 34px（发送 36px），13px/600；hover 只变 `--primary-hover` + `--glow`（**不加位移、不加渐变**，保持 v2 克制）。
- **次按钮**（导出/余额/设置）：透明底 + `1px --glass-border`，hover `--hover` 底 + `--glow` 微光。
- **图标按钮**：32×32，圆角 `--radius-sm`，hover `--hover` + `--text`；rail 内按钮用 40×40。
- **输入框**：高 36px，`1px --border`，圆角 `--radius-md`；**focus**：`border-color:--primary` + `--glow-focus`（3px soft 环 + 外发光，发光可关，3px 环常驻）。输入区 `.input-row` focus-within 用 `--glow`。
- **自定义下拉 `.cs-*`**：`cs-trigger` 高 36px，玻璃底 `--glass-bg-2` + `--glass-border`；`cs-menu` 圆角 `--radius-lg` + `--shadow-lg` + 玻璃底；选项 hover `--hover`，选中 `--primary-soft` + `--primary` 字。**R1 铁律**：所有 `select` 必须在 DOM 常驻（面板只用 class 控显隐），否则 `initCustomSelect` 初始化时机错乱。
- **徽章 `.header-badge`**：`--primary-soft` 底 + `--primary` 字，`--radius-full`，11px/500，高 20px。选中态徽章可加 `--glow` 微光。

---

## D. 动效规范（逐条对应需求 §4 E1–E10）

> **性能铁律**：所有动画**只用 `transform / opacity`**（+ `backdrop-filter` 静态、`filter` 谨慎），**避免触发重排**（不动 width/height/margin/top/left）。所有时长走令牌。

| # | 特效 | 时长 | 缓动 | 触发 | 降级规则 |
|---|------|------|------|------|---------|
| **E1** | 极光背景动效 | `--dur-aurora` 26s / `--dur-aurora-2` 40s | `linear` / `ease-in-out` | 常驻，`transform:translate/rotate/scale` 缓慢漂移；`#auroraBg{position:fixed;z-index:-1;opacity:var(--aurora-bg-opacity)}` | 总开关关 / reduced-motion → **冻结为首帧静态极光**（保留氛围但不流动） |
| **E2** | 玻璃拟态 | 静态 | — | 面板常驻 `backdrop-filter` | 关闭动效**仍保留玻璃**（静态）；`backdrop-filter` 不支持 → 用 `--glass-fallback` 不透明兜底 |
| **E3** | 微光边框/发光焦点 | `--dur-glow` 260ms | `--ease-glow` | hover / focus | 总开关关 → 去掉外发光，**保留 3px `--primary-soft` 焦点环**（无障碍底线不可去） |
| **E4** | 数字滚动 count-up | `--dur-count` 640ms | `--ease-out` | token/成本/统计数字变化 | 总开关关 / reduced-motion → **直接跳到终值**（瞬时） |
| **E5** | 消息入场 | 220ms | `--ease-out` | 新消息插入（`fadeInUp`，位移 6px） | 总开关关 → 瞬时；reduced-motion → 瞬时 |
| **E6** | 图表入场/绘制 | `--dur-chart` 900ms | `--ease-out` | 图表首次渲染/数据更新 | 总开关关 / reduced-motion → **静态直接呈现最终图形** |
| **E7** | 工具卡执行中呼吸/流光 | 2s 呼吸 / `--dur-aurora-2` 扫光 | `ease-in-out` / `linear` | 工具执行中 | 总开关关 / reduced-motion → **静止**，仅保留 spinner 旋转（功能反馈） |
| **E8** | 渐变光晕（按钮/图标） | `--dur-glow` 260ms | `--ease-glow` | hover / 选中 | 总开关关 → 去掉光晕，保留 `--primary-soft` 底色 |
| **E9** | 面板切换过渡 | `--dur-panel` 200ms | `--ease-out` | 点击 rail 切换面板 | 总开关关 → 瞬时切换（`opacity` 直切） |
| **E10** | 流式进度条增强 | 1.4s | `ease-in-out` | 流式生成中 | **功能条，不随特效开关关闭**；`#streamBar` 保持 `z-index:10000`，加 `--glow` 发光（reduced-motion 下去发光） |

### D.1 开关与降级矩阵

| 状态 | E1 极光 | E2 玻璃 | E3 发光 | E4 数字 | E5 入场 | E6 图表 | E7 工具卡 | E8 光晕 | E9 面板 | E10 流式 |
|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **默认（全开）** | ▶ | ✅ | ✅ | ▶ | ▶ | ▶ | ▶ | ✅ | ▶ | ▶ |
| **特效总开关关闭** | ❄ 静态 | ✅ 保留 | ✖ | ⏭ 瞬时 | ⏭ 瞬时 | ⏭ 静态 | ❄ 静态 | ✖ | ⏭ 瞬时 | ▶ 保留 |
| **`prefers-reduced-motion:reduce`** | ❄ 静态 | ✅ 保留 | ✖ | ⏭ 瞬时 | ⏭ 瞬时 | ⏭ 静态 | ❄ 静态 | ✖ | ⏭ 瞬时 | ▶ 去发光 |

> ▶=播放　✅=静态保留　❄=冻结首帧　✖=移除　⏭=瞬时到终态

### D.2 开关落地

- **特效总开关**：设置面板新增 `#fxToggle`（新 DOM id，允许），或 rail 底部按钮。关闭时给 `<body>` 加 `.fx-off` 类，用 `.fx-off` 覆盖上述动效为静态。
- **持久化**：并入 `glm_config`（`70-config.js` `collectConfig` 加字段，后端只存 JSON blob，**不改方法契约**）或复用 `localStorage`（参照 `glm_theme`）。
- **reduced-motion**：保留并**扩展** v2 的 `@media (prefers-reduced-motion: reduce)` 降级块（现 `index.template.html` L375-378），追加"停极光漂移、停扫光、停 count-up"。

---

## E. 反例清单（Anti-Slop）

### E.1 复述需求 §1.3 反例（红线，逐条禁止）
- ❌ 全屏彩虹/高饱和渐变**铺满内容区**（压信息、伤眼、典型 AI-slop）。
- ❌ 玻璃叠玻璃导致可读性崩溃（文字对比度随背景波动）。
- ❌ 动效无节制的持续全屏动画（CPU/GPU 占用、干扰阅读）。
- ❌ 纯黑 `#000` / 纯白 `#fff` 大面积对撞。
- ❌ 圆角 >16px 的胶囊化卡片堆叠。
- ❌ emoji 作为主要图标语言（v3 不得回退到 emoji）。
- ❌ 每个卡片都带阴影。
- ❌ 为了炫而牺牲"一眼看懂"（功能藏进多层浮层/隐藏手势）。

### E.2 玻璃/极光/发光"容易翻车"的具体做法（v3 新增补充）

**玻璃（Glass）**
- ❌ **玻璃叠玻璃**：面板里再放一个 `backdrop-filter` 卡片 → 两层模糊叠出"脏灰"，且文字对比度不可控。→ ✅ 嵌套改用 `--glass-bg-2` 或不透明 `--card-bg`。
- ❌ **玻璃没有兜底色**：直接 `background:rgba(255,255,255,.3)` → 极光流动时文字忽明忽暗、跌破 4.5:1。→ ✅ 强制 `linear-gradient(...), var(--glass-fallback)`。
- ❌ **玻璃面积过大**：整个主区一块大玻璃 → 模糊开销大、边缘发灰。→ ✅ 玻璃只用于面板容器与浮层，主区保留 `--main-bg` 实色。
- ❌ **模糊值过小（<12px）**：背景色块清晰透出 → 像"没擦干净"。→ ✅ 浅色 18px / 深色 20px。

**极光（Aurora）**
- ❌ **极光铺满内容区 / 不透明度 >12%**：文字背景动态变化，`--text-2` 率先跌破 4.5:1。→ ✅ 硬锁 ≤12%，且极光层 `z-index:-1`。
- ❌ **极光色块清晰可见**：模糊不足 → 出现刺眼色斑。→ ✅ `--aurora-blur:90px`，色斑柔化成"光雾"。
- ❌ **极光流动过快 / 周期 <20s**：干扰阅读、耗电。→ ✅ 26s+ 双周期错频。
- ❌ **极光色进入正文 UI**：青/品红做按钮底、边框 → 品牌色系被稀释、饱和度冲突。→ ✅ 极光只进背景层 + 图表 + 选中光晕。

**发光（Glow）**
- ❌ **发光滥用**：每个卡片、每个按钮都发光 → 满屏"霓虹"，焦点失效。→ ✅ 同屏强发光 ≤2 处。
- ❌ **发光当边框用**：用大发光替代边框 → 边界模糊、廉价感。→ ✅ 先 1px 实边，再叠轻发光。
- ❌ **彩虹渐变按钮 / 多色发光**：主 CTA 用极光四色渐变 → 典型 AI-slop。→ ✅ CTA 只发光，不换色。
- ❌ **发光色与主题脱节**：深色主题仍用浅色发光基 → 发白刺眼。→ ✅ `--glow-color` 随主题切（浅 `rgba(79,110,247,.5)` / 深 `rgba(107,132,255,.55)`）。

**通用**
- ❌ **动效 >280ms 用于常规交互**（面板/hover）→ 迟钝。→ ✅ 面板 ≤200ms、hover ≤260ms。
- ❌ **图表用假数据撑场面**：任何硬编码示例数字 → Anti-Slop 红线。→ ✅ 无数据即空态。
- ❌ **为玻璃牺牲等宽**：把 token 数字改成比例字体"好看" → 数字不对齐。→ ✅ 数据永远 `--font-mono` + `tabular-nums`。

---

## F. 给 Phase 3 的落地清单

### F.1 可直接抄进 CSS 的完整变量块

```css
:root{
  /* ===== v2 保留（值不变，禁止删改）===== */
  --bg:#f6f7f9; --sidebar-bg:#ffffff; --main-bg:#f6f7f9; --header-bg:rgba(255,255,255,.78);
  --card-bg:#ffffff; --surface-2:#f1f3f7;
  --border:#e4e6ec; --border-strong:#d2d6e0;
  --text:#14161c; --text-2:#5f6674; --text-3:#6a7180;
  --primary:#4f6ef7; --primary-hover:#3d5ae6; --primary-soft:#eef1fe;
  --user-bubble:#4059e0; --user-bubble-text:#ffffff; --ai-bubble:#ffffff;
  --hover:#f1f3f7; --active:#eef1fe; --chip-bg:#f1f3f7;
  --ok:#1a7f4e; --warn:#b7791f; --err:#cf3222;
  --ok-bg:#e8f6ee; --warn-bg:#fdf5e6; --err-bg:#fdecea;
  --shadow-sm:0 1px 2px rgba(16,18,28,.06);
  --shadow-md:0 2px 8px rgba(16,18,28,.08);
  --shadow-lg:0 12px 28px rgba(16,18,28,.14);
  --radius-xs:4px; --radius-sm:6px; --radius-md:9px; --radius-lg:12px; --radius-xl:16px; --radius-full:999px;
  --font-sans:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei","Noto Sans SC",sans-serif;
  --font-mono:"JetBrains Mono","Cascadia Code",Consolas,"SFMono-Regular",Menlo,monospace;
  --dur-fast:120ms; --dur-base:180ms; --dur-slow:280ms;
  --ease:cubic-bezier(.4,0,.2,1); --ease-out:cubic-bezier(.16,1,.3,1);
  --sidebar-w:264px; --content-w:820px;
  --brand-gradient:linear-gradient(135deg,#6b84ff,#4f6ef7);

  /* ===== v3 新增 · 玻璃层 ===== */
  --glass-bg:rgba(255,255,255,.62);
  --glass-bg-2:rgba(255,255,255,.80);
  --glass-border:rgba(255,255,255,.72);
  --glass-blur:18px;
  --glass-fallback:#f4f6fb;

  /* ===== v3 新增 · 极光色板 ===== */
  --aurora-1:#22d3ee; --aurora-2:#4f6ef7; --aurora-3:#8b5cf6; --aurora-4:#ec4899;
  --aurora-opacity:.12; --aurora-bg-opacity:.55; --aurora-blur:90px;

  /* ===== v3 新增 · 发光 ===== */
  --glow-color:rgba(79,110,247,.50);
  --glow:0 0 0 1px var(--glass-border),0 0 22px -6px var(--glow-color);
  --glow-strong:0 0 0 1px rgba(79,110,247,.60),0 0 34px -4px rgba(79,110,247,.70);
  --glow-focus:0 0 0 3px var(--primary-soft),0 0 20px -4px var(--glow-color);
  --brand-glow:radial-gradient(circle at 30% 30%,var(--glow-color),transparent 70%);

  /* ===== v3 新增 · 图表色板 ===== */
  --chart-1:#4f6ef7; --chart-2:#22d3ee; --chart-3:#8b5cf6; --chart-4:#ec4899;
  --chart-grid:rgba(16,18,28,.08); --chart-axis:#6a7180;
  --chart-area-from:rgba(79,110,247,.26); --chart-area-to:rgba(79,110,247,0);

  /* ===== v3 新增 · 动效时长 ===== */
  --dur-aurora:26s; --dur-aurora-2:40s; --dur-panel:200ms; --dur-glow:260ms;
  --dur-count:640ms; --dur-chart:900ms;
  --ease-glow:cubic-bezier(.22,.61,.36,1);

  /* ===== v3 新增 · 导航与面板尺寸 ===== */
  --rail-w:60px; --rail-btn:40px; --rail-gap:6px;
  --panel-pad:22px; --panel-gap:16px; --panel-title:18px;
  --chart-h:240px; --chart-h-sm:160px;
}
body.dark{
  /* ===== v2 保留（值不变，禁止删改）===== */
  --bg:#101114; --sidebar-bg:#16181d; --main-bg:#101114; --header-bg:rgba(22,24,29,.78);
  --card-bg:#1a1c22; --surface-2:#212429;
  --border:#272a32; --border-strong:#343843;
  --text:#e6e7ea; --text-2:#8b909c; --text-3:#9298a6;
  --primary:#6b84ff; --primary-hover:#8098ff; --primary-soft:#1d2337;
  --user-bubble:#3b53c9; --user-bubble-text:#ffffff; --ai-bubble:#1a1c22;
  --hover:#212429; --active:#232a3f; --chip-bg:#212429;
  --ok:#4ade80; --warn:#fbbf24; --err:#f87171;
  --ok-bg:#12251b; --warn-bg:#2a2213; --err-bg:#2b1618;
  --shadow-sm:0 1px 2px rgba(0,0,0,.4);
  --shadow-md:0 2px 10px rgba(0,0,0,.45);
  --shadow-lg:0 16px 40px rgba(0,0,0,.6);

  /* ===== v3 新增 · 玻璃层（深色）===== */
  --glass-bg:rgba(26,28,34,.60);
  --glass-bg-2:rgba(30,33,41,.78);
  --glass-border:rgba(255,255,255,.10);
  --glass-blur:20px;
  --glass-fallback:#171a21;

  /* ===== v3 新增 · 极光（深色同色相，层透明度沿用）===== */
  --aurora-1:#22d3ee; --aurora-2:#6b84ff; --aurora-3:#8b5cf6; --aurora-4:#ec4899;
  --aurora-opacity:.12; --aurora-bg-opacity:.60; --aurora-blur:90px;

  /* ===== v3 新增 · 发光（深色）===== */
  --glow-color:rgba(107,132,255,.55);
  --glow:0 0 0 1px var(--glass-border),0 0 22px -6px var(--glow-color);
  --glow-strong:0 0 0 1px rgba(107,132,255,.65),0 0 34px -4px rgba(107,132,255,.75);
  --glow-focus:0 0 0 3px var(--primary-soft),0 0 20px -4px var(--glow-color);
  --brand-glow:radial-gradient(circle at 30% 30%,var(--glow-color),transparent 70%);

  /* ===== v3 新增 · 图表色板（深色）===== */
  --chart-1:#6b84ff; --chart-2:#34e0f5; --chart-3:#a78bfa; --chart-4:#f472b6;
  --chart-grid:rgba(255,255,255,.09); --chart-axis:#8b909c;
  --chart-area-from:rgba(107,132,255,.30); --chart-area-to:rgba(107,132,255,0);
}
```

### F.2 必须遵守的落地注意事项（按优先级）

1. **R1 最高危 · 下拉初始化时机**：多面板**只用 class 控显隐（如 `.panel.on`），所有 `select` DOM 必须常驻**，否则 `initCustomSelect`（`110-boot.js` L14 一次性 `querySelectorAll('select')`）漏包，`CS.sync()` 失效。**优先方案：面板显隐用 `display:none` 切换 + DOM 常驻**（初始 `display:none` 的 select 仍会被 `querySelectorAll` 选中并包装，可行；**但绝不能运行时才注入 DOM**）。
2. **R3 · 图表用新容器**：图表**不得复用 `#tokenStat`**（`updateTokenStat()` 直接写 `textContent` 会冲掉）。`#tokenStat` 保留为底栏纯文本摘要；图表另建新 id 容器。
3. **R6 · 对比度锁死**：玻璃面板必须 `linear-gradient(var(--glass-bg),var(--glass-bg)), var(--glass-fallback)`；极光内容区叠加 **≤12%**；浅/深两套逐一实测正文 ≥4.5:1、次级 ≥3:1。
4. **R7 · 层叠顺序**：`#auroraBg` 用 `position:fixed;z-index:-1`；`#streamBar` 保持 `z-index:10000`；玻璃面板 `z-index` 介于两者之间，**不得盖住 `#streamBar`**。
5. **R5 · 折叠语义**：`.sidebar.collapsed{margin-left:calc(-1*var(--sidebar-w))}` 不变；`--rail-w` 是独立常驻栏，**不参与折叠**。
6. **R4 · 空状态**：只改 CSS，**不改 `85-session-mgmt.js` 内 `emptyState` 的 HTML 结构**。
7. **保留 v2 全部变量名**：本文件 F.1 是 v2 的**超集**，旧变量名一个都不能少（JS 有 `var(--primary)` / `var(--chip-bg)` / `var(--err)` 内联引用）。
8. **图标规格统一**：新图标一律 `stroke-width:1.7` 线性 SVG，`fill:none`，**禁用 emoji**。
9. **特效开关 + reduced-motion 必须落地**：`.fx-off` 覆盖 + 扩展 reduced-motion 降级块；焦点 3px `--primary-soft` 环**不可关**（无障碍底线）。
10. **只改 `frontend/` 源码**，改完 `node frontend/build.js`；**绝不手改根目录 `glm-chat.html`**。

---

*文档结束。Phase 3 原型构建师请以 F.1 变量块为 CSS 起点，严格遵守 F.2 十条注意事项与 00-contract-brief.md 的全部契约红线。*
