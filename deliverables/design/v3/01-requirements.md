# GLM-Chat UI 重构 v3 · 需求摘要（Phase 1 · 需求发现）

> 产出人：需求发现分析师 **许明需（Xu）**
> 版本：v3（在 v2「Linear/Vercel 专业工具风」基础上，按用户新选定方向做**炫科技风整体 UI 重构**）
> 依据（均为实际读到的文件，未臆造）：
> `deliverables/design/00-contract-brief.md`、`01-requirements.md`、`02-design-system.md`、`04-critique.md`；
> `frontend/index.template.html`；`frontend/src/{00-state,05-bridge,10-custom-select,15-theme,25-tool-exec,55-tool-route,60-agent-loop,65-session-store,70-config,75-token-stat,80-utils,85-session-mgmt,100-send,110-boot}.js`
> 一句话需求：**在一个已能跑、且前后端必须保持完全联通的 Windows 桌面 AI Agent 客户端上，把 v2「克制工具风」整体换成「现代科技感·炫」——玻璃拟态 + 极光渐变 + 微光边框 + 多面板图标导航 + 数据图表 + 拉满动效（可关），且一眼看懂功能。**

---

## 0. 事实基线（本次需求判断的锚点，非臆测）

| 事实 | 来源（文件:位置） |
|------|------------------|
| 单窗口 pywebview 桌面应用，`body` 100vh flex，固定侧栏 + 弹性主区 | `index.template.html` L66、L81、L175 |
| 侧栏 `.sidebar` 宽 `--sidebar-w:264px`，折叠靠 `.sidebar.collapsed{margin-left:-264px}`，由 `toggleSidebar()` 切换 | L81-84、`100-send.js` L133 |
| 全部颜色走 `:root` / `body.dark` 两套 CSS 变量 | L17-64 |
| 后端调用统一走 `callApi(name,argsArray,timeoutMs)` → `window.pywebview.api[name](...args)` | `05-bridge.js` L8-18 |
| token/成本计算纯前端：`calcUsage(messages)` 遍历 `m.usage` 累加 | `75-token-stat.js` L2-20 |
| 单价表 `MODEL_PRICE`：flashx `{in:2,out:7,cache:0.57}`、flash `{in:0.8,out:2.8,cache:0.23}`（元/百万 token） | `75-token-stat.js` L2-5 |
| 每条 assistant 消息的 `m.usage = {prompt_tokens, completion_tokens, total_tokens, prompt_tokens_details:{cached_tokens}, model}` | `60-agent-loop.js` L220 |
| 会话数组 `sessions[]`（`{id,title,createdAt,updatedAt,messages[]}`），经 `get_sessions`/`save_sessions` 持久化 | `65-session-store.js`、`110-boot.js` L92 |
| 工具调用记录在消息里：assistant 消息含 `.tool_calls[]`，其后紧跟 `role:'tool'` 消息含 `{tool_call_id,content,__tool:name}` | `60-agent-loop.js` L219-227、L459-464 |
| 工具结果 `content` 是 JSON 字符串：`{ok|error|skipped|output|info...}` | `25-tool-exec.js` 全、`60-agent-loop.js` L417-429 |
| 自定义下拉：`loadAll()` 时对 `document.querySelectorAll('select')` 执行 `initCustomSelect`，把 select 包进 `.cs`，并加 `.cs-src` 隐藏 | `10-custom-select.js` L3-33、`110-boot.js` L14 |
| 主题持久化 `localStorage['glm_theme']`；配置持久化 `localStorage['glm_config']` + `save_config` | `15-theme.js` L12、`70-config.js` L42-48 |
| 有 `prefers-reduced-motion: reduce` 降级块 | `index.template.html` L375-378 |
| v2 已修复 `libs/` 引用（marked/purify/highlight 均存在） | `04-critique.md` §0 |

---

## 1. 五维度需求摘要

