# GLM-Chat v1.3「生态位」MCP 支持功能规格书（PRD）

**日期**：2026-10-15
**类型**：PRD / 功能规格书
**参与成员**：方向明（主理人 / Grill 决策方）、产品通（产品管理专家 / 调研与撰写）
**产品**：GLM-Chat v1.3.0（主题「生态位」——MCP 客户端支持，单功能独立成版）
**PRD 状态**：v1.1（2026-10-15 产品负责人 grill 会话四问裁决完毕，W0 已冻结；裁决记录见 §10）

---

## 📌 TL;DR（执行摘要）

- **核心目标**：v1.3.0 引入 MCP（Model Context Protocol）客户端支持，把 GLM-Chat 从「单机工具执行者」升级为「**本地 MCP 宿主**」，补上工具生态这块最大短板——并且用 v1.2 已交付的护栏哲学（确认矩阵 / 审计 / 熔断）接住外部工具面，**开放不以信任为代价**。
- **关键决策**（Grill 会话七项，见文末决策记录）：范围 = stdio + Streamable HTTP 传输、tools 能力优先；实现 = **手写最小客户端**（零第三方依赖，守住 Python 3.10+ 与 onefile 打包铁律）；安全 = 分层护栏模型（服务器默认关 + 工具三档注解推导 + 后端二次 enforce + 全量审计 + 接入 R4 熔断）；配置 = Claude 兼容 `mcp_servers.json` + 一键导入；协议 = 钉死 2025-06-18 最新稳定规范；发布 = MCP 独立成 v1.3.0。
- **工作量**：约 21 人日（19 开发 + 2 回归）；单人全职约 4.5 周 / 2 人并行约 3 周。
- **下一步**：W0 已冻结（§10 四问 2026-10-15 裁决：DPAPI 字段级加密捆绑 / 仅 full 角色 / 启用时环境预检测+失败兜底 / instructions 展示不注入），进入 W1 配置先行（R2）。

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| 推荐方案 | v1.3.0「MCP 支持」：手写最小 MCP 客户端（stdio + Streamable HTTP）+ Claude 兼容配置 + 分层护栏集成，单批发布 |
| 优先级 | P0 四项（R1 协议核心 / R2 配置管理 / R3 分层护栏 / R4 工具注入执行）+ P1 两项（R5 设置面板 / R6 生命周期）+ P0 一项合规（R7 测试契约）；全部纳入，无降级项 |
| 预期影响 | 守住「BYOK + 本地 + 深执行 + MCP」桌面端无人占据的卡位（竞析窗口期判断）；把 v1.2 信任基建转化为生态准入的叙事资产；MCP 资产零迁移成本（Claude 兼容） |
| 资源需求 | 约 21 人日；单批发布，复用 v1.2 的 DoD 发布门（契约差分 + 验收走查 + 冒烟 + UI 契约） |
| 风险等级 | 中——手写客户端协议正确性、外部服务器质量参差、只钉新版挡掉旧服务器、弹窗疲劳、stdio 子进程杀软误报 |

---

## 1. 产品目标

v1.3 是 v1.2「信任版」之后的能力扩张版，但扩张的只有**工具来源**，不放宽**信任边界**。三个目标：

- **G1 生态位卡位**：MCP 正成为工具接入的事实标准（竞析：缺席有边缘化风险；Cherry Studio 已上 MCP/WebDAV/知识库全家桶，Claude Code 有 MCP 生态）。本品在「BYOK 自带 Key + 完全本地 + 直接 Agent 执行」的交集无人占据（v1.2 竞析卡位结论），MCP 是这块卡位上唯一缺失的生态拼图——补上它且不破坏单文件零安装、数据不出本机的定位。
- **G2 信任不退让**：MCP 是本品史上开放程度最大的功能——stdio 服务器就是**任意本地代码执行**。设计上对齐官方规范 2025-06-18 的安全建议（原文 SHOULD：人类在环可拒绝、调用前展示工具输入、确认提示、结果校验、超时、日志审计），并把 v1.2 的三档确认矩阵 / 审计日志 / R4 熔断全套继承到 MCP 工具面。注解（annotations）按规范视为**不可信输入**：只用于推导默认档位，永不放宽到 off。
- **G3 零迁移成本**：配置格式采用 Claude Desktop 兼容的 `mcpServers` 结构 + 一键导入 `claude_desktop_config.json`——用户从任意 MCP 服务器 README 抄来的配置直接可用，存量资产 5 分钟迁完。

