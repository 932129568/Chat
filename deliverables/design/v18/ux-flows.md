# Harbor v1.8.0「Agent 能力版」关键交互流程与状态反馈设计

**日期**：2026-10-20
**类型**：交互流程设计（UX Flows & State Feedback）
**基线**：v1.7.0 前端（`frontend/index.template.html` 单文件 + `frontend/src/` 模块化）+ `iteration-plan-v18-agent-2026-10-20.md` + `agent-autonomy-research-2026-10-20.md`
**状态**：v1.0（供原型与联调计划引用；接口清单由主理人另出，本文只标注触点）
**读者**：主理人 / 原型工程师 / 前后端联调

---

## 📌 TL;DR

- **一条铁律**：Agent 的每一个长时间动作（**≥3s**）必须在界面上有可见的等待或进度态——**禁止静默黑箱**。搜索在跑、软件在执行、本地在推理，用户都必须看得见。
- 本文覆盖 **10 个关键流程**：每个流程给出 ① 触发条件 ② 分步流程（用户操作/系统响应/前端状态/后端调用并列）③ 状态机（ASCII）④ 状态反馈设计 ⑤ 中断与取消语义 ⑥ 前后端触点。
- **UI 契约纪律**：所有新组件均为**纯新增 DOM id/class**，既有 41 id/43 callApi/13 onclick/39 类/v2 变量零改动；新 js_api 全部走 `_V12_EXTRA` 隐身通道。
- **版本归属**：流程 1-6 属 v1.8.0；流程 7 属 v1.8.5（A1/A2 权限地基）；流程 8-10 属 v1.9.0（放手版）。本文一并设计以保证原型 DOM 结构与容器复用的一致，**开发排期以版本为准**。

### 版本归属速查

| # | 流程 | 版本 | 核心状态机 |
|---|------|------|-----------|
| 1 | Agent 发起浏览器搜索 | v1.8.0 | understanding → cache/window → extracting → validating → done |
| 2 | 人工接管反爬验证（U1） | v1.8.0 | captcha_detected → takeover → recheck → extracting/aborted |
| 3 | 深度提取（browser_open） | v1.8.0 | loading → extracting → truncating(toolcache) → done |
| 4 | 外部软件调用（software_call） | v1.8.0 | guard → probe → schema → executing(cli/gui/uri) → done |
| 5 | 混合路由会话（H1） | v1.8.0 | understanding → tool_exec → validating → 置信门 → composing |
| 6 | 本地端点降级 | v1.8.0 | available ↔ degraded ↔ unavailable（必提示边界） |
| 7 | L2 任务授权生命周期 | v1.8.5 | no_grant → active(TTL) → revoked/expired |
| 8 | Plan-Act 计划执行 | v1.9.0 | planning → plan_review → acting(todo 五态) → delivering |
| 9 | 批量澄清（clarify） | v1.9.0 | clarify_pending(≤5 问单表单) → planning |
| 10 | 检查点与回滚 | v1.9.0 | creating → active → confirm → rolling → rolled_back |

### 全局反馈组件基线（既有复用，零改动）

| 组件 | 载体 | 用途 |
|------|------|------|
| 工具调用条目 | `.tool-call-item`（spinner → tc-dot，`.done`/`.fail` 类） | 所有工具调用的等待/完成/失败态 |
| 流式进度条 | `#streamBar`（`.on` 类，v4 E10） | 云端流式输出期 |
| toast 四态 | `toast(msg, 'ok'/'warn'/'err'/'info', {stay,pinned})`（18-toast.js） | 短时反馈；err 9s/warn 6.5s/info 4.5s；长流程用 `pinned` 常驻 |
| 模态确认 | `uiConfirm/uiPrompt`（`#modalRoot`，`modal-check` 勾选） | 高危确认、回滚二次确认等 |
| 会话头部状态区 | `#headerStatusZone`（v1.6 T11） | 阶段 chip、分账显示、状态灯 |
| 设置面板 | `#settingsPanel` + `#setNav`（sticky 分区导航，33-set-nav.js 自动生成） | 新设置区块挂载点 |
| 状态灯模式 | `.sb-light`（沙箱状态灯，既有样式） | 本地端点/软件探测状态灯复用同款 |
| 消息流容器 | `#chatContainer` | 计划卡、澄清表单、摘要卡挂载点 |
| 审计查看器 | 28-audit-viewer.js | grant/revoke/degrade 等决策记录可查 |

### 新增组件清单（纯新增，本文定义挂载点）

| 组件 | 前端模块 | DOM 容器（建议 id） | 版本 |
|------|----------|---------------------|------|
| 搜索面板（U1） | `63-search-panel.js` | `#searchPanel`（结果列表/原文预览/接管按钮） | v1.8.0 |
| 软件设置面板（S3） | `64-software-panel.js` | 设置区 `#softwareBlock`（set-block） | v1.8.0 |
| 混合路由配置+分账 | `65-hybrid.js` | 设置区 `#hybridBlock` + `#headerStatusZone` 内 `#hybridLedger` | v1.8.0 |
| L2 授权条+收回 | 新模块或 26-guard.js 扩展 | `#taskGrantBar`（输入区上方常驻） | v1.8.5 |
| 计划卡 | 新模块 | `#planCard`（消息流顶部） | v1.9.0 |
| 澄清表单卡 | 新模块 | `#clarifyCard`（消息流内） | v1.9.0 |

---

## 流程 1 · Agent 发起浏览器搜索（browser_search）`v1.8.0`

**一句话**：Agent 决策调用 `browser_search` → 本地理解补全参数 → 缓存/双窗口/兜底三通道取数 → 提取校验 → 结构化结果入上下文；全过程在工具条目和搜索面板双可见。

### ① 触发条件

- Agent 在对话中调用 `browser_search` 工具（经 `build_tools(role, include_agent=True)` 下发，设置内「浏览器搜索」功能开关开启）。
- 无用户直接入口（工具由模型决策调用）；用户控制点 = 功能开关 + 引擎默认值设置。
- GLM 端点场景与内置 `web_search` 双通道并存（按端点自动选）——工具选择歧义见 Gap-3。

### ② 分步流程

| # | 用户操作 | 系统响应 | 前端状态 | 后端调用 |
|---|---------|---------|---------|---------|
| 1 | 发送消息后等待 | Agent 流式输出中插入工具调用 | 消息流新增 `.tool-call-item`（spinner + 「搜索：query」）；`#streamBar` 持续 | `runAgentLoop` → `executeToolRaw('browser_search')` |
| 2 | — | 本地理解：参数校验/补全（query 改写、engine 建议），5s 预算 | 工具条目标签更新「正在理解检索意图…」；`#searchPanel`（若开）显示阶段 1/4 | `callApi('browser_search')` → `search_service` → H1 本地理解 |
| 3 | — | 缓存查询（同 query TTL 30min 内） | 命中：条目直接完成 | C1 缓存（`search_cache_stats`） |
| 4 | — | 次窗口 `load_url` → 选择器轮询等待（≤8s，抗 SPA） | 面板「正在打开 Bing…」+ 计时；>3s 工具条目附秒表 | `search_browser.load_url` + `evaluate_js` |
| 5 | — | 窗口不可用/超时 → urllib 抓 HTML 兜底（非 JS 引擎可用） | 面板标注「已降级直连抓取」 | urllib |
| 6 | — | 检测到验证页特征 | 转**流程 2**（人工接管） | 适配器特征检测 |
| 7 | — | 提取：引擎适配器纯函数解析 → 原始结果列表 | 面板「正在提取搜索结果…」 | `search_adapters` |
| 8 | — | 过滤/去重（URL 归一）/日期解析/相关性重排 | — | `search_service` |
| 9 | — | `extract=full`？ → 对 Top N 逐个 `browser_open` | 面板「深度提取 N 篇正文…」（转流程 3，总进度可见） | `browser_open` 连锁 |
| 10 | — | V1 本地校验（结果非空？与 query 相关？）→ 不通过则本地改写重试（≤2 次） | 重试时面板标注「校验未过，正在改写检索式重试（1/2）」 | validator + reformulate |
| 11 | 看到结果 | 结构化 JSON（超长走 toolcache 截断）+ 缓存写入 + 审计（op=web_search） | 工具条目完成态「✓ 搜索：query · N 条」+ 结果摘要卡 | 审计 |