| 维度 | v3 结论 |
|------|---------|
| 场景 | Windows 桌面客户端（pywebview 单窗口）；本次新增**左侧图标导航栏 + 多面板**结构 |
| 受众 | 重度使用 AI Agent 的开发者 / 技术用户（同 v2，见下） |
| 调性 | **现代科技感·炫**：玻璃拟态 + 极光渐变 + 微光边框 + 发光焦点；**但必须保留 v2 已建立的"技术数据等宽、状态即语言"的专业底色** |
| 品牌 | 保留 GLM Chat 名称/logo 语义与蓝紫主色系（`#4f6ef7` 系），升级为**发光·渐变版**品牌位 |
| 规模 | 单窗口多面板（图标栏 + 主区 + 可切换面板 + 图表面板）；桌面尺寸，无移动端断点 |

### 1.1 场景（Surface）
- **形态不变**：单窗口桌面应用，非网页、非移动端。改造后新增**左侧窄图标栏（icon rail，建议 56–64px）** + **主区（可含多面板切换）**。
- **需承载的视图/面板**（全部来自现有 DOM，见 §5 红线）：
  1. **对话面板**：消息流 `.chat-container`、输入区、工具调用卡片（灵魂组件）。
  2. **会话面板**：会话列表 `#sessionList`（切换/删除）。
  3. **成本 / 数据分析面板（v3 新增，最重要增量）**：成本/token 趋势图 + 工具调用统计图。
  4. **工作区面板**：`.ws-card` 文件夹绑定、`#toolMode` 权限档、生效路径条。
  5. **设置面板**：`#settingsPanel` 4 组 `.set-block`（API Key / 模型与推理 / 省 token / 生成参数 / 角色与联网）。
- **导航逻辑**：图标栏点击切换主区显示的面板；「一眼看懂功能」= 每个图标有 tooltip + 选中态高亮 + 面板顶部有标题与一句话说明。

### 1.2 受众（Audience）
沿用 v2 结论（证据来自代码，未变）：
- 需自配 **API Key**（`#apiKey`）→ 技术用户、理解 API 计费。
- 绑定**工作区文件夹**（`#wsEnabled/#wsSel/#browseWs`）+ **工具权限三档**（`#toolMode`）→ 让 AI 直接操作本机，对权限/可信度敏感。
- **token 成本 + 单会话预算**（`#sessionBudget/#saverLevel/#shotQuality`）→ 对"花多少钱"高度敏感。
- **长会话多轮**（历史压缩、缓存命中提示）→ 需要趋势可视化来判断"钱花在哪、哪次调用最贵"。

**核心诉求（v3 新增第 6 条）**：
1. 一眼看懂功能（信息架构清晰）——**本次最高优先级**。
2. 工具调用与流式过程可见（三态：执行中/成功/失败）。
3. 成本可控可感知，且**能看趋势**（v3 新增图表）。
4. 长时间盯屏不累眼（**注意：炫风与护眼存在天然张力，见 §1.3 反例**）。
5. 操作可信（破坏性操作有清晰状态暗示）。
6. 有美感、符合最新行业设计标准（用户原话）。

### 1.3 调性（Tone）——「现代科技感·炫」的具体视觉定义

**必须落地（用户明确选定）**：
- **玻璃拟态（Glassmorphism）**：面板/浮层用半透明底 + `backdrop-filter: blur()`（现有 `.header` 已用 `blur(14px)`）+ 1px 半透明亮边；层级靠模糊与亮度差，而非纯阴影。
- **极光渐变（Aurora）**：背景用缓慢流动的多色渐变光晕（青/蓝/紫/品红），**作为"氛围层"而非主体**；建议放在独立 `position:fixed` 的 `::before` 或独立 `#auroraBg` 层，`z-index:-1`，不遮挡内容。
- **微光边框（Glow border）**：卡片/按钮/焦点态用 1px 渐变描边或 `box-shadow` 外发光（`0 0 0 1px rgba(...) , 0 0 24px -6px var(--glow)`）。
- **发光强调**：主按钮/选中项/数据高亮带 glow；图表线条用渐变 + 辉光。
- **保留专业底色（不可丢）**：技术数据（路径/命令/token 数字）继续 `--font-mono` + `tabular-nums`；工具三态色（ok/warn/err）语义不变；深色仍为默认优选主题（开发者长时盯屏）。