**衡量方式**（零成本本地指标，数析口径扩展，不引入遥测）：MCP 服务器启用数 / 人均、MCP 工具调用占比（相对内置工具）、确认率与拒绝率、MCP 调用失败率与超时率、R4 熔断触发中 MCP 序列占比、Claude 配置导入功能使用率。v1.3.0 上线后纳入 14 项本地指标基线做复盘。

---

## 2. 用户故事

- **US-1（画像 A，主力）**：作为按量付费的个人开发者，我希望把 Claude Desktop 配置或社区文档里的 MCP 服务器直接粘贴 / 导入进 GLM-Chat，让 Agent 调用外部工具（查数据库、调 API、读 Notion），以便不开第二个客户端就能用整个 MCP 生态。
- **US-2（画像 A，核心安全故事）**：作为不敢放任 Agent 的用户，我希望每个 MCP 工具调用按我配的档位确认——标注破坏性的每次确认、标注只读的会话内首次确认、未标注的保守每次确认，以便开放工具面不放宽失控面。
- **US-3（画像 D，重度假设人群）**：作为重度 Agent 用户，我希望 MCP 工具同样受循环熔断保护（同工具同参数 ×3 / 连续 15 步无进展即暂停），以便外部工具抽件时不会烧钱到天亮。
- **US-4（画像 B）**：想用远程工具服务的开发者：我希望连远程 HTTP MCP 服务器（Streamable HTTP），以便使用云端封装的各类 API 工具。
- **US-5（全体，审计控）**：作为审计控，我希望每次 MCP 调用的服务器 / 工具 / 参数摘要 / 我的决策都落在本地审计日志（复用 v1.2 审计查看器可查），以便事后追溯 Agent 到底通过外部工具做了什么。

---

## 3. 需求论证（战略窗口与前置条件）

- **信任优先于能力扩张的执行结论**（瑞思，v1.2）：v1.2 已交付信任地基（R1–R6 全部落地，62 测试通过），「护栏缺位时开放外部工具 = 放大失控」的前置条件已经解除——roadmap 原文：「R2+R4 → MCP（外部工具必须先进护栏，v1.3 前置条件）」。
- **MCP 标准化窗口**（竞析）：MCP 正成工具接入事实标准，缺席有边缘化风险，但协议仍在演进——v1.3 接入、钉死一个稳定规范版本、每季度重估，是已批准的应对策略。
- **Cherry Studio 上攻的对冲**（竞析）：其 682 open issues、50+ 服务商、MCP 全家桶执行力最强；若其补 Agent 执行能力，本品卡位削弱。本品对冲 = 执行深度（v1.0 起即有）+ MCP（本 PRD）+ 成本透明（R5 已交付）。
- **社区预期基线**（瑞思）：多模型已由 v1.2 R6 满足，跨平台明确后置 v2.0；MCP 是同类项目用户默认预期中**唯一未满足项**。
- **反共识警告的状态**：多模态/GLM-6V 仍不进 v1.3（护栏成熟度门不变），本 PRD 不触碰。

---

## 4. GitHub 对标项目调研（2026-10-15 检索，GitHub connector）

### 4.1 对标项目矩阵

| 项目 | Star | 形态 | MCP 能力 | 传输 | 配置方式 | 权限/确认 | 对本品启示 |
|---|---|---|---|---|---|---|---|
| modelcontextprotocol/python-sdk | 24.5k | 官方 Python SDK | 客户端+服务器 | stdio / Streamable HTTP / SSE | — | — | 协议行为基准；附带 Inspector 可作交叉验证工具。**不引入**（Python 3.11+ 与重依赖冲突零依赖铁律） |
| nanbingxyz/5ire | 5.3k | Electron 桌面 AI 助手 + MCP 客户端 | tools + prompts | 依赖 Python/Node/uv 运行时（stdio 类） | UI + 服务器市场 | README 未明示 | 桌面 MCP 客户端形态验证；服务器市场是供应链信任争议点（本品不做） |
| daodao97/chatmcp | 2.2k | Flutter 跨平台聊天客户端 | tools | stdio + SSE | `mcp_server.json`，**Claude 兼容 mcpServers 格式** | "Auto Choose MCP Server" | 配置格式兼容是行业基线，直接采纳；需预装 uvx/npx |
| AI-QL/tuui | 1.1k | 桌面 MCP 客户端 | tools | — | — | — | 小众但证明独立桌面 MCP 客户端需求存在 |
| indragiek/Context | 805 | 原生 macOS MCP 客户端 | — | — | — | — | 本品 Windows 单文件零安装形态差异（macOS 是 v2.0 议题） |