### ③ 状态机

```
[触发] Agent 调用 browser_search
   │
   ▼
┌────────────────┐  本地可用且 ≤5s 完成         ┌──────────┐
│ understanding  ├────────────────────────────►│          │
│  (≤5s 预算)    │                             │          │
└───────┬────────┘  超时/失败（降级：直接用      │          │
        │            LLM 原参 + 轻提示）        │          │
        │◄─────────────────────────────────────┤          │
        ▼                                      ▼          ▼
┌────────────────┐  命中(≤300ms)        ┌──────────┐  ┌──────────────┐
│  cache_check   ├─────────────────────►│   done   │  │window_loading│
└───────┬────────┘  (标注「缓存」+来源)  └──────────┘  │ (≤8s 轮询)   │
        │ 未命中                                   └───┬──────┬─────┘
        │                    ┌──────────────────────────┘      │
        │                    │ 超时/窗口不可用                 │ 验证页特征
        │                    ▼                                 ▼
        │           ┌────────────────┐              ┌─────────────────┐
        │           │ urllib_fallback├─成功────────► │     captcha     │
        │           └───────┬────────┘               │ (转流程 2 接管)  │
        │                   │ 也失败                 └─────────────────┘
        │                   ▼
        │            ┌───────────┐
        │            │  failed   │（人话错误 + 可操作提示）
        │            └───────────┘
        ▼
┌────────────────┐  解析失败        ┌───────────┐
│   extracting   ├─────────────────►│engine_retry│（换引擎 ≤2 次）
│   (纯函数)     │◄─────────────────┤(源文档 R1) │
└───────┬────────┘                  └───────────┘
        │ 成功
        ▼
┌────────────────┐  extract=full? ─是─► 逐个 browser_open（流程 3）
│   filtering    │（黑白名单/去重/重排）
└───────┬────────┘
        │ 否
        ▼
┌────────────────┐  不通过且重试<2      ┌──────────────┐
│  validating    ├─────────────────────►│  reformulate │（本地改写 query）
│    (V1)        │                      └──────┬───────┘
└───────┬────────┘                             │
        │ 通过/重试耗尽                         │
        ▼                                      │
┌────────────────┐                             │
│ truncate+cache │◄────────────────────────────┘
│     done       │
└────────────────┘

[任意执行态] ──用户点「停止」──► cancelled（关次窗口、结果丢弃、审计记录）
```

### ④ 状态反馈设计

| 状态 | 用户看到什么 | 载体 |
|------|-------------|------|
| understanding | 工具条目「正在理解检索意图…」；面板阶段指示 1/4 | `.tool-call-item` / `#searchPanel` |
| cache hit | 「✓ 搜索：query · N 条（缓存 · 0.3s · 来源 Bing）」 | 工具条目完成态 + 摘要行 |
| window_loading | 「正在打开 Bing…」+ 秒表计时（>3s 必显） | 面板 + 工具条目 |
| extracting | 「正在提取搜索结果…」 | 同上 |
| engine_retry | 「Bing 解析失败，正在切换 DuckDuckGo 重试（1/2）」 | 面板 warn 行 |
| validating 重试 | 「校验未过，正在改写检索式重试（1/2）」 | 面板 info 行 |
| done | 结果摘要卡：N 条结果 / 来源引擎 / 耗时 / 缓存或实时标记；面板结果列表（标题+摘要+域名+时间） | 消息流摘要 + `#searchPanel` |
| failed | 人话错误分四类：① 验证阻断（转流程 2）② 窗口超时且直连失败「页面加载超时，可重试或换个引擎」③ 提取失败「未能从结果页提取有效内容」④ 无结果「未找到相关内容，建议调整关键词」+「重新搜索」按钮 | toast err + 条目 fail 态 |
| captcha | 醒目 warn「需要人工验证」+ 操作指引 | `#searchPanel` + 次窗口弹出（流程 2） |

**核心原则落地**：搜索 P50 目标 ≤3s，超过即从「spinner 等待」升级为「阶段进度」；整个搜索过程 U1 面板实时显示「AI 正在搜什么」——这是信任特性，不是调试信息。

### ⑤ 中断与取消语义

- **用户点「停止」**：当前 `browser_search` 后端调用作废，次窗口关闭（或 60s 空闲回收），Agent 循环中断（既有 `userStopped` 机制），条目标「⊘ 已取消」。已成功的 `extract=full` 单篇结果保留在缓存但不入本次上下文。
- **后端自主超时**（窗口 8s / 本地 5s）不是用户中断，走降级分支并在面板如实标注（「已降级直连抓取」）。
- 用户不能取消「缓存写入」这类无副作用收尾。

### ⑥ 前后端触点

| 层 | 触点 | 说明 |
|----|------|------|
| js_api | `browser_search` / `browser_open` / `search_cache_stats` | 全部进 `_V12_EXTRA` 隐身 |
| 前端模块 | `25-tool-exec.js`（新分支 `browser_search`/`browser_open`）、`60-agent-loop.js`（条目渲染扩展：阶段标签动态更新）、`63-search-panel.js`（新） | |
| DOM | `.tool-call-item`（既有复用）、`#searchPanel`（新）、`#chatContainer` | 面板挂消息流右侧或覆盖层，原型阶段定 |
| 后端 | `search_service.py` / `search_browser.py` / `search_adapters.py` / `search_extract.py` | |
| 接口输入 | 进度回报通道：同步 `callApi` 阻塞期间，阶段如何送达前端（事件推送 or `search_status` 轮询）——需接口清单定义（Gap-9） | |

---

## 流程 2 · 人工接管反爬验证（U1）`v1.8.0`

**一句话**：引擎返回验证页 → 搜索面板弹出 + 可见次窗口获焦点 → 用户手动过检 → 点「继续」交还 → 后端复检续跑；放弃路径返回结构化错误让 Agent 换路。

### ① 触发条件

- 流程 1 的 `window_loading`/`extracting` 阶段，适配器检测到验证页特征（captcha/verify 元素或「结果数为 0 + 验证特征命中」）。
- 前置：U1 面板随首批交付（源文档 §13.1 建议已采纳为 P1——反爬没有接管路径等于半成品）。

### ② 分步流程

| # | 用户操作 | 系统响应 | 前端状态 | 后端调用 |
|---|---------|---------|---------|---------|
| 1 | — | 后端停轮询，标记 captcha_pending，**保持次窗口不关** | 工具条目转 warn 态「等待人工验证」 | `browser_search` 调用内（阶段事件） |
| 2 | — | 面板弹出/置顶 + 次窗口 `show()`+`focus()`（主窗口让位） | `#searchPanel` 显示「搜索引擎要求人机验证」+「去验证 →」按钮（聚焦窗口） | `search_browser` 窗口控制 |
| 3 | 在可见窗口中手动过检（输验证码/点选） | 系统等待，**不自动操作页面**（Non-goal：不做浏览器自动化） | 面板「等待手动验证…」+ 已等待计时 mm:ss | （纯等待，无调用） |
| 4a | 点「继续」 | 后端 `evaluate_js` 复检结果页选择器（≤5s） | 面板「正在检查验证结果…」 | `search_browser.evaluate_js` |
| 4b | 点「放弃」 | 返回结构化错误 `captcha_aborted` | 面板关闭，toast「已放弃本次搜索」 | `browser_search` 返回 error |
| 5 | — | 复检成功 → 回流程 1 `extracting`；仍验证页 → 可重试（≤3 次） | 面板恢复进度 / warn「验证未通过，请重试（1/3）」 | — |

### ③ 状态机