**明确避免（反例清单，来自 v2 审查 + 本次炫风易翻车点）**：
- ❌ **全屏彩虹/高饱和渐变铺满内容区**（会压过信息、伤眼、且是典型 AI-slop）。极光只做背景氛围，且透明度克制（建议主体区叠加 ≤ 12% 不透明度）。
- ❌ **玻璃层叠玻璃层**导致可读性崩溃（背景流动时文字对比度不稳定）——玻璃面板下必须有不透明兜底色，文字对比度**始终 ≥ 4.5:1**。
- ❌ **动效无节制的持续全屏动画**（CPU/GPU 占用、干扰阅读）——背景动效必须**低频、慢速、可关**。
- ❌ **纯黑 `#000` / 纯白 `#fff` 大面积对撞**；❌ 圆角 > 16px 的胶囊化卡片堆叠。
- ❌ **emoji 作为主要图标语言**（v2 已收敛为线性 SVG，v3 不得回退）；❌ 每个卡片都带阴影。
- ❌ 为了炫而牺牲"一眼看懂"——导航与面板切换必须直白，**不可为了酷炫把功能藏进多层浮层/隐藏手势**。

> **张力处理原则**：炫风是"外层氛围 + 交互反馈"，信息主体（文字、数据、工具状态）保持 v2 的克制与高对比。**氛围可以炫，内容必须稳。**

### 1.4 品牌上下文（Brand Context）
- 保留：品牌名 `GLM Chat`、`.brand-logo`（升级为**发光渐变版**）、模型副标题 `#brandModel`、头部徽章 `多模态 Agent`。
- 主色 `#4f6ef7`（浅）/`#6b84ff`（深）**保留为强调色基座**，新增极光辅助色（青/品红）仅用于背景氛围与图表，不进入正文 UI。
- v2 已把渐变收敛到 logo + 空状态图标 2 处；v3 允许重新扩大渐变使用（这是用户选择），但需遵守 §1.3 反例（氛围层允许，内容层克制）。
- **无用户提供的品牌手册**；如需严格品牌规范，须在 Phase 2 前补充。

### 1.5 规模（Scale）
- 单窗口；新增图标导航（≥5 个入口）+ 至少 1 个新面板（数据分析）。无独立路由。
- 改造范围：全局背景层（新增）、导航层（重构）、主区各面板（重排 + 重新皮肤）、消息渲染（工具卡/代码块/成本）、图表面板（新增）。
- 响应式：仅桌面窗口尺寸（窗口缩窄时图标栏可收窄/侧栏可折叠），无移动端断点。

---

## 2. 数据可视化需求（v3 核心增量）

> **总原则**：图表数据**优先全部前端聚合**，严禁为图表新增后端 `js_api` 方法（会破坏 §5 的 43 方法契约）。下面逐图给出**精确数据来源**与**缺口标注**。

### 图 1 · 成本 / Token 趋势图