生态规模佐证：GitHub 检索 "model context protocol client" 命中 **1764 个仓库**；官方 SDK 24.5k star。

### 4.2 官方规范关键结论（modelcontextprotocol/modelcontextprotocol，2025-06-18 版）

- **工具协议面**（tools.mdx）：`tools/list`（游标分页）/ `tools/call`（name + arguments）/ `notifications/tools/list_changed`；结果含 `content` 数组 + `structuredContent` + `isError`；协议错误（JSON-RPC error）与工具执行错误（isError: true）双通道。
- **生命周期**（lifecycle.mdx）：客户端 MUST 先发 `initialize`（protocolVersion + capabilities + clientInfo）→ 收响应 → 发 `notifications/initialized`；HTTP 传输后续请求 MUST 带 `MCP-Protocol-Version` 头；stdio 关闭流程 = 关 stdin → 等待退出 → SIGTERM → SIGKILL；所有请求 SHOULD 有超时与取消。
- **版本协商语义**：客户端发其支持的最新版；服务器响应它支持的最新版；**客户端不支持服务器响应的版本时 SHOULD 断开**——这正是「只钉 2025-06-18」决策的协议依据，错误响应里 `data.supported` 会带上服务器支持的版本列表（用于我们的错误文案）。
- **安全建议**（tools.mdx 原文 SHOULD 列表）：人类在环可拒绝 / 调用前展示工具输入 / 确认提示 / 校验结果 / 实现超时 / 记录审计——本品分层护栏逐条对齐（见 R3）。
- **注解不可信原则**（tools.mdx Warning）：客户端 MUST 将工具注解（`readOnlyHint` / `destructiveHint` / `idempotentHint` / `openWorldHint`，schema.mdx 已核实字段名）视为不可信，除非来自可信服务器——故本品只用注解**推导默认档位**（最宽到 session），任何情况下不因注解自动关闭确认。

### 4.3 卡位结论

桌面端「BYOK + 本地 + 深执行 + MCP」交集仍无人占据：Cherry Studio 执行弱、Claude Desktop 生态封闭且仅 Claude、Cline 绑 IDE、5ire/chatmcp 非 Windows 单文件零安装形态。本品的差异化不在「也支持 MCP」，而在「**带护栏的 MCP**」——把 v1.2 的信任资产变成生态准入的卖点。

---

## 5. 数据依据

- **本地指标基线**（数析口径，零成本）：14 项现有指标 + v1.3 扩展 6 项 MCP 指标（见 §1 衡量方式）。不引入遥测（遥测最小版是独立 PRD，v1.3 不捆绑）。
- **生态规模数据**：GitHub star / 仓库数（2026-10-15 检索，见 §4）。
- **如实说明的数据缺口**：无真实 MCP 使用数据（无遥测）、无用户存量 MCP 资产分布——「用户会启用几个服务器」类判断为假设；排期以工作量与依赖为锚，不依赖缺失数据（沿用 v1.2 路线图纪律）。

---

## 6. 需求池

### P0（信任与主链，全部纳入）

**分组论证**：R1/R2 是主链（没有客户端与配置就没有功能），R3 是信任边界（没有护栏就不允许开放），R4 是价值出口（工具到不了 LLM 面前就等于没接），R7 是发布门。四项缺一，G1/G2 落空。