```
searching ──验证页特征──► captcha_detected
                              │
                              ▼
                     ┌──────────────────┐
                     │takeover_prompting│（面板弹出 + 次窗口可见获焦点）
                     └───────┬──────────┘
              ┌──────────────┼───────────────┐
              ▼              ▼               ▼
      ┌──────────────┐  (点「继续」)    (点「放弃」/关窗)
      │user_verifying│       │               │
      └──────┬───────┘       ▼               ▼
             │        ┌─────────────┐   ┌──────────┐
             │        │recheck(≤5s) │   │ aborted  │
             │        └──┬───────┬──┘   │(结构化错误回传│
             │      成功 │       │仍验证  Agent，可换引擎│
             │           ▼       ▼      │/urllib 不适用)│
             │    ┌───────────┐ ┌────────┴──────────┐
             │    │ extracting│ │takeover_prompting │
             │    │(回流程 1) │ │(重试 ≤3 次)       │
             │    └───────────┘ └──────────────────┘
             ▼
      （5 分钟无操作 → toast 提醒「仍在等待验证」；
        10 分钟无操作 → 自动 aborted，防永久挂起）
```

### ④ 状态反馈设计

| 状态 | 用户看到什么 |
|------|-------------|
| takeover_prompting | warn 色横幅 + 「去验证 →」主按钮（点击聚焦次窗口）；面板**不可关闭**（只能继续/放弃二选一）——防用户忽略后 Agent 永久挂起 |
| user_verifying | 计时 mm:ss + 明确指令「请在弹出的窗口中完成验证，然后点击『继续』」 |
| recheck 失败 | toast warn「验证未通过，请重试」+ 重试计数（1/3） |
| 成功 | toast ok「验证通过，继续搜索」+ 面板恢复阶段进度 |
| 放弃/超时 | toast「已放弃本次搜索」+ Agent 收到 `captcha_aborted` 后自主决策（换引擎/告知用户），用户可见 Agent 的后续说明 |
| 软超时提醒 | 5 分钟 toast「仍在等待人工验证，可点击放弃」 |

### ⑤ 中断与取消语义

- **放弃** = 本次 `browser_search` 调用以 `captcha_aborted` 失败结束；不阻塞会话，Agent 换路（换容忍度更高的引擎或直连告知）。
- **关闭次窗口**等同放弃（窗口关闭事件 → aborted）。
- 接管等待设软超时：5 分钟提醒、10 分钟自动放弃——反爬是概率事件（诚实边界），不能把会话吊死。
- 接管期间用户点「停止」等同放弃 + 关窗。

### ⑥ 前后端触点

| 层 | 触点 | 说明 |
|----|------|------|
| js_api | `browser_search`（阶段事件：captcha_detected/need_takeover）；窗口控制走 `search_browser` 后端侧 | 阶段事件通道见 Gap-9 |
| 前端模块 | `63-search-panel.js`（新：接管态渲染）、`60-agent-loop.js`（warn 条目）、`18-toast.js` | |
| DOM | `#searchPanel`（新）、次窗口（pywebview WebView2，独立用户数据目录） | |
| 验收注意 | 接管流程依赖真实显示设备，只能在目标机冒烟（源文档 §10）；UI 层提示状态可用 harness 模拟（Gap-5） | |

---

## 流程 3 · 深度提取（browser_open）`v1.8.0`

**一句话**：打开指定 URL → readability 主体提取或选择器覆盖 → 超长截断落 toolcache（read_more 可续读）→ V1 校验 → 结构化正文。

### ① 触发条件

- Agent 直接调用 `browser_open(url, selector?, max_chars)`。
- 或 `browser_search` 带 `extract=full` 时，后端对 Top N 连锁调用（前端只见总进度「深度提取 N 篇」，内部单篇失败不中断整批）。

### ② 分步流程

| # | 用户操作 | 系统响应 | 前端状态 | 后端调用 |
|---|---------|---------|---------|---------|
| 1 | — | 次窗口 `load_url` + 等待 load 事件/选择器（≤8s） | 工具条目「正在打开页面…」；面板原文预览 tab | `browser_open` |
| 2 | — | 主体提取：readability（去 script/style/nav、文本密度打分选主区）或用户 selector 覆盖 | 「正在提取正文…」 | `search_extract` |
| 3 | — | 长度判定：≤max_chars 直接返回；超长 → 截断落 toolcache | 「正文较长，已截断（可展开全文）」 | toolcache + `cache_id` |
| 4 | — | V1 校验：正文非空/长度合理/与页面标题相关 | — | validator |
| 5 | 看到正文 | 返回 `{title, text, truncated, cache_id, url}` | 条目完成 + 原文预览卡（标题/字数/来源域名/获取时间） | — |

### ③ 状态机

```
idle ──► loading(≤8s)
            │超时 ─► urllib_fallback ─┬成功─► extracting
            │                        └失败─► failed「页面加载超时」
            ▼
       extracting(readability / selector 覆盖)
            │正文 <200 字
            ▼
       thin_warning（仍返回，标注「正文较短：可能是登录墙/动态渲染页」）
            │
            ▼
       truncating ──>max_chars──► toolcache(cache_id, 返回预览 + read_more 提示)
            │
            ▼
       validating(V1) ──不通过──► failed「提取内容与页面不相关」
            │通过
            ▼
         done

[任意态] ──用户停止──► cancelled（放弃本次打开；连锁批次中已成功的保留在缓存）
```

### ④ 状态反馈设计

| 状态 | 用户看到什么 |
|------|-------------|
| loading | >3s 显示「仍在加载（对抗懒加载）…」+ 计时 |
| extracting | 「正在提取正文…」 |
| truncating | 明确提示「已截断至 N/总计 M 字」+ 预览卡 `read_more` 按钮（点击调 `read_more` 续读，既有工具模式） |
| thin_warning | 「正文过短（N 字），可能需要登录查看」+「在主窗口打开链接」按钮 |
| done | 标题 + 字数 + 域名 + 获取时间；连锁批次显示「深度提取 2/5 篇…」 |
| failed | 人话 + 可操作（重试/换 selector/主窗口打开） |

### ⑤ 中断与取消语义

- 用户停止 → 放弃本次打开；`extract=full` 连锁批次中，已成功的单篇入缓存但标注「未纳入本次结果」，未开始的不启动。
- 后端自主超时（8s）走 urllib 兜底，面板如实标注降级。

### ⑥ 前后端触点

| 层 | 触点 | 说明 |
|----|------|------|
| js_api | `browser_open` / `read_more`（既有，toolcache 续读） | `_V12_EXTRA` |
| 前端模块 | `25-tool-exec.js`（新分支）、`63-search-panel.js`（原文预览 tab） | |
| DOM | `.tool-call-item`、`#searchPanel` 预览区 | |
| 后端 | `search_extract.py`（readability 纯函数 + 选择器覆盖） | |

---

## 流程 4 · 外部软件调用（software_call）`v1.8.0`

**一句话**：guard 风险档位判定（高危强制确认）→ 探测状态 → 参数 schema 校验（失败自校正）→ CLI 沙箱执行/GUI 标题核验/URI 协议 → 人话结果与异常。

### ① 触发条件

- Agent 调用 `software_call(software, action, args, timeout?)`。
- 设置面板「外部软件」区块（S3）的测试调用——注意：测试调用语义不同（视为用户本人操作，不走 Agent guard 链），见 Gap-4。

### ② 分步流程（Agent 路径）

| # | 用户操作 | 系统响应 | 前端状态 | 后端调用 |
|---|---------|---------|---------|---------|
| 1 | — | 前端 guard 预检（risk 档位：read→session；mutate→session+审计；dangerous→always 强制确认） | 工具条目「正在调用 git commit…」 | `guardCheckTool` → `guard_check` |
| 2 | 高危时：确认/拒绝（可勾「永久信任」） | 签发 confirm-token 或回绝 | `#modalRoot` 模态：动作人话描述 + 参数明细 + 风险标签 | `guard_confirm_token` |
| 3 | — | 探测状态检查（已探测/未安装/版本不符） | 未安装：人话 + 官网链接 | `software_probe`（探测缓存） |
| 4 | — | 参数 schema 校验（类型/必填/枚举/路径约束；路径过工作区门禁 + realpath 归一） | 失败：Agent 收到结构化错误 + schema 回显自校正 | `software_service` 校验 |
| 5 | — | **CLI 类**：`sandbox_service.run_in_sandbox`（Job Object 收编 + 看门狗超时清剿） | >3s 显示「正在执行 git status…（已 12s）」+ 沙箱态 chip | 沙箱执行 |
| 5' | — | **GUI 类**：ShellExecute + `FindWindowW` 标题核验（≤10s） | 「已发起启动，正在确认窗口…」+「启动后无法中止」提示 | ShellExecute + FindWindowW |
| 5'' | — | **URI 类**：协议调用 | 「正在调用协议…」 | 协议处理器 |
| 6 | 看到结果 | 结果入上下文 + 审计 | 完成态：exit=0 ✓ / 非零 ✗人话 / 超时 ✗已终止 | 审计 |