| 项 | 定义 |
|----|------|
| 图表类型 | 折线/面积图（趋势）+ 可切换「按会话」/「按时间」两种 X 轴 |
| 指标 | ① 总 tokens ② 缓存命中 tokens ③ 实际成本（¥）④ 缓存命中率（%） |
| 数据来源（现成，无需新增后端） | 全局状态 `sessions[]`（`65-session-store.js` 持久化，`110-boot.js` L92 载入）。对每个会话 `s`：`calcUsage(s.messages)` → `{total, cached, cost}`（`75-token-stat.js` L6-20）。逐条消息粒度：`m.usage.total_tokens / prompt_tokens / completion_tokens / prompt_tokens_details.cached_tokens`，单价用 `MODEL_PRICE[m.usage.model]`。 |
| 计算方式 | **纯前端聚合**。按会话：遍历 `sessions` 得每会话 `total/cached/cost`。按时间：用 `s.createdAt`/`s.updatedAt` 排序（或按消息顺序）作 X 轴，Y 轴累加。 |
| 展示位置 | 数据分析面板顶部大图（宽度占主区 ≥ 60%）。 |
| 缺口标注 | ✅ **无缺口，可完全前端聚合**。注意：`saveSessions()` 会把 `sessions` 截断到最多 60 条（`65-session-store.js` L13-15），趋势图时间跨度上限即最近 60 会话；`usage` 数字很小不受 30000 字符串截断影响。 |
| 契约风险 | 若把现有 `#tokenStat`（底栏文本，被 `updateTokenStat()` 直接写 `textContent`）改成图表容器，会与该方法冲突 → **应新增独立图表容器 DOM，保留 `#tokenStat` 原样**（见 §5）。 |

### 图 2 · 工具调用统计图

| 项 | 定义 |
|----|------|
| 图表类型 | ① 按工具名分组的**调用次数条形图** ② **成功率**（环形/百分比） ③ **平均耗时**（横向条） |
| 指标 | 调用次数（count）、成功数、失败/拦截数、成功率（%）、平均/最大耗时（ms） |
| 数据来源（调用次数 + 成功率，现成） | 遍历 `sessions[].messages`：assistant 消息的 `.tool_calls[]`（每个 `{function:{name,arguments}}`）计次数；其后的 `role:'tool'` 消息 `content`（JSON 字符串）判成功失败：`JSON.parse(content)` 后 —— 有 `error` = 失败；有 `skipped` = 被拦截（去重/防误操作）；否则视为成功。`__tool` 字段提供工具名（`60-agent-loop.js` L464）。 |
| 数据来源（耗时，**缺口**） | ⚠️ **现有代码未记录任何工具耗时**：`executeTool`（`25-tool-exec.js`）无计时，消息里也无时间戳字段。 |
| 缺口处理（推荐：前端插桩，不碰后端） | 在 `executeTool` 外包一层 `performance.now()` 计时，把耗时写入结果消息（如新增 `__ms` 字段）。**这是前端改动、不改后端契约**。代价：**仅对本次改动后产生的新工具调用有效**，历史会话无耗时数据 → 图表对历史显示"暂无耗时数据"。 |
| 缺口处理（不推荐） | 新增后端方法（如 `get_tool_stats`）→ **破坏 §5 的 43 方法契约红线，明确禁止**。 |
| 展示位置 | 数据分析面板下半区（左：次数条形图；右：成功率环形 + 耗时条）。 |
| 契约风险 | 解析 `content` 判成败需容错（`content` 可能是非 JSON、被截断、或 `__tool` 缺失）；统计口径要与 `60-agent-loop.js` 的 `skipped`/`error` 判定一致。 |

### 图 3（可选，低优先级）· 文件改动 / 工作日志统计
- 数据来源：`get_worklog`（`100-send.js` L17）、`append_worklog`（写文件/命令成功后追加，`60-agent-loop.js` L399）；`get_memory`/`append_memory`。
- 说明：可展示"AI 改过哪些文件"的清单/计数。属锦上添花，**若工期紧可砍**。

### 图表通用要求
- **纯手写 SVG 或 Canvas**（不引入外部图表库，保持单文件构建、无新依赖；v2 只有 flate/marked/purify/highlight 4 个本地库）。
- 图表配色用主题变量 + 极光辅助色；**深/浅两套主题都必须成立**，网格线/文字对比度达标。
- 图表数据**全部来自真实运行时状态**（`sessions`/`messages`），**禁止硬编码示例数字**（Anti-Slop 红线）。
- 空数据态：无会话或无工具调用时显示友好占位（复用 `.empty-state` 风格），不显示假数据。

---

## 3. 导航重构需求（左侧图标栏 + 多面板）