| 编号 | 需求 | 优先级 | 验收标准 | 估算工作量 |
|---|---|---|---|---|
| R1 | MCP 协议客户端核心（手写最小客户端）：initialize/initialized 握手；tools/list 游标分页；tools/call；ping；notifications/tools/list_changed（标记失效）；stdio + Streamable HTTP 双传输；全请求超时 + 取消；钉死协议版本 2025-06-18；HTTP 请求带 MCP-Protocol-Version 头；客户端能力声明最小集（不接 sampling/elicitation/roots，服务器发起时返回 -32601） | P0 | Given 启用一个 stdio 服务器，When 测试连接，Then 完成握手并返回工具清单与服务器信息；Given 工具数超过一页，When tools/list，Then 跟随 nextCursor 取全量；Given 服务器仅支持旧版协议，When 握手，Then 连接失败且错误文案包含该服务器支持的版本列表；Given 调用超过超时阈值，When 触发，Then 发送取消并返回人话错误；Given HTTP 服务器，When 任一请求，Then 带 MCP-Protocol-Version 头 | 5.5 人日（stdio 帧+握手 2 / HTTP 传输 1.5 / 列表分页+调用 1.5 / 超时取消与错误 0.5） |
| R2 | 服务器配置管理：新增 `~/.glm-chat/mcp_servers.json`，`mcpServers` 结构（name → {command/args/env 或 url/headers} + 扩展键 enabled / tierOverrides）；Claude 兼容；一键导入 `claude_desktop_config.json`（同名冲突跳过并报告）；CRUD；**不碰 config.json** | P0 | Given 用户粘贴 Claude 格式配置，When 保存，Then 服务器出现在列表且可启用；Given 导入含 3 个服务器的 claude_desktop_config.json，When 导入，Then 3 个全部出现（默认 enabled=false）且冲突项有明确提示；Given 保存配置，When 跑契约差分测试，Then config.json 内容逐字节不变 | 2 人日（文件结构+CRUD 1 / 导入+测试连接 1） |
| R3 | 分层护栏集成：服务器级开关（新服务器默认关，opt-in 启用）；工具级三档 always/session/off，默认值由注解推导（readOnlyHint=true → session；destructiveHint=true 或无注解 → always）；用户逐工具覆盖（tierOverrides）；always 档确认框带「本会话内不再提示」勾选（复用 R2 信任态）；后端 `mcp_call_tool` 执行前二次 enforce（防前端绕过）；全量审计入 `audit_log.jsonl`（op=mcp_call，含服务器/工具/参数摘要/决策）；接入 R4 三维熔断（同工具同参数 ×3 / 连续 15 步无进展） | P0 | Given 新服务器且工具无注解，When Agent 调用，Then 每次弹确认；Given 工具 readOnlyHint=true，When 同会话第 2 次调用，Then 不再确认；Given 用户点拒绝，When 确认框交互，Then 工具不执行且向 Agent 返回拒绝原因；Given 绕过前端直接调后端，When 档位为 always，Then 后端拒绝执行；Given 循环调用同一 MCP 工具同参数，When 第 3 次，Then R4 熔断暂停并高亮序列 | 3 人日（注解推导+档位判定 1.5 / 后端 enforce+审计 1 / R4 熔断接入 0.5） |
| R4 | 工具注入与执行：`build_tools(role, include_mcp=False)` 新增可选参数（默认路径输出不变，契约逐字节比对天然通过）；工具命名 `mcp__<server>__<tool>`（GLM/OpenAI 函数名合法字符集内）；仅 full 角色注入 MCP 工具；Agent 循环分发 MCP 调用；结果渲染（文本 / structuredContent 序列化 / isError 态 / 超长复用 cache_tool_output 截断落盘 + read_more）；错误人话映射（握手失败 / 版本不匹配 / 超时 / 服务器崩溃 / 工具不存在） | P0 | Given 无启用服务器，When build_tools(role)，Then 输出与 v1.2 逐字节一致（契约差分测试门）；Given 启用含 2 个工具的服务器，When Agent 循环，Then LLM 收到 2 个 mcp__ 前缀工具定义且调用成功回传；Given 工具返回结构化内容，When 执行，Then 序列化为文本回传 Agent；Given 输出超长，When 返回，Then 截断落盘且可 read_more 取全 | 2.5 人日（include_mcp+命名 0.5 / 循环分发+结果渲染 1.5 / 错误人话 0.5） |

### P1（体验与稳健，全部纳入）