### ③ 状态机

```
tool_pending
   │
   ▼
guard_check ──dangerous/always──► confirm_modal ─┬ 批准(可勾永久信任) ──► token_issued
   │                                          └ 拒绝 ────────────────► denied（人话回传 Agent）
   │（read/session 且已信任）
   ▼
probe_check ──未安装/版本不符──► not_installed（人话 + 官网链接；不自动下载）
   │
   ▼
schema_validate ──失败──► schema_error（结构化错误 + 正确示例；Agent 自校正 ≤2 次）
   │通过
   ▼
executing
   ├─ CLI ─► sandbox_run ─┬ exit=0 ──────────► done
   │                      ├ exit≠0 ─────────► exit_nonzero（stderr 人话映射 + 原始尾段）
   │                      └ 看门狗超时 ─────► killed（清剿进程树 + 「可调大 timeout 重试」）
   ├─ GUI ─► launching ─┬ 标题核验成功(≤10s) ► done
   │                    └ 超时 ────────────► unconfirmed（「可能被 UAC/杀软拦截」）
   └─ URI ─► protocol_call ─┬成功─► done
                            └失败─► uri_error

executing ──用户停止──► cancelling（CLI：清剿进程树）──► cancelled
```

### ④ 状态反馈设计

| 状态 | 用户看到什么 |
|------|-------------|
| confirm_modal | 模态标题「高危操作确认」；动作人话描述（「将强制推送到远程仓库」而非 `git push --force` 裸命令）；参数明细表；风险标签（dangerous 红 / mutate 黄）；「永久信任此类操作」勾选（既有 modal-check 模式）；批准/拒绝 |
| executing CLI >3s | 条目标签带计时「（已 12s）」+ 沙箱 chip「沙箱执行中 · Job Object 收编」；stdout 增量如事件通道可用则面板滚动 |
| executing GUI | 「已发起启动，正在确认窗口出现…」+ 明确「启动后无法中止」 |
| not_installed | err 提示「未检测到 X」+「去官网下载」链接按钮（**不自动下载**，供应链纪律） |
| schema_error | 用户侧：条目 fail「参数不符合 X 的调用规范，Agent 正在自我修正…」→ 重试成功转 done（自校正过程可见但不打扰） |
| killed | 「已终止（超过 Ns 上限）。可调大 timeout 重试」+ 已产生的部分 stdout 保留展示 |
| unconfirmed | warn「已发起启动但未检测到窗口（可能被 UAC/杀软拦截）。请检查任务栏与安全软件日志」 |
| done | exit=0 摘要 + stdout 尾段（可展开）；写操作同步 append_worklog |

### ⑤ 中断与取消语义

- **确认模态拒绝** = 取消（Agent 收到 denied + 原因，可换路或询问用户）。
- **CLI 执行中停止** → Job Object 清剿进程树（沙箱保证无孤儿进程）→「已终止执行」+ 部分输出保留。
- **GUI 启动不可逆**：`launching` 态明示「启动后无法中止」；停止只在执行前有效。
- 测试调用（S3）不适用以上 guard 语义（Gap-4）。

### ⑥ 前后端触点

| 层 | 触点 | 说明 |
|----|------|------|
| js_api | `software_list` / `software_call` / `software_probe` | `_V12_EXTRA` |
| 前端模块 | `25-tool-exec.js`（新分支）、`26-guard.js`（guard 预检复用）、`64-software-panel.js`（新，S3） | |
| DOM | `#modalRoot`（高危确认）、`.tool-call-item`、设置区 `#softwareBlock`（新 set-block，setNav 自动收录） | |
| 后端 | `software_service.py`（注册表/探测/执行）+ `sandbox_service.run_in_sandbox`（CLI 复用 v1.6 资产） | |
| 审计 | mutate 档 session+审计；dangerous always+审计；decision=grant 供 L2 联动（流程 7） | |

---

## 流程 5 · 混合路由会话（H1 · auto 策略）`v1.8.0`

**一句话**：本地管理解/校验、云端管规划/终稿；每回合四阶段（本地理解→云端执行→本地校验→置信门→云端终稿），会话头部实时分账，降级可见（流程 6）。

### ① 触发条件

- 会话启用混合路由（`hybrid.json` 独立配置，默认 `auto` 策略；设置内功能开关可关）。
- 每个 Agent 回合自动生效，无需用户操作。

### ② 分步流程

| # | 用户操作 | 系统响应 | 前端状态 | 后端调用 |
|---|---------|---------|---------|---------|
| 1 | 发送消息 | 并行启动本地 understand（首 token 50-500ms，连接复用）+ 主流程准备 | 输入框锁定、`#streamBar` on；`#headerStatusZone` 阶段 chip「本地理解中」 | `hybrid_router` → 本地端点 |
| 2 | — | 本地理解返回意图/参数/检索式（≤5s 预算） | chip 切「云端执行中」 | 本地 LLM |
| 3 | — | 云端 plan + 工具调用执行 | 工具条目逐个出现（流程 1/3/4 各自状态） | 云端 LLM + 工具面 |
| 4 | — | 本地 validate（≤3s 预算）→ `verdict + confidence + reason` | chip「本地校验中」 | 本地 LLM |
| 5 | — | 置信门 ≥0.7 通过 → 云端 compose；<0.7 → 云端复核 或 reformulate 重试 ≤2 | chip「云端复核中」 | 云端 LLM |
| 6 | 看到流式回复 | 终稿流式输出 | `#streamBar` + typing dots；分账实时更新 | 云端 LLM |
| 7 | — | 路由决策日志（哪阶段走哪端、为何降级）落 `~/.glm-chat/logs/` | 审计查看器可见（28-audit-viewer.js 新增筛选项） | 审计 |

**策略差异**：

| 策略 | understand/validate | plan/compose | 用户体验差异 |
|------|---------------------|--------------|-------------|
| `auto`（默认） | 本地（可用则） | 云端 | 头部分账双列增长；偶发降级提示（流程 6） |
| `saver`（省 token） | 全本地优先 | 按任务复杂度分档（简单问答也本地） | 头部长驻「saver 模式：质量可能下降」提示；**任何降级必提示**（用户意图被违背且产生费用） |
| `quality` | — | 全云端 | 等价现行为；分账仅云端列（或隐藏分账区） |

### ③ 状态机

```
turn_start
   │
   ▼
┌─────────────────┐
│ understanding   │（本地 5s 预算）
│   (本地)        │
└───┬─────────┬──┘
    │成功     │超时/端点不可用            │置信 <0.7
    ▼         ▼                          ▼
┌─────────────────┐  degrade(提示)  ┌──────────────────┐
│   tool_exec     │◄────────────────│  cloud_understand│（云端接管理解）
│ (云端规划/工具)  │                 └──────────────────┘
└────────┬────────┘
         ▼
┌─────────────────┐
│   validating    │（本地 3s 预算）
└───┬─────────┬──┘
    │≥0.7     │超时                      │<0.7
    ▼         ▼                          ▼
┌─────────────────┐  degrade(提示)  ┌──────────────────┐
│   composing     │◄────────────────│  cloud_revalidate│
│ (云端终稿)       │                 └───┬──────────┬───┘
└────────┬────────┘                     │通过       │不通过
         ▼                              ▼          ▼
    streaming ──► done            composing   reformulate(≤2) ──► tool_exec
   （分账定账）                              （重试耗尽则云端兜底终稿）

[任意态] ──用户停止──► cancelled（本回合请求全部 abort；分账保留已发生部分）
```

### ④ 状态反馈设计