### 3.1 图标栏入口建议（≥5 个，每个含 SVG 图标 + tooltip + 选中发光态）

| # | 入口 | 图标语义 | 对应面板 | 面板内容（现有 DOM 归属） |
|---|------|---------|---------|--------------------------|
| 1 | **对话** | 对话气泡 | 对话面板（默认） | `.chat-container` + `.input-area` |
| 2 | **会话** | 列表/历史 | 会话面板 | `#sessionList`（含 `newSession/exportChat` 入口） |
| 3 | **分析** | 图表/仪表 | 数据分析面板（新增） | 图 1 + 图 2 容器（新 DOM） |
| 4 | **工作区** | 文件夹 | 工作区面板 | `.ws-card`（`#wsEnabled/#wsBody/#wsSel/#wsInd/#wsEffTag/#wsEffPath/#wsUnbindBtn`）、`#toolMode`、`#effTag/#effPath` |
| 5 | **设置** | 齿轮 | 设置面板 | `#settingsPanel`（4 个 `.set-block`） |
| 6 | **底部** | 主题切换 / 余额 | — | `#themeBtn`（`toggleTheme`）、`openBilling()` 可移入图标栏底部 |

### 3.2 「一眼看懂」的信息架构建议（用户核心诉求）
1. **图标栏常驻可见**（桌面窗口不隐藏），选中项高亮 + 发光；hover 显示中文 tooltip。
2. **每个面板顶部有统一标题区**：大标题（中文功能名）+ 一句话说明（如"分析 · 看看 token 花在哪、工具调了多少次"）。
3. **成本/权限状态在图标栏常驻**（角标或底部小徽章）：把 v2 的"成本显性化"升级为"任意面板都可见"，如底部固定 `#tokenStat` 摘要 + 预算进度环。
4. **保留可折叠侧栏**：图标栏之上或之内，原 `.sidebar` 的会话/工作区内容可折叠展开（`toggleSidebar()` 语义保留）。
5. **不新增隐藏手势**：所有功能通过可见入口到达。

---

## 4. 特效需求清单（逐条 + 开关）

| # | 特效 | 说明 | 是否需开关 | 备注 |
|---|------|------|:---:|------|
| E1 | **极光背景动效** | `#auroraBg` 固定层，多色渐变缓慢流动/漂移（建议 20s+ 循环） | ✅ 必须 | 低频慢速；`z-index:-1`；不遮挡内容 |
| E2 | **玻璃拟态** | 面板/浮层 `backdrop-filter:blur()` + 半透明底 + 1px 亮边 | ⚠️ 建议 | 与 E1 联动；关闭动效时玻璃仍可保留（静态） |
| E3 | **微光边框 / 发光焦点** | 卡片/按钮 hover、input focus 外发光 | ⚠️ 建议 | 与"特效总开关"联动 |
| E4 | **数字滚动（count-up）** | token / 成本 / 统计数字变化时滚动递增 | ✅ 必须 | 尊重 `prefers-reduced-motion` |
| E5 | **消息入场动效** | 新消息 fadeInUp（v2 已有 220ms，可加强） | ⚠️ 建议 | 现有 `fadeInUp` 基础上增强 |
| E6 | **图表入场/绘制动画** | 折线描画、柱状生长 | ✅ 必须 | reduced-motion 时静态呈现 |
| E7 | **工具卡执行中呼吸/流光** | 执行中态扫光/呼吸 | ⚠️ 建议 | 与三态语义一致 |
| E8 | **渐变光晕背景（按钮/图标）** | 主 CTA、选中图标的径向光晕 | ⚠️ 建议 | 克制使用 |
| E9 | **面板切换过渡** | 多面板切换的淡入/滑动 | ⚠️ 建议 | 短时长（≤220ms） |
| E10 | **流式进度条增强** | 保留 `#streamBar` 并加发光 | 否 | 功能条，非装饰 |