| 编号 | 需求 | 优先级 | 验收标准 | 估算工作量 |
|---|---|---|---|---|
| R5 | 设置面板与工具可视化管理：设置页新增「MCP 服务器」区块——列表（名称 / 状态灯 / 工具数 / 开关 / 编辑 / 删除）、添加编辑表单（stdio: command+args+env；HTTP: url+headers）、测试连接、逐工具档位查看与覆盖、导入 Claude 配置按钮；运行时错误走 R3 toast 模式 | P1 | Given 启用服务器，When 面板打开，Then 显示工具数与每个工具当前档位；Given 服务器启动失败，When 启用，Then 状态灯变红且 toast 明示原因；Given 修改某工具档位，When 保存，Then 下次调用按新档位执行；Given 走 UI 契约校验，Then 新增 DOM id / class 只增不改 | 3 人日（列表+表单 1.5 / 档位覆盖 UI 0.5 / 状态与导入 1） |
| R6 | 进程生命周期与运行环境：stdio 服务器按需拉起（首次调用或启用时）；空闲超时回收；应用退出按规范关闭（关 stdin → 等待 → SIGTERM → SIGKILL）；崩溃自动标记 + 下次重拉一次；uvx/npx 缺失检测与引导（预检测策略见 Q2）；env 明文存储风险在面板明示 | P1 | Given 服务器启用，When 应用退出，Then 子进程全部终止无残留；Given 服务器进程崩溃，When 下次调用，Then 自动重拉一次，仍失败则明确报错；Given 环境缺 npx，When 启用依赖 npx 的服务器，Then 提示缺少什么、去哪装 | 1.5 人日（拉起/回收/退出 1 / 环境检测与引导 0.5） |

### P0 合规（发布门，内嵌各需求）

| 编号 | 需求 | 优先级 | 验收标准 | 估算工作量 |
|---|---|---|---|---|
| R7 | 测试与契约合规：新增 `tests/test_v13_mcp.py`——协议帧单测（stdio 打桩 / HTTP mock：握手 / 分页 / 调用 / 超时 / 取消 / 版本不匹配）、护栏集成测试（档位推导 / enforce / 审计落盘）、契约差分回归（build_tools 默认路径逐字节 + get_api_info + config.json 不污染）、UI 契约只增不改 | P0 | pytest 全绿（62 既有 + 新增）；`check_contract.py` PASS；`get_api_info` 输出与 legacy 逐字节一致；新增 js_api 方法全部登记进 `_V12_EXTRA` 隐身集合 | 1.5 人日（协议单测 0.5 / 护栏测试 0.5 / 契约回归 0.5） |

### P2 → Non-goals / 后续路线图（不在 v1.3.0）

SSE 传输、resources/prompts 能力、OAuth 2.1 远程认证、sampling/elicitation/roots、多协议版本协商、官方 mcp SDK、MCP 服务器市场/一键安装；遥测最小版、DND 免打扰、API Key DPAPI 加固（捆绑与否见 Q1）、审计查看器增强——均拆独立 PRD。

---

## 7. 关键流程

**7.1 服务器启用流程（R2/R5/R6）**
```
设置 → MCP 服务器 → 添加/导入（Claude 兼容 JSON）
  └─> 保存至 mcp_servers.json（默认 enabled=false）
        └─> 用户打开开关
              ├─> 展示将执行的命令/URL、env 键名、工具清单（信任仪式）
              ├─> 测试连接（initialize 握手 → tools/list）
              │     ├─> 失败（版本不匹配/缺运行时/进程崩溃）→ 红状态灯 + toast 人话
              │     └─> 成功 → 绿状态灯 + 工具数 + 注解推导的默认档位
              └─> 启用：按需拉起 stdio 子进程（或校验 HTTP 可达）
```

**7.2 MCP 工具调用护栏流程（R3，对齐 v1.2 R2 7.1 设计）**
```
Agent 发起 mcp__<server>__<tool> 调用
  └─> 查该工具档位（tierOverrides 用户覆盖 > 注解推导默认）
       ├─> off ──> 直接放行，记审计
       ├─> session 且本会话已信任 ──> 放行，记审计
       └─> always / session 首次 ──> 确认框（服务器名 / 工具名 / 参数全文 / 档位来源）
            ├─> 用户拒绝 ──> 不执行，向 Agent 返回拒绝原因，记审计
            ├─> 用户同意 ──> 执行，记审计
            └─> 勾选「本会话内不再提示」──> 同意 + 会话信任态
  ※ 后端 mcp_call_tool 执行前再查一次档位（防绕过）；同工具同参数 ×3 / 15 步无进展 → R4 熔断
```