| 状态 | 用户看到什么 |
|------|-------------|
| 各阶段 | `#headerStatusZone` 轻量 chip 轮换：本地理解中 → 云端执行中 → 本地校验中 → 终稿生成中（不打断阅读，纯新增） |
| 分账 | 会话头部「本地 X tok · 云端 Y tok · 省 ≈¥Z」实时（数字滚动 `--dur-count`）；本地 ¥0 但计入统计 |
| 降级 | toast warn（边界规则见流程 6） |
| saver 模式 | 头部长驻 warn chip「saver 模式：简单任务全程本地，质量可能下降」 |
| 置信门重试 | 条目/面板 info「本地校验置信度 0.55，升级云端复核」 |
| 策略切换 | 设置内切换即时生效于**下一回合**；当回合不中断 |

### ⑤ 中断与取消语义

- 用户停止 → 当前本地/云端请求 abort（前端 AbortController），工具批次中断（既有 `userStopped`），分账保留已发生部分。
- 本地请求作废不重试（避免停止后仍消耗云端额度）。
- 策略切换不是取消：不中断当回合。

### ⑥ 前后端触点

| 层 | 触点 | 说明 |
|----|------|------|
| js_api | `hybrid_get_config` / `hybrid_save_config` / `hybrid_stats`（约数，以接口清单为准） | `_V12_EXTRA`；`hybrid.json` 独立文件不污染 config.json |
| 前端模块 | `65-hybrid.js`（新：配置 UI + 分账渲染）、`60-agent-loop.js`（阶段 chip 挂 `#headerStatusZone`）、`28-audit-viewer.js`（路由日志筛选） | |
| DOM | `#headerStatusZone`（既有容器内新增 `#hybridLedger`）、设置区 `#hybridBlock`（新） | |
| 后端 | `hybrid_router.py`（任务分类器 understand/validate/plan/compose + 三策略 + 置信门） | |

---

## 流程 6 · 本地端点降级（5s/3s 预算）`v1.8.0`

**一句话**：本地任何阶段超时/失败绝不阻塞主流程，静默降级云端——但**降级本身必须让用户知道**；本文定义「什么必须提示、什么可以静默」的边界。

### ① 触发条件

- 本地端点请求超过预算（understand 5s / validate 3s）。
- 本地端点连接失败（连接拒绝/404/模型缺失）——**快速失败，不等满预算**。
- 探测连续失败累计 3 次 → 端点标记 unavailable。

### ② 分步流程

| # | 用户操作 | 系统响应 | 前端状态 | 后端调用 |
|---|---------|---------|---------|---------|
| 1 | — | 本地请求进入 5s/3s 预算窗 | 阶段 chip 正常显示 | `hybrid_router` |
| 2 | — | 超时/失败 → 降级云端（当前步骤） | **本会话首次**：toast warn「本地模型响应超时（>5s），已切换云端处理本步骤」 | degrade 事件 |
| 3 | — | 连续失败 3 次 → 标记 unavailable | 设置面板本地状态灯变灰；toast warn「本地模型持续不可用，本会话剩余步骤将走云端」 | `local_probe` 周期探测（60s） |
| 4 | — | 后台周期探测（或下回合前探测） | 灯黄「恢复探测中」 | `local_probe` |
| 5 | — | 恢复 → 后续阶段回本地 | toast ok「本地模型已恢复，后续理解/校验将回到本地」；灯绿 | — |

### ③ 状态机

```
available ──请求超时/失败──► degraded(单次降级 + 首降提示)
   │                              │下一请求成功
   │                              ▼
   │                          available（不再重复提示）
   │                              │连续失败 3 次
   │                              ▼
   │                        unavailable（提示 + 灯灰 + 周期探测 60s）
   │                              │探测成功
   └──────────────────────────────┴──► available（恢复提示 + 灯绿）
```

### ④ 状态反馈设计：静默降级的边界（核心）

| 情形 | 必须提示 | 可静默 | 理由 |
|------|:-------:|:------:|------|
| understand 单次超时（本会话首次） | ✓ | — | 用户应知道「谁在处理我的数据」——隐私相关 |
| understand 单次超时（本会话重复） | — | ✓ | 首次已建立认知；重复 toast 是骚扰 |
| 端点持续不可用（3 连败） | ✓ | — | 影响成本与隐私面，必须知情 |
| 端点恢复可用 | ✓ | — | 让用户知道「本地回来了」 |
| **saver 策略下任何降级** | ✓（每次） | — | 用户选 saver=意图省钱/留本地，降级违背意图且产生云端费用 |
| validate 超时跳过校验 | ✓（合并阶段提示） | — | 校验缺席影响结果可靠性 |
| understand 参数补全失败（预算内返回失败） | — | ✓ | 对用户无感，Agent 用原参继续；质量影响在结果层体现，不在流程层刷屏 |
| V1 确定性 validator（文件存在性/退出码） | — | ✓ | 纯本地计算，不涉及端点，无「谁处理」问题 |

**反馈组件**：
- 设置面板本地状态灯：复用 `.sb-light` 三态模式（绿=可用 / 黄=降级或探测中 / 灰=不可用），挂「连接与模型」块 `#localProbeResult` 附近。
- 会话头部分账「本地」列停止增长 = 隐性可见（配合显式提示）。
- 审计查看器：路由决策日志（阶段/原因/耗时）可筛——「为何降级」有据可查。

### ⑤ 中断与取消语义

- 无用户取消语义（系统自动行为）。
- 用户控制点 = 设置内关闭混合路由（回 `quality` 全云端）——即时生效，下一回合起全云端，toast 确认。

### ⑥ 前后端触点

| 层 | 触点 | 说明 |
|----|------|------|
| js_api | `local_probe`（既有，探测复用）；降级事件经 `hybrid_router` 阶段通道 | |
| 前端模块 | `65-hybrid.js`（降级提示与灯态）、`34-local-model.js`（状态灯挂载）、`28-audit-viewer.js`（路由日志） | |
| DOM | `#headerStatusZone`、`#localProbeResult`（既有，灯纯新增元素） | |
| 后端 | `hybrid_router.py`（5s/3s 硬超时 + 快速失败 + 探测节流）、`local_model_service.py`（既有探测/错误分类） | |

---

## 流程 7 · L2 任务授权生命周期 `v1.8.5`

**一句话**：用户对长任务一次性授权（工作区内文件写入+命令执行自动，破坏性操作除外）→ 常驻指示灯 + TTL 倒计时 → 授权内自动放行（审计记 grant）→ 越界仍拦 → 随时收回 / TTL 到期自动失效。

### ① 触发条件

- Agent 在多步写任务开始前，消息流内**建议卡**：「本任务涉及 N 次文件写入/命令执行，可授权本任务自动执行（范围：工作区内；破坏性操作除外）」。
- 用户主动发起（计划卡或 guard 设置内入口）。
- **铁律**：授权必须用户显式操作——Agent 无权自行放宽自己的权限（Non-goal #4）。

### ② 分步流程

| # | 用户操作 | 系统响应 | 前端状态 | 后端调用 |
|---|---------|---------|---------|---------|
| 1 | 点「授权本任务」 | 弹出授权确认模态 | `#modalRoot`：范围说明 + TTL 选择（30min/2h/4h，默认 2h）+ 例外清单明示 | `guard_task_grant` |
| 2 | 确认 | guard_service 建立 task_grant（绑定 task_id） | `#taskGrantBar`（输入区上方常驻）：「任务授权中 ⏱ 1:59:59」 | task_grant 状态 |
| 3 | （等待） | 范围内操作自动放行 | 每次放行：审计 decision=grant（**不逐条 toast**，防噪） | `guard_check` → grant |
| 4 | （等待） | 越界/deny 清单操作仍拦截 | 照常弹确认，模态附注「该操作超出任务授权范围」 | `guard_check` → op 档位 |
| 5 | 点「收回授权」 | 立即失效 | 指示灯变灰「授权已收回」+ toast | `guard_task_grant_revoke` |
| 6 | （等待） | TTL 到期 | 指示灯灰「授权已到期」+ toast warn | 定时器 |

### ③ 状态机