**开关规则（硬性）**：
- 提供**至少一个「特效总开关」**（如设置面板内新增 `#fxToggle`，或图标栏底部按钮），关闭后：停 E1/E3/E4/E6/E7/E8/E9，保留必要的功能反馈（E5/E10 降级为瞬时）。
- **必须尊重系统 `prefers-reduced-motion: reduce`**：开启时**无条件**停掉所有装饰动效（现有 L375-378 降级块保留并扩展）。
- 开关偏好持久化：复用 `localStorage`（参照 `glm_theme` 写法）或并入 `glm_config`（`70-config.js` 的 `collectConfig` 加字段，后端只是存 JSON blob，**不改方法契约**）。
- 新增的开关控件会产生**新 DOM id**（允许；契约只禁止删除/改名已有 id）。

---

## 5. 硬约束红线（完整复述 + v3 风险点）

> 以下为 `00-contract-brief.md` 的硬约束，v3 改造**逐条不得违反**。

### 5.1 铁律（§1）
- **永不直接改根目录 `glm-chat.html`**（构建产物）；只改 `frontend/` 源码，再 `node frontend/build.js` 重建。

### 5.2 后端调用契约（§2）——43 个方法，禁止改方法名 / 参数个数与顺序 / 返回值解析
```
set_current_sid set_session_ws append_memory clear_caches set_ws_dir get_memory
append_worklog write_file take_screenshot set_ws_enabled set_clipboard search_replace
save_workspace_file save_sessions save_config run_powershell run_command run_admin_command
read_more read_file pick_folder open_url open_billing open_app move_path make_dir
list_processes list_dir kill_process get_ws_state get_worklog get_sessions get_file_info
get_effective_ws get_config get_clipboard get_api_info delete_session_ws delete_path
copy_path build_tools build_system_prompt append_file
```

### 5.3 DOM 契约（§3）——`getElementById` 依赖的 id 一个都不能丢
```
apiKey attachPreview brandModel chatContainer continueNewBtn ctxMenu effPath effTag
emptyState enableSearch headerTitle liveTokenStat maxTokens modelSelect reasoningEffort
saverLevel searchEngine searchEngineWrap sendBtn sessionBudget sessionList settingsPanel
shotQuality sidebar streamBar systemPrompt tempVal temperature themeBtn tokenStat
toolMode topP topPVal userInput wsBody wsEffPath wsEffTag wsEnabled wsInd wsSel wsUnbindBtn
```
> ⚠️ **发现一处口径差异**：契约简报 §3 标称"40 个 id"，但清单实际为 **41 个**（含 `ctxMenu`、`streamBar`）。以**清单本身**为准，改造时按 41 个全保留。`ctxMenu` 由 `105-context-menu.js` 动态创建（模板可无）；`emptyState` 由 `85-session-mgmt.js` 的 `newSession()/switchSession()` 动态重建，其内部结构固定为：
```html
<div class="empty-state" id="emptyState">
  <div class="empty-icon">✦</div>
  <h2>开始和 GLM 聊天</h2>
  <p>支持文字、图片、视频、文本文件 · 历史记录自动保存</p>
</div>
```

### 5.4 内联 onclick 契约（§4）——函数必须存在且签名不变
```
newSession() exportChat() openBilling()
onFolderEnabled(this.checked) onIndToggle(this.checked) onWsSelect(this.value)
browseWs() unbindSession() toggleSidebar() toggleTheme() toggleSettings()
sendMessage() continueInNewSession()
document.getElementById('imgInput'|'vidInput'|'fileInput'|'zipInput').click()
```

### 5.5 CSS 类契约（§5）——JS 动态创建元素所用类名必须保留并有效样式化
```
.message / .message.user / .message.assistant / .avatar / .content / .content.error
.md-body / .typing-dots / .tool-call-item / .tool-spinner / .toolchip / .tc-head / .tc-label / .tc-meta
.usage-info / .msg-images / .msg-file / .copy-btn / .code-copy / .code-lang
.cs / .cs-trigger / .cs-label / .cs-arrow / .cs-menu / .cs-opt / .cs-opt.on / .cs-src
.ctx-menu / .ctx-menu-item / .sys-tip / .attach-item / .attach-preview
.session-item / .session-item.active / .session-title / .session-time / .session-del / .sidebar-empty
.empty-state / .empty-icon
```