**7.3 版本不匹配与错误处理流程（R1）**
```
initialize 握手
  ├─> 服务器响应 protocolVersion ≠ 2025-06-18 且非 2025-06-18
  │     └─> 断开，错误文案：「该 MCP 服务器支持协议版本 X，GLM-Chat 支持 2025-06-18。
  │           请升级该服务器，或在设置中暂时禁用它。」+ data.supported 列表
  ├─> 调用超时 ──> 发送取消通知，返回人话错误（可提高超时？v1.3 固定阈值，见假设）
  ├─> 服务器崩溃 ──> 标记 + 自动重拉一次，仍失败 → 红状态灯 + 建议重启服务器
  └─> 工具不存在 ──> -32602 映射为「服务器未提供该工具（可能已升级/卸载）」
```

---

## 8. Non-goals（明确不做）

1. **不做 SSE 传输**：规范已弃用；Streamable HTTP 覆盖远程场景。用户拿到的 SSE 服务器配置会得到明确的不支持提示。
2. **不做 resources / prompts 能力**：tools 优先（5ire  badges 与 chatmcp 均以 tools 为核心价值）；协议消息与 UI 后置 v1.3.x 评估。
3. **不做 OAuth 2.1 远程认证**：远程 HTTP 服务器仅支持无认证或静态 token 头；OAuth 留 v1.4（涉及浏览器回调与 token 刷新，工程面大）。
4. **不做 sampling / elicitation / roots**：客户端高级能力，v1.3 不接；服务器发起时按规范返回方法未找到错误，功能降级但不崩溃。
5. **不做多协议版本协商**：只钉 2025-06-18（Grill 已裁决）；旧服务器明确报错并给出升级指引，不做向下兼容。
6. **不引入官方 mcp Python SDK**：零第三方依赖铁律 + Python 3.10+ 底线 + onefile 打包零风险；v1.4 评估官方 SDK（触发条件：需 OAuth/sampling 等高级能力时）。
7. **不做 MCP 服务器市场 / 一键安装**：供应链信任与「信任版」定位冲突（5ire/chatmcp 有市场，本品明确不跟）；手动配置 + Claude 导入已覆盖主流路径。
8. **不碰红线**：不改 config.json（新配置独立文件）、50 个 js_api 契约零变更（新方法进 `_V12_EXTRA` 隐身集合）、UI 契约只增不改、不引入第三方依赖、`GLM-Chat.spec` 打包配置不动。

---

## 9. 时间线 & 里程碑（单批发布）

> 单人全职约 4.5 周 / 2 人并行约 3 周（基于 v1.2 模块化结构与 21 人日估算）。

| 阶段 | 主题 | 关键交付 | 工作量 | 周期参考 | 负责方 | 风险 |
|------|------|----------|--------|----------|------|------|
| W0 | 需求冻结 | 本 PRD 审定 + 第 10 节四问裁决 | — | 2 天 | 产品 | 决策延迟顺延全链 |
| W1 | 配置先行 | R2 mcp_servers.json + CRUD + Claude 导入 | 2 人日 | 1 周 | 工程 | 导入冲突语义 |
| W1–W2 | 协议核心 | R1 手写客户端（stdio/HTTP/握手/分页/调用/超时取消） | 5.5 人日 | 1.5 周 | 工程 | 帧处理/大消息/并发正确性 |
| W2–W3 | 护栏集成 | R3 注解推导 + 档位判定 + 后端 enforce + 审计 + R4 熔断接入 | 3 人日 | 1 周 | 工程 | 弹窗疲劳平衡 |
| W3 | 工具出口 | R4 include_mcp + mcp__ 命名 + 循环分发 + 结果渲染 + 错误人话 | 2.5 人日 | 3 天 | 工程 | 非 GLM 端点工具调用兼容 |
| W3–W4 | 体验与稳健 | R5 设置面板 + R6 生命周期（可并行） | 4.5 人日 | 1 周 | 工程+设计 | 子进程误报/退出残留 |
| W5 | 回归发布 | R7 契约差分 + UI 契约 + 冒烟（导入→启用→确认→拒绝→审计→熔断六步）+ 发布 v1.3.0 | 2 人日 | 3 天 | 工程+产品 | 契约漂移 |

**关键路径**：R2 配置结构 → R1 协议核心 → R3 护栏判定 → R4 工具注入执行 → R5 面板联调。R6 与 R7 全程并行/内嵌。