```
no_grant ──用户发起──► granting(模态: 范围 + TTL + 例外清单)
                          │确认
                          ▼
        ┌─────────────────active─────────────────┐
        │ 指示灯亮 + TTL 倒计时                    │
        │                                         │
        ├─ 范围内调用 ──► auto_pass(audit: grant) ─┤
        │                                         │
        ├─ 越界/deny 调用 ──► blocked(仍弹确认) ───┤
        │                                         │
        ├─ 用户收回 ──► revoked(立即, audit: revoke)
        │                     │
        └─ TTL 归零 ──► expired(宽限: 见 Gap-1)    │
                              │                   │
                              ▼                   ▼
                          no_grant ◄──────────────┘

active ──剩余 <10min──► expiring_soon（灯变黄 + 倒计时高亮 + 「重新授权」入口）
```

### ④ 状态反馈设计

| 状态 | 用户看到什么 |
|------|-------------|
| active | `#taskGrantBar` 常驻（输入区上方，靠近操作焦点）：「任务授权中」+ TTL 倒计时 mm:ss 实时 + 「收回」按钮 |
| auto_pass | 不进 toast（防噪）；审计查看器可见 grant 记录（op/scope/at） |
| blocked | 确认模态附注「超出任务授权范围：删除工作区外路径」——让用户知道授权不是免检 |
| expiring_soon | 灯变黄 + 倒计时高亮；点「重新授权」打开模态重新确认（防误触延长） |
| revoked | 灯灰「已收回」+ toast「授权已收回，后续操作将逐项确认」 |
| expired | 灯灰「已到期」+ toast warn「任务授权已到期（2h），后续操作将逐项确认」 |

### ⑤ 中断与取消语义

- **收回** = 立即取消**未来**放行；不追溯已放行操作；对进行中的调用的处理建议「不受影响，跑完即止」（Gap-1 待裁决）。
- **TTL 到期** = 自动取消；宽限策略见 Gap-1。
- 授权不转移：绑定 task_id，新会话/新任务需重新授权（`begin_task` 时校验）。
- deny 清单（工作区外删除/提权/凭证外传/永久删关键路径/guard off）在授权内**依然拦截**——授权是提权不是免检。

### ⑥ 前后端触点

| 层 | 触点 | 说明 |
|----|------|------|
| js_api | `guard_task_grant` / `guard_task_grant_status` / `guard_task_grant_revoke` | `_V12_EXTRA`；guard_service 进程内状态 + 审计 |
| 前端模块 | `26-guard.js`（扩展：grant 预检分支 + 模态 + 收回）、`60-agent-loop.js`（任务开始建议卡） | |
| DOM | `#taskGrantBar`（新，输入区上方）、`#modalRoot`（授权/收回确认） | |
| 后端 | `guard_service.py`（scope/grant 判定顺序：deny 清单 → allow_rules → task_grant → op 档位 → 确认弹窗） | |

---

## 流程 8 · Plan-Act 计划执行 `v1.9.0`

**一句话**：计划即契约——先出可编辑计划卡（步骤+预声明+风险标注）→ 用户批准 → Act 按 todo 五态执行 → 偏差检测（轻微自适应/重大暂停回问）→ V1 自验交付摘要 + 回滚入口。

### ① 触发条件

- 用户开启 Plan 模式（建议：输入区上方模式切换 chip 或 `/plan` 前缀）并发送多步任务。
- 或 Agent 判断需要计划时**提议**（用户确认后才进入 Plan，减少意外）。
- 信息不足时先走流程 9（批量澄清）再出计划。

### ② 分步流程

| # | 用户操作 | 系统响应 | 前端状态 | 后端调用 |
|---|---------|---------|---------|---------|
| 1 | 发送多步任务 | 进入 Plan：本地理解 → 生成计划 | 消息流顶部计划卡骨架「正在生成计划…」 | H1 本地 + 模板约束 |
| 2 | 审阅 | 计划卡：步骤 checklist + 涉及文件/命令预声明 + 风险标注（哪些步触发 L0/L2/deny） | 计划卡可交互：步骤增删/重排/改标注 | — |
| 3 | 批准 / 编辑后批准 / 拒绝 | 批准 → Act 开始 + **检查点创建（流程 10 联动）**；拒绝 → 对话式修改 | 计划卡状态条「已批准 · 执行中」 | `begin_task` + checkpoint |
| 4 | （等待） | 按步执行 | todo 五态实时：pending 灰圈 / doing 呼吸圈+工具 spinner / done ✓ / blocked ✗ / skipped ⊘ | `executeToolRaw` |
| 5 | （等待） | 偏差检测：实际调用 vs 计划声明 | 轻微偏差：步骤标 `~` + 条目标注「计划外：xxx（低风险，已继续）」；重大偏差（计划外删/越界/提权）：**暂停条**「检测到计划外操作：删除 X —— 已暂停」 | guard + 计划基准比对 |
| 6 | 处理暂停 | 用户选择：允许本次 / 加入计划 / 中止任务 | 暂停条按钮组 | — |
| 7 | （等待） | 步骤 blocked → Agent 提议修订计划 | 计划卡「提议修订」diff（增绿/删红/改黄） | — |
| 8 | 批准修订 / 驳回 / 跳过 | 继续执行 / 维持 blocked / 跳过该步 | 计划卡更新（版本号 v2/v3…） | — |
| 9 | 看到摘要 | V1 校验跑结果自验 → 交付摘要 | 摘要卡：改了什么（文件清单）/ 验证结果 / 未决事项 / 「回滚到此任务前」链接 | validator |

### ③ 状态机

```
task_received
   │
   ▼
planning(本地理解) ──信息不足──► clarifying(流程 9) ──► planning
   │计划生成
   ▼
plan_review(计划卡待批)
   ├─ 批准 ──────────────► acting
   ├─ 编辑后批准 ────────► acting（计划更新, audit: plan_edited）
   └─ 拒绝 ──────────────► replanning(对话式修改) ──► plan_review
   │
   ▼
acting ──► step_doing ─┬ 成功 ──► step_done ─┬ 还有下一步 ──► step_doing
                        │                    └ 全部完成 ────► delivering
                        ├ 失败 ──► step_blocked ──► replan_proposal(Agent 提议修订)
                        │                              ├─ 用户批准 ──► acting(v2 计划)
                        │                              └─ 驳回 ──────► step_blocked ──用户点跳过──► step_skipped
                        └ 计划外调用 ──► deviation_check
                                          ├─ 轻微 ──► 自适应继续(标 ~) ──► step_doing
                                          └─ 重大 ──► paused(高亮 + 回问)
                                                       ├─ 允许本次 ──► step_doing
                                                       ├─ 加入计划 ──► acting(计划更新)
                                                       └─ 中止 ──────► aborted
delivering ──► summary(V1 自验 + 交付摘要 + 回滚链接) ──► done

[任意态] ──用户停止──► cancelling ──► cancelled（保留已完成步；检查点可回滚）
```

### ④ 状态反馈设计

| 状态 | 用户看到什么 |
|------|-------------|
| planning | 计划卡骨架 + 「正在生成计划…」 spinner |
| plan_review | 完整计划卡：步骤 checklist；每步涉及文件/命令预声明；风险标注（L0 红 / L2 黄 / deny 灰锁）；「批准执行」主按钮 + 「编辑」+ 「拒绝」 |
| step_doing | 步骤呼吸圈（`--dur-breathe` 令牌）+ 联动 `.tool-call-item` spinner；>3s 步骤显示计时 |
| 轻微偏差 | 步骤 `~` 前缀 + 条目标注「计划外：xxx（低风险，已继续）」——**可见但不打断** |
| 重大偏差 | 暂停条 warn 色（计划卡顶部或消息流内）：「检测到计划外操作：删除 X —— 已暂停等待确认」+ 三按钮 |
| replan_proposal | 修订 diff 视图：新增步骤绿 / 删除红 / 修改黄 + 「批准修订」/「驳回」 |
| delivering | 交付摘要卡：改动文件清单 / 验证结果（V1 verdict）/ 未决事项 / 回滚按钮 |
| cancelled | 摘要卡降级版：「已停止。已完成 N 步；可回滚到此任务前」 |