### 5.6 主题变量契约（§6）
- 主题经 `body.dark` 切换（`15-theme.js` / `applyTheme()`），`localStorage['glm_theme']` 存 `light`/`dark`。
- **两套主题都必须成立**。
- 现有变量名**一个都不能删**（JS 有 `var(--primary)` / `var(--chip-bg)` / `var(--err)` 内联引用）：`--bg --sidebar-bg --main-bg --header-bg --card-bg --border --text --text-2 --primary --primary-hover --user-bubble --ai-bubble --hover --active --chip-bg --ok --warn --err --shadow-sm/md/lg`。新增变量可以。

### 5.7 联通缺口（§7）
- v2 已修复 `libs/` 引用（`marked.min.js`/`purify.min.js`/`highlight.min.js` 均存在）。v3 **不得回退**，构建后须验证 `window.marked / DOMPurify / hljs` 可用。

### 5.8 ⚠️ v3 布局重排**新增触及的契约风险点**（本报告重点）
| 风险 | 说明 | 触发条件 | 规避 |
|------|------|---------|------|
| **R1 · 自定义下拉初始化时机（最高危）** | `initCustomSelect` 在 `loadAll()` 里对 `document.querySelectorAll('select')` 一次性执行（`110-boot.js` L14）。若把 `#modelSelect/#toolMode/#searchEngine/#shotQuality/#saverLevel/#reasoningEffort/#wsSel` 等移入**初始 `display:none` 的面板**或**懒加载（后插入 DOM）的面板**，则这些 select 不会被包装、不进 `CS.reg`；`refreshWsCard()` 里的 `CS.sync(sel)`（`80-utils.js` L87）将失效，工作区下拉显示错乱。 | 多面板用 `display:none` 隐藏 + select 在其中；或面板 DOM 运行时才注入 | 面板切换**只用 class 控制显隐、DOM 始终在册**；或改造 `loadAll` 对所有面板的 select 都初始化；改 JS 需回归 `CS.syncAll()` |
| **R2 · 布局迁移丢失 id** | icon rail + 多面板要求把现有元素分组/搬位，任何被搬动的元素其 **id 必须原样保留**（§5.3）。 | 重构 `.sidebar`/`.main` 结构时 | 迁移前列 id 清单，迁移后跑 `check_contract.py` 逐项核对 |
| **R3 · `#tokenStat` 被误当图表容器** | `updateTokenStat()` 直接 `el.textContent = ...` 覆盖内容（`75-token-stat.js` L22-31）。若把 `#tokenStat` 改为图表区，文本会被冲掉/冲突。 | 想复用底栏位置放图表 | **图表用新容器**；`#tokenStat` 保留为纯文本摘要节点 |
| **R4 · `emptyState` 结构** | `newSession()/switchSession()` 用固定 HTML 重建（`85-session-mgmt.js` L21-26）。 | 改空状态样式时若改结构 | 只改 CSS，不改那段 JS 内 HTML 结构 |
| **R5 · `.sidebar.collapsed` 负 margin 与 `--sidebar-w`** | 折叠靠 `margin-left:calc(-1*var(--sidebar-w))`（L84）。新增 icon rail 后若改变侧栏宽度语义，折叠会错位。 | 重排导航宽度 | 新宽度用新变量；折叠逻辑与 `toggleSidebar()` 同步回归 |
| **R6 · 玻璃背景下的对比度** | 极光流动使背景色动态变化，玻璃面板若半透明度过高，文字对比度会**随背景波动跌破 4.5:1**。 | E1+E2 叠加 | 玻璃面板设不透明兜底色 + 限制背景层不透明度；两主题实测对比度 |
| **R7 · `#streamBar` 定位** | `position:fixed;top:0` 的流式条（L76）在多层 z-index 重排后可能被背景层/玻璃层盖住。 | 新增 fixed 背景层 | 背景层 `z-index:-1`；`#streamBar` 保持 `z-index:10000` |
| **R8 · 面板切换与 `isStreaming`** | 生成中若允许切走对话面板，用户会看不到流式输出。 | 多面板切换未考虑流式态 | 生成中锁定/提示或自动跳回对话面板（需求建议，非契约） |