**DoD（硬门槛，复用 v1.2）**：① pytest 契约差分通过（`build_tools` 默认路径逐字节不变 + `get_api_info` 一致 + config.json 未污染）；② 需求验收标准逐条走查通过；③ 手动冒烟六步（导入 Claude 配置 → 启用服务器 → Agent 调用弹确认 → 拒绝后 Agent 收到原因 → 审计日志可查 → 循环触发熔断）；④ UI 契约 `check_contract.py` PASS；⑤ `node frontend/build.js` 构建成功（新增 2 个前端模块）。

---

## 10. 待确认问题（2026-10-15 已裁决，W0 冻结）

> 以下四问经 grill-me 会话由产品负责人逐项裁决（2026-10-15），全部采信推荐方案。裁决记录：Q1 字段级 DPAPI 捆绑 / Q2 仅 full / Q3 预检测+兜底 / Q4 展示不注入。四项共同内核：外部输入（注解 / instructions / command 环境）一律不可信，只用于推导默认行为或展示，永不自动放宽信任边界。

1. **DPAPI 加固捆绑 v1.3.0——已裁决：捆绑，字段级加密**（+0.5 人日）。实现口径：ctypes 调 `CryptProtectData`/`CryptUnprotectData`（stdlib，零新依赖，Python 3.10+ / onefile 兼容）；**只加密 env 值与 header 值**，command/args/键名保持明文（Claude 兼容结构可读、可手改、导入不受影响）；解密失败（换机器/换 Windows 用户）按明文兜底并记日志，不锁死用户。理由：MCP 配置密钥密度比 config.json 高一个量级；路径原稿力荐项。
2. **uvx/npx 运行环境预检测——已裁决：方案 A（启用时预检测）+ B 作兜底**。实现口径：启用时 `shutil.which(command)` 解析 PATH（Windows 自动走 PATHEXT，覆盖 .cmd/.bat 包装器与完整路径），缺失则阻断启用并明示缺什么、去哪装（uv / Node 官网指引）；which 通过但仍启动失败（如 node 装了缺全局依赖）走 R6 兜底：崩溃标记 + 自动重拉一次 + 红状态灯人话报错。A 拦明显缺失，B 接残余故障。
3. **MCP 工具仅进 full 角色——已裁决：接受，仅 full**。ro（只读）/ chat（纯对话）不含 MCP 工具。核心理由：readOnlyHint 是规范明示的不可信输入（服务器自签），拿它往弱安全角色放宽保证与信任哲学冲突；full 角色下 readOnly 工具默认 session 档（会话内确认一次后放行），体感已接近只读。只读 MCP 进 ro 留作 v1.3.x 优化（待本地指标数据支撑）。
4. **server instructions——已裁决：面板展示，不自动注入系统提示**。initialize 响应 instructions 在设置面板 MCP 服务器详情可见（用户掌握「服务器想对 Agent 说什么」的情报），不进入任何 prompt 组装路径（提示注入面为零）；逐服务器 opt-in 注入开关留 v1.3.x（默认关）。

---

## ✅ 行动清单

| # | 行动 | 负责方 | 时间窗 |
|---|------|------|------|
| 1 | 产品负责人审定本 PRD，裁决第 10 节四个待确认问题（W0 冻结） | 产品负责人 | W0 |
| 2 | R2：mcp_servers.json 结构 + CRUD + Claude 导入 + 测试连接 | 工程 | W1 |
| 3 | R1：手写 MCP 客户端核心（stdio/HTTP 双传输 + 握手/分页/调用/超时取消） | 工程 | W1–W2 |
| 4 | R3：注解推导档位 + 确认 UI + 后端 enforce + 审计 + R4 熔断接入 | 工程 | W2–W3 |
| 5 | R4：build_tools include_mcp + mcp__ 命名 + 循环分发 + 结果渲染 + 错误人话 | 工程 | W3 |
| 6 | R5 设置面板 + R6 生命周期（并行） | 工程+设计 | W3–W4 |
| 7 | R7：test_v13_mcp.py + 契约差分回归 + UI 契约校验 | 工程 | W1–W5 内嵌 |
| 8 | 冒烟六步 + 发布 v1.3.0（VERSION/APP_VERSION → 1.3.0）+ 发布说明（stdio 子进程杀软提示） | 工程+产品 | W5 |

---

## ⚠️ 待确认 / 假设