### ⑤ 中断与取消语义

- **停止** = 取消后续步骤；已完成步骤保留磁盘结果（可回滚，流程 10）。
- **拒绝计划** = 零副作用（未开始执行，检查点未创建）。
- **暂停条「中止任务」** = 取消后续 + 保留已完成 + 提示可回滚。
- **编辑后批准** = 计划更新为基线，后续偏差检测以 v2 计划为基准（audit 记 plan_edited）。

### ⑥ 前后端触点

| 层 | 触点 | 说明 |
|----|------|------|
| js_api | 计划生成经 H1 本地 + 云端；`checkpoint_create`（联动）；工具执行复用 `executeToolRaw` | clarify 伪工具见流程 9 |
| 前端模块 | 新计划卡模块（`#planCard`）、`60-agent-loop.js`（todo 状态渲染）、`26-guard.js`（计划基准比对挂点） | |
| DOM | `#planCard`（新，消息流顶部）、暂停条（计划卡内）、`#chatContainer` | |
| 后端 | 计划模板 + 偏差检测（计划声明 vs 实际调用）+ todo 状态机常驻系统提示（压缩不丢计划） | |

---

## 流程 9 · 批量澄清（clarify）`v1.9.0`

**一句话**：信息不足攒着一次问完——`clarify` 伪工具一次提交 ≤5 问单张表单，每题带默认值，支持「全部按默认」一键确认；禁止执行中挤牙膏式单问。

### ① 触发条件

- Plan 阶段（流程 8 `planning`）检测到信息不足：多选一缺失 / 路径不明 / 范围不清。
- **唯一例外**（阻断级单问）：不答就无法安全继续的问题（如「目标路径在工作区外，是否允许」）——安全优先于批量原则。

### ② 分步流程

| # | 用户操作 | 系统响应 | 前端状态 | 后端调用 |
|---|---------|---------|---------|---------|
| 1 | — | Agent 提交 `clarify` 伪工具调用（JSON：≤5 问，每题 `{id, question, options, default}`） | 消息流出现澄清表单卡（替代常规工具 spinner） | clarify 伪工具（工具面，非 js_api） |
| 2 | 逐题作答 / 一键默认 | 表单交互：选项 chip（单选/多选/文本）；默认值预选高亮 | `#clarifyCard`：题号 + 问题 + 选项 + 「默认」标记；「全部按默认继续（N 项默认）」主按钮 + 「逐题确认」次按钮 | — |
| 3 | 提交 | 答案作为 clarify 工具结果回传 Agent → 继续 Plan | 表单锁定（已答态）→ 计划卡生成 | agent loop 拦截渲染 |
| 4 | — | 若仍不足（第 2 轮）：再次 clarify，总轮次 ≤2 | 第 2 轮表单附提示「最后一轮澄清，剩余信息将按假设处理」 | — |
| 5 | — | 超 2 轮：带假设继续 | 计划卡假设步骤 `~` 前缀 + 摘要「以下步骤基于假设：…」 | — |

### ③ 状态机

```
planning ──信息不足──► clarify_pending(单张表单 ≤5 问)
   │                      ├─ 提交(含默认) ──────► planning(答案入上下文)
   │                      ├─ 关闭表单 ──────────► planning(全默认, 计划标「假设」)
   │                      └─ 第 2 轮仍不足 ─────► planning(带假设, 不再追问)
   ▼
plan_review
```

### ④ 状态反馈设计

| 状态 | 用户看到什么 |
|------|-------------|
| clarify_pending | 表单卡：未答题 primary-soft 高亮边框；已答锁定；每题默认值预选 + 「默认」徽标 |
| 一键默认 | 主按钮文案明示后果「全部按默认继续（N 项默认）」——用户明确知道自己在接受什么 |
| 等待期 | **发送按钮禁用** + 输入框 placeholder「请先回答上方澄清」（防上下文错乱；Gap-6 待确认） |
| 假设标注 | 计划卡对应步骤 `~` 前缀 + 交付摘要集中列示假设项 |

### ⑤ 中断与取消语义

- 澄清无独立取消语义（任务内的子流程）：**关闭表单 = 按默认值继续**；要中止整个任务用「停止」。
- 表单已提交不可回收修改（防答案与上下文不一致）。
- 「默认值」不是「取消」——表单必须给出明确结果（答案或显式默认）才能继续，不存在静默跳过。

### ⑥ 前后端触点

| 层 | 触点 | 说明 |
|----|------|------|
| 工具面 | `clarify` 伪工具（Agent 提交清单 → 结果回传）；**不是 js_api**，走工具调用/结果通道 | |
| 前端模块 | `60-agent-loop.js`（拦截 clarify 工具名 → 渲染 `#clarifyCard` → 回传结果） | |
| DOM | `#clarifyCard`（新，消息流内）、`#sendBtn`/`#userInput`（禁用态） | |
| 后端 | 无需新后端（伪工具在前端闭环）；问题清单生成在 Plan 阶段本地/云端模型 | |

---

## 流程 10 · 检查点与回滚 `v1.9.0`

**一句话**：任务开始自动快照（git 锚点 / 非 git 文件快照）→ 回滚入口常驻 → 文件清单二次确认 → 恢复；与压缩备份（管上下文）分层互补，互不替代。

### ① 触发条件

- **创建**：Plan 批准后自动（v1.9.0 联动）；非 Plan 模式下 Agent 检测到写操作类任务时自动。
- **回滚**：用户主动发起（计划卡「回滚到此任务前」+ 完成摘要回滚链接）。

### ② 分步流程

| # | 用户操作 | 系统响应 | 前端状态 | 后端调用 |
|---|---------|---------|---------|---------|
| 1 | （批准计划/任务开始） | 创建检查点 | 计划卡脚注「检查点已创建 · N 个文件 · 12MB」+ 轻 toast（不弹模态） | `checkpoint_create` |
| 2 | — | git 仓库：`git stash create` 记录 HEAD（**不碰用户分支状态**，只做恢复锚点）；非 git：快照**计划声明涉及**的文件 → `~/.glm-chat/checkpoints/<task_id>/` | — | git / 快照复制 |
| 3 | （任务中/后） | 入口常驻 | 计划卡 + 摘要卡「回滚到此任务前」ghost-danger 按钮 | `checkpoint_list` |
| 4 | 点回滚 | 二次确认：将恢复/删除的文件清单 + 不可逆警示 | `#modalRoot`：清单表格（状态列：将恢复/将删除/将覆盖）+ danger「确认回滚」+「开始后无法中断」明示 | `checkpoint_list` |
| 5 | 确认 | 逐文件恢复 | >3s 显示进度「正在恢复 3/7…」（模态内进度条） | `checkpoint_rollback` |
| 6 | 看到结果 | 完成/部分失败 | 成功：toast ok「已恢复到任务开始前（N 个文件）」；部分失败：失败文件清单 + 「关闭占用程序后重试」按钮 | — |

### ③ 状态机

```
task_start
   │
   ▼
checkpoint_creating
   ├─ git 仓库 ──────► anchor_recorded(HEAD ref)
   └─ 非 git ────────► snapshotting(复制计划涉及文件)
                          └─ 超限(200MB/500 文件) ──► manifest_only(仅 diff 清单 + warn toast)
   │
   ▼
active(回滚入口可用)
   │用户点回滚
   ▼
confirm_modal(清单二次确认)
   ├─ 取消 ──► active（零副作用）
   └─ 确认 ──► rolling(逐文件, 进度 N/M)
                ├─ 全部成功 ──► rolled_back(toast ok + 摘要)
                └─ 部分失败 ──► partial(失败清单 + 原因: 被占用/权限 + 重试入口)
   │
   ▼
task_end ──► retained(默认保留至下个任务开始; 完成即清可配置 —— Gap-10 待裁决)
```

### ④ 状态反馈设计