---

## 6. 可验收成功标准（量化）

| # | 标准 | 量化验收 |
|---|------|---------|
| 1 | **联通零回归** | 构建后 `check_contract.py`：DOM id **41/41**、onclick **13/13**、callApi **43/43**、CSS 类 **39/39**、CSS 变量 **≥21 且无删除**、本地库 **4 引用 0 缺失** 全 PASS；能真实收发消息、切会话、读写工作区 |
| 2 | **数据图表真实可用** | 图 1/图 2 渲染数据全部来自运行时 `sessions`，**零硬编码示例数字**；图 2 成功率与 `60-agent-loop.js` 判定口径一致；无数据时显示空态而非假数据 |
| 3 | **工具耗时缺口已闭合** | 新产生的工具调用带 `__ms` 字段，图 2 能显示平均耗时；历史会话显示"暂无耗时数据"而非报错 |
| 4 | **导航一眼看懂** | ≥5 个图标入口，每个有 tooltip + 选中发光态 + 面板标题与一句话说明；新用户 10 秒内能定位"看成本""绑工作区""改设置" |
| 5 | **特效可控且护眼** | 提供特效总开关；`prefers-reduced-motion:reduce` 下所有装饰动效停止；**两主题正文对比度 ≥ 4.5:1**（含玻璃层与极光背景叠加时） |
| 6 | **双主题成立** | `light`/`dark` 两套均无破版、无对比度不达标；玻璃/极光在两套下都协调 |
| 7 | **构建可复现** | 只改 `frontend/`，`node frontend/build.js` 重建出 `glm-chat.html`；未手改产物 |
| 8 | **性能** | 极光/玻璃背景常驻时无明显掉帧（建议用 CSS `transform/opacity` 动画，避免触发重排）；面板切换无明显卡顿 |

---

## 7. 交接给下游（Phase 2 设计系统 / Phase 3 原型构建）

- **建议设计系统方向**：以 v2 的「Modern Minimal × Tech Utility」为**结构底座**（保留等宽数据、三态语言、高对比），叠加 **Glassmorphism + Aurora + Glow** 作为**视觉皮肤层**。参考血统：Vercel（克制）× Raycast（命令感）× 现代 glass UI（如 macOS Sonoma / Arc 浏览器的玻璃质感）。
- **建议原型模板**：桌面 SaaS 多面板 App（icon rail + 主面板 + 数据面板），非营销落地页。
- **Phase 2 令牌必须新增**：玻璃层变量（`--glass-bg/--glass-blur/--glass-border`）、极光色板（青/品红/紫辅助色）、发光变量（`--glow/--glow-strong`）、图表色板（含深/浅两套）、动效时长档（含极光慢循环）；**同时保留全部旧变量名**。
- **Phase 3 构建注意事项（按风险优先级）**：
  1. **R1 最高危**：多面板的 select 初始化时机必须先解决，否则下拉全挂。
  2. **R3**：图表用新 DOM 容器，勿动 `#tokenStat`。
  3. 图 2 的**耗时**需前端插桩 `executeTool`（改 `25-tool-exec.js`，不改后端）。
  4. 特效总开关 + `prefers-reduced-motion` 必须落地。
- **特别提醒**：本产品的**灵魂组件**是「工具调用三态卡片」与「成本/分析仪表」；炫风改造中这两者优先级最高，绝不能因玻璃/渐变而牺牲其状态可辨性与数据可读性。