- **待确认**：见第 10 节四问（DPAPI 捆绑 / 环境预检测 / 角色范围 / instructions 注入）。
- **关键假设**：① 工作量基于 v1.2 模块化结构（backend/services 分层 + frontend/src 模块化 + 契约测试网）与单人 velocity；手写客户端按 2025-06-18 规范核心方法集估算，若规范细节复杂化（大消息分片、并发请求、进度通知）需追加缓冲；② 主流 MCP 服务器遵循 2025-06-18 或更新版本——旧版被挡是已裁决取舍（错误文案含升级指引兜底）；③ 用户接受 stdio 服务器需本机 Python/Node 运行时（与 5ire/chatmcp 同款约束，行业基线）；④ MCP 工具调用兼容主流 OpenAI 兼容端点的 function calling（v1.2 R6 已验证 GLM/DeepSeek 路径）；⑤ v1.3.0 不引入遥测，所有规模判断以上线后本地指标校准。
- **Non-goals**：见第 8 节八项。

---

## 📚 数据来源 & 决策记录

**GitHub 调研（2026-10-15，GitHub connector 检索）**：modelcontextprotocol/python-sdk（README + src/mcp 目录结构）、nanbingxyz/5ire（README）、daodao97/chatmcp（README）、AI-QL/tuui、indragiek/Context；生态规模检索 "model context protocol client"（1764 仓库）。
**官方规范（modelcontextprotocol/modelcontextprotocol，2025-06-18）**：`docs/specification/2025-06-18/server/tools.mdx`（协议消息 / 安全建议 / 注解不可信 Warning）、`basic/lifecycle.mdx`（握手 / 版本协商 / 关闭流程 / 超时）、`schema.mdx`（注解字段名核实：readOnlyHint / destructiveHint / idempotentHint / openWorldHint）。
**既有文档**：`prd-glmchat-v12-trust-2026-10-15.md`（结构模板 / 用户画像 / 卡位结论）、`roadmap-update-glmchat-2026-10-15.md`（v1.3 范围与 MCP 前置条件）、`competitive-analysis-glmchat-2026-10-15.md`（窗口期判断）、`v12-delivery-report-2026-10-15.md`（v1.2 落地状态）。
**代码库勘察**：`backend/api.py`（`_V12_EXTRA` 隐身机制）、`backend/tools_schema.py`（工具 schema 单一数据源）、`backend/services/guard_service.py`（三档矩阵 + 审计）、`tests/test_api_contract.py`（build_tools 逐字节比对范围）、`frontend/src/60-agent-loop.js`（loadBackendTools / 工具分发）、`GLM-Chat.spec` + `开发说明.txt`（零依赖 / Python 3.10+ / 打包命令）、`frontend/src/` 模块清单（新模块拟编号 29-mcp.js / 62-mcp-exec.js，28-audit-viewer.js 已存在可复用）。

**Grill 会话决策记录（2026-10-15，产品通 × 主理人）**：

| # | 决策分支 | 裁决 | 核心理由 |
|---|---|---|---|
| 1 | 功能选择 | MCP 支持 | v1.3 头号战略项；GitHub 参考最丰富；R2 护栏前置条件已具备 |
| 2 | 能力范围 | stdio + Streamable HTTP，tools 优先 | 覆盖生态 90%+；SSE 已弃用；resources/prompts 后置 |
| 3 | 实现路线 | 手写最小客户端 | 零新依赖 / Python 3.10 底线 / 打包零风险 / 协议代码可自审计（信任版同构） |
| 4 | 安全模型 | 分层护栏 | 服务器默认关 + 注解推导三档 + 后端二次 enforce + 全量审计 + R4 熔断 |
| 5 | 配置与 UX | Claude 兼容 + 全套面板 | 行业基线配置格式；一键导入零迁移；mcp__ 命名 + include_mcp 参数保契约 |
| 6 | 协议版本 | 只钉 2025-06-18 | 规范版本协商语义支持；旧服务器明确报错兜底 |
| 7 | 发布范围 | MCP 独立成 v1.3.0 | 一个 PRD 一个功能；其余 v1.3 候选拆独立 PRD |
| — | 前提校验 | 「主要竞品是 PrimoCache」被拒绝 | PrimoCache 为 Windows 磁盘缓存软件，非同品类；竞品矩阵以 §4 调研为准 |

---

> 本 PRD 由产品通（产品管理专家）基于 Grill 会话决策、GitHub 调研与代码库勘察撰写，重要决策请由产品负责人审定。