| 状态 | 用户看到什么 |
|------|-------------|
| creating 成功 | 轻量：计划卡脚注 + 短 toast——**不弹模态**（避免每次任务开始都打断） |
| creating 超限降级 | **必须** warn toast「文件过多，检查点仅记录变更清单，回滚能力受限」——能力缩水必须知情 |
| confirm_modal | 完整清单（每条文件 + 将恢复/将删除/将覆盖状态列）+ 「不可逆」警示 + danger 主按钮 + 「开始后无法中断」明示 |
| rolling | >3s 显示「正在恢复 N/M…」进度（快操作不闪烁） |
| rolled_back | toast ok + 数量；计划卡/摘要标注「已回滚」 |
| partial | 失败清单 + 具体原因（被占用/权限）+ 「关闭占用程序后重试」按钮 |

**与压缩备份的区别**（UI 层明确分离，防用户混淆）：

| 维度 | 检查点（本流程） | 压缩备份（既有） |
|------|----------------|-----------------|
| 管什么 | **磁盘文件**（工作区） | **对话上下文**（消息历史） |
| 入口 | 计划卡 / 任务摘要 | 会话管理（压缩时自动，50 条上限） |
| 触发 | 任务开始自动 + 用户回滚 | 上下文超限自动 |
| 语义 | 恢复文件到任务前 | 折叠旧消息为摘要 |

### ⑤ 中断与取消语义

- 确认模态**可取消**（零副作用）。
- 恢复进行中**不可取消**（防半恢复态；文件操作快，代价低于半状态）——模态内已明示。
- 回滚后检查点本身保留（可再次回滚或任务继续），不自动清除。

### ⑥ 前后端触点

| 层 | 触点 | 说明 |
|----|------|------|
| js_api | `checkpoint_create` / `checkpoint_list` / `checkpoint_rollback` | `_V12_EXTRA`；快照目录 `~/.glm-chat/checkpoints/` |
| 前端模块 | 计划卡模块（入口+脚注）、`18-toast.js`（进度 toast pinned） | |
| DOM | `#planCard` 脚注、`#modalRoot`（回滚确认） | |
| 后端 | git 锚点 / 快照复制 / diff 清单降级 / 逐文件恢复 | |

---

## ⚠️ 发现的需求冲突与 Gap（供主理人裁决）

1. **L2 授权 TTL 到期 vs 进行中调用的竞态（未定义）**：源文档未定义「TTL 到期/收回时，进行中的工具调用如何处理」。本文建议：**进行中的调用允许完成（写入宽限），新调用需确认**。备选方案（源文档 §11.2）：「跟随任务生命周期 + 空闲 30 分钟自动收回」与「TTL 2h」两种到期语义尚未合并，需裁决。
2. **saver 策略的「质量下降自负」提示 vs 降级必提示的张力**：源文档 §13.3 待确认是否加提示；而流程 6 边界规则要求 saver 下降级**每次必提示**（用户意图被违背且产生费用）。本文按「必提示」设计，若产品希望弱化需同步调整流程 6 边界表。
3. **browser_search 与内置 web_search 双通道的工具选择歧义**：GLM 端点 + `enableSearch` 开启时，Agent 工具集里有两个搜索工具（内置黑盒 vs 自有受控），模型选择不确定。建议：`include_agent` 通道下 GLM 端点场景默认只下发 `browser_search`，内置 `web_search` 仅在混合路由关闭或用户显式选择时可用——需与 `build_tools` 契约策略一并裁决（默认路径逐字节不变的红线下，Agent 通道可裁）。
4. **S3 测试调用与 guard 链的关系未定义**：设置面板「测试调用」走哪个风险档？本文建议：测试调用视为**用户本人手动操作**（source=manual_test），不走 Agent guard 确认链，但照常审计。若测试 mutate/dangerous 动作也弹确认，用户会觉得「我自己点自己还要确认」。
5. **人工接管验收依赖显示设备**：接管流程（真实 WebView2 窗口 + 焦点）只能在目标机冒烟（源文档 §10 已注明本环境无显示设备）。建议：UI 层提示状态（面板横幅/按钮/计时）用前端 harness 模拟验证，窗口层验收单列目标机冒烟项。
6. **澄清等待期发送禁用（本文建议，需确认）**：源文档未定义澄清未答时用户能否继续发消息。本文按「禁用发送」设计（防上下文错乱）；若产品希望允许并行输入，需定义消息队列语义。
7. **U1 次窗口焦点管理实现细节**：人工接管需要 pywebview 次窗口 `show()`+`focus()` 且主窗口让位，源文档只说「面板弹出可见窗口」，未定义窗口层级与焦点 API 细节——需实现侧确认 pywebview 多窗口焦点能力。
8. **browser_search 进度回报通道（接口输入）**：`browser_search` 是同步 `callApi` 阻塞调用，阶段进度（理解中/加载中/提取中/验证页）如何送达前端（事件推送 or `search_status` 轮询）未定义——本文所有流程的「面板实时阶段」均依赖此通道，需接口清单明确。
9. **版本归属提醒**：流程 7 属 v1.8.5、流程 8/9/10 属 v1.9.0，但本文一并设计以保证原型 DOM 结构一致（`#taskGrantBar`/`#planCard`/`#clarifyCard` 容器与 v1.8 组件同规范）。**开发排期请以版本为准**，勿因本文合并叙述误解为 v1.8.0 全做。
10. **检查点保留策略待裁决**（源文档 §11.3）：默认保留至下个任务开始（可回滚上一任务）vs 完成后即清（省磁盘）。本文按「保留至下个任务」设计，保留策略可在 `hybrid.json` 同级配置文件中调整。

---

## 附 · 状态机清单速查（10 流程）

| # | 流程 | 主状态链 | 异常/降级分支 | 取消语义 |
|---|------|---------|--------------|---------|
| 1 | 浏览器搜索 | understanding → cache/window → extracting → validating → done | 本地超时降级原参；窗口超时→urllib；验证页→流程 2；校验不过→reformulate ≤2 | 停止=调用作废+关窗+结果丢弃 |
| 2 | 人工接管 | captcha_detected → takeover_prompting → user_verifying → recheck → extracting/aborted | 复检失败重试 ≤3；5min 提醒/10min 自动放弃 | 放弃/关窗= captcha_aborted，Agent 换路 |
| 3 | 深度提取 | loading → extracting → truncating(toolcache) → validating → done | 加载超时→urllib；正文过短→thin_warning | 停止=放弃本次；连锁批次保留已成功 |
| 4 | 软件调用 | guard → probe → schema → executing(cli/gui/uri) → done | 未安装引导；schema 失败自校正 ≤2；CLI 超时清剿；GUI 未确认人话；非零人话映射 | 模态拒绝=取消；CLI 停止=清剿进程树；GUI 启动不可逆 |
| 5 | 混合路由 | understanding → tool_exec → validating → 置信门 → composing → streaming | 本地超时→降级(流程 6)；置信<0.7→云端复核/reformulate ≤2 | 停止=全部 abort；分账保留 |
| 6 | 本地降级 | available ↔ degraded ↔ unavailable | 3 连败→unavailable；60s 周期探测恢复 | 无用户取消；设置可关混合路由 |
| 7 | L2 授权 | no_grant → granting → active(TTL) → revoked/expired | 越界仍拦；deny 清单不豁免；剩余<10min 黄牌 | 收回=立即失效(未来)；到期=自动失效 |
| 8 | Plan-Act | planning → plan_review → acting(todo 五态) → delivering → summary | 信息不足→流程 9；blocked→重规划提议；偏差：轻微自适应/重大暂停 | 停止=取消后续保留已完成；拒绝计划=零副作用 |
| 9 | 批量澄清 | clarify_pending(≤5 问单表单) → planning | 第 2 轮≤2；超限带假设继续(标 ~) | 关闭表单=按默认继续；无独立取消 |
| 10 | 检查点回滚 | creating → active → confirm_modal → rolling → rolled_back | 超限→仅清单(warn)；恢复部分失败→清单+重试 | 模态可取消；恢复中不可取消 |

---

> 本文由需求发现分析师许明需编制，基于 v1.8.0 迭代方案、Agent 自主能力调研与 v1.7.0 前端基线实测。所有触点标注供联调计划引用；接口签名以主理人接口清单为准。§「Gap」10 项请产品负责人优先裁决 1/2/3/10。
