---
tags: [deep-research-report, status/review]
created: 2026-10-20
scope: Harbor-v18单版本全量实现方案
sources: "内部 1（本仓代码库+既有方案文档）/ 外部 0（外部依据见调研报告）"
search-mode: 代码库实测→方案合成
---

# 深度检索报告：《Harbor v1.8.0 单版本全量实现方案》

## 范围
- 查询范围：将 iteration-plan-v18-agent-2026-10-20.md + agent-autonomy-research-2026-10-20.md + 全网调研 R1-R25 修订**全部合并进单一版本 v1.8.0** 的可落地实现方案
- 基线：v1.7.0（721 passed / 契约 PASS / 安装器三 exe 已交付）
- 输入：本仓代码库实测（api.py / services/ / tools_schema.py / frontend/src/ / paths.py）+ 两份既有方案 + 调研终版修订表
- 输出：范围目标 / 模块与文件结构 / 数据结构 / 接口 / 流程 / 顺序依赖 / 兼容迁移 / 验证要点——可直接指导编码
- 检索模式：代码库实测（Grep/Read 已核实的文件与函数名）+ 方案合成；无新增外部检索（外部依据全部来自 deep-research-20261020-harbor-v18-v19-220e3984，URL 在其证据清单内）

## 核心结论
- [内] **单版本合并可行且建议如此**：三大能力（浏览器搜索/软件调用/本地协同）+ 放权四件套（任务授权/Plan-Act/澄清/检查点）+ 信任棒（MCP 门控/日志/readiness/prompt-CI）合计约 54.5 人日，模块间依赖有序（guard 扩展是放权与搜索的共同前置），合版避免两次回归与两次发布工程
- [内] **契约零漂移的合并打法**：`build_tools(role, include_mcp=False, include_agent=False)` 第三可选参数承载全部新工具；约 28 个新 js_api 全进 `_V12_EXTRA`；新配置全部独立文件（software.json/hybrid.json/memory.json/search_cache.json）；guard.json 与 mcp_servers.json 纯增键；sessions.json 纯增字段——**契约差分与 UI 契约天然通过**
- [内] **最关键的一条实现纪律**：浏览器提取结果必须经 **pywebview js_api 回调**回传（`on_page_data`），禁用 evaluate_js 返回值——外部站 Strict CSP 下后者必失败；搜索次窗口用独立 WebView2 profile + 下载默认禁 + 外链进系统浏览器
- [内+外] **dual-LLM-lite 是搜索的安全骨架**：主模型只看本地读取器产出的结构化 JSON（带 provenance 包裹），读取器无工具权、schema 约束输出——注入防御从提示词层升到架构层（依据调研报告 §②，URL 见该报告证据清单 #3）
- [内+外] **两处「先实测再定稿」项**：R23 剪贴板 UI 限制（Job Object READCLIPBOARD Flag 值未知，可能闭合 KNOWN_ISSUES §17）与 DeepSeek 模型线换代（preset 校准）——实现顺序中排最前（W0/W1），因其结论影响后续模块设计

## 关键要点（Key Takeaways）
- **一个版本号、四个内部里程碑**：v1.8.0（M1 地基周 → M2 能力周 → M3 放权周 → M4 信任周），每里程碑结束跑全量门禁，不允许累积未测代码跨里程碑
- **约 28 个新 js_api 全部隐身**：`get_api_info()` 输出与 legacy 逐字节一致是发布门，新方法入 `_V12_EXTRA` 是唯一合法通道
- **新增 8 个后端 service + 6 个前端模块 + 1 个 prompts 目录**，改动 10 个既有模块——文件清单见 §3，全部路径已按仓库现状核实
- **最大单项是浏览器搜索（11 人日）**：窗口通道+适配器+dual-LLM-lite+注入防御+面板+缓存+可选 API 加速器
- **验证七门**：pytest（721+新增）/ 契约差分 / check_contract / 构建幂等 / 安装器 e2e / 注入 fixture / 真机冒烟——外加 3 条基准任务链前后对比（token·TTFT·cache hit·确认次数）

## 证据清单
| # | 结论摘要 | 支撑 | 来源 |
|---|---------|------|------|
| 1 | 契约合并打法（include_agent/_V12_EXTRA/独立配置文件） | [内] | backend/api.py（_V12_EXTRA 现况）+ backend/tools_schema.py（build 签名）+ tests/test_api_contract.py |
| 2 | 浏览器提取须 js_api 回调（CSP 约束） | [内+外] | 调研报告证据 #2（deepwiki pywebview 安全模型）+ 本仓 05-bridge.js（window.pywebview.api 桥模式） |
| 3 | dual-LLM-lite 安全骨架 | [内+外] | 调研报告证据 #3（nomadx/red.ht/ai-tldr） |
| 4 | OWASP 楼层规则+TOFU 适配点 | [内+外] | 调研报告证据 #8（OWASP 门控）+ backend/services/mcp_service.py（derive_tier 现况） |
| 5 | estTokens 中文比校准 1.8→3.2-3.4 | [内+外] | 调研报告证据 #14 + frontend/src/40-auto-compact.js（现比值） |
| 6 | DeepSeek preset 需校准（旧型号 2026-07-24 退役） | [内+外] | 调研报告证据 #11（api-docs.deepseek.com）+ frontend/src/36-connect.js（PRESETS 现况） |
| 7 | Job Object 剪贴板 UI 限制待实测（R23） | [内+外] | 调研报告证据 #13（learn.microsoft.com）+ backend/services/sandbox_service.py（_UI_LEVELS 现况）+ KNOWN_ISSUES §17 |
| 8 | 模块清单与文件路径 | [内] | 本仓 backend/services/（21 个现存 service）+ frontend/src/（43 模块）+ backend/paths.py |

## 口径与来源（跨文档对比/专业术语查询时启用）
- 术语/指标口径：「js_api 隐身」= 入 `_V12_EXTRA` 使 `get_api_info()` 自省排除；「UI 契约」= check_contract.py 校验的 40 DOM id/13 onclick/43 callApi/39 CSS 类/21 主题变量（只增不改）；「task grant」= 进程内任务级授权（TTL+范围+除外清单）；「TOFU」= 首次见到的工具定义指纹钉住
- 实体解析：「Harbor」→ 本仓项目（aliases: GLM-Chat，数据目录 ~/.glm-chat 不变）；「M1-M4」= 本方案的四个内部里程碑（非发布版本）
- 数据状态：代码库实测截至 2026-10-20（VERSION=1.7.0，721 passed）；外部依据截至调研报告（2026-10-20）

## 来源分区
### 内部资料（本仓实测）
- backend/api.py（Api 门面/_V12_EXTRA/run_command 接线）
- backend/tools_schema.py（build_tools 契约面）
- backend/paths.py（CONFIG_DIR 与各配置文件路径）
- backend/services/（guard_service/mcp_service/mcp_transport_http/mcp_transport_stdio/local_model_service/cmd_service/sandbox_service/webdav_service 等 21 个现存 service）
- frontend/src/（43 模块：60-agent-loop/25-tool-exec/55-tool-route/26-guard/34-local-model/36-connect/29-mcp/37-webdav/40-auto-compact/30-history-shrink/35-frozen-compact 等）
- frontend/index.template.html（set-grid 设置浮层结构）
- tests/（24 个测试文件，721 passed 基线）
- deliverables/dev-plan/iteration-plan-v18-agent-2026-10-20.md + agent-autonomy-research-2026-10-20.md + sandbox-architecture-2026-10-19.md
- outputs/deep-research/deep-research-20261020-harbor-v18-v19-220e3984.md（全网调研 R1-R25，外部 URL 在其证据清单）

### 公开信息（0，本方案不新增外部检索）
- 无（全部外部依据经上述调研报告引入，本文件只做工程合成）

## 合成与核实方式（本任务为工程合成，无外部检索）
- 输入=代码库实测+既有两份方案+调研终版；无新增查询（外部依据全部经调研报告引入）
- 代码库核实方式：Grep/Read 逐项确认本方案引用的每个文件路径、函数名、常量名、配置键名真实存在（api.py:379 build_system_prompt、api.py:46 _V12_EXTRA、tools_schema.build、paths.CONFIG_DIR、mcp_service.derive_tier、sandbox_service._UI_LEVELS、40-auto-compact.js estTokens 比值、36-connect.js PRESETS）
- 外部主张均回溯到调研报告编号（R1-R25），不重复列 URL

---

# 正文档：Harbor v1.8.0 单版本全量实现方案

## 1. 版本范围与目标

**版本号**：VERSION 1.7.0 → **1.8.0**（`update_service.py` 回退常量同步）。
**范围**：一次性合入下列全部内容，不拆分：

| 棒 | 内容 | 人日 |
|---|---|---|
| 能力 | B 浏览器精准搜索（dual-LLM-lite+四层注入防御+面板+缓存+可选 API）/ S 外部软件调用 / H 本地模型协同（路由+readiness+template 探测） | 31 |
| 放权 | A 任务授权 L2+白名单 L4 / B Plan-Act / C 批量澄清 / D 检查点回滚 / F1 Reflexion 自反思环 / F2 跨会话记忆 | 16.5 |
| 信任 | V1 校验框架 / MCP 门控加固（楼层规则+TOFU+健康度）/ trace_id+消息数组日志 / prompt-CI / estTokens 校准 / DeepSeek·GLM 校准 / 剪贴板复核 / onboarding 向导 | 7 |

**目标（可证伪）**：① 非 GLM 端点获得受控搜索能力（注入 fixture 零触发）；② 确认弹窗/任务 -60%（L2+白名单）；③ 任务结果自检覆盖率 100%（Reflexion）；④ 同任务链 token -15%（提示词+记忆+estTokens 校准合力）；⑤ 721 既有测试零回归 + 新增约 200 项全绿。

## 2. 里程碑与实现顺序（W0-W12，单人约 11 周 / 2 人约 6-7 周）

```
W0  M1 地基（3 人日）
     · prompts/ 目录 + manifest + build_system_prompt 改造为读文件（R19 第一步）
     · tools_schema.build 增 include_agent 参数（默认 False，契约面先落）
     · api.py 批量登记新 js_api 名入 _V12_EXTRA（先占位后实现，防契约漂移）
     · R23 剪贴板 Flag 实测（Win32 探针：设 READCLIPBOARD 后子进程读剪贴板是否真被拦）
       → 结论落 KNOWN_ISSUES §17 修订 + sandbox_service strict 档是否加 Flag
     · R20 DeepSeek preset 校准（36-connect.js PRESETS：v4-flash/v4-pro+价格+1M ctx）
W1  M1 地基（4 人日）
     · guard_service 扩展：deny 清单（5 条永豁免）+ allow_rules（增删查+模式匹配）
       + task_grant（进程内：scope/TTL/除外/收回）+ 判定链重构
     · 26-guard.js：授权条 UI + 「升级为规则」快捷入口 + 规则管理
     · 审计 trace_id（api.py 生成 t_<ts36>_<rand4>，贯穿 plan/tool/audit）
W2  M2 能力（5 人日）H 组
     · hybrid_router.py：四类任务分类+三策略+预算+降级链+stats
     · local_model_service 扩展：readiness 8 项评分 + /api/show template 探测
     · 65-hybrid.js 配置 UI + 34-local-model.js readiness 面板
W3-W5 M2 能力（11 人日）B 组——最大单项
     · search_browser.py（pywebview 次窗口：独立 profile/load_url/on_page_data 回调/下载禁/外链进系统浏览器）
     · search_adapters.py（Bing/DDG/Baidu/Google 四预设+generic：URL 模板+纯函数解析器，fixture 可测）
     · search_extract.py（readability 风格正文提取→markdown）
     · search_service.py（编排+缓存+过滤去重+注入包裹+audit）
     · dual-LLM-lite：hybrid_router 驱动本地读取器（schema 约束 JSON，无指令权）
     · 39-search-panel.js（结果列表/原文预览/人工接管/反爬检测）
     · browser_search/browser_open js_api + 25-tool-exec 分发 + include_agent 工具定义
W6  M2 能力（3.5 人日）S 组
     · software_service.py（software.json 注册表+PATH/winreg 探测+--version 验身份+cli 沙箱执行/gui FindWindowW 核验/uri 协议+异常人话矩阵）
     · 64-software-panel.js（探测列表/测试调用/自定义向导）
     · software_* js_api + 分发 + 工具定义
W7  M2 能力（2.5 人日）V1+F1
     · validation_service.py（6 类校验器注册表+reformulate 重试）
     · reflect：hybrid validate 类 + verdict 结构化三元组 + 补做循环（≤2）
W8-W9 M3 放权（7.5 人日）Plan-Act+C+D
     · plan_service.py（计划生成/状态机/偏差检测/重规划/检查点调度）
     · 66-plan.js（计划卡/批准/编辑/偏差暂停条）
     · clarify：批量问题清单（≤5 问+默认值+单张表单）
     · checkpoint：git 锚点/非 git 快照（≤200MB/500 文件/保留 3 份）/回滚入口
W10 M4 信任（3.5 人日）
     · mcp_service：楼层规则（delete_/drop_/purge_/wipe_→L5）+schema hash TOFU+健康度三态
     · 29-mcp.js 健康徽标；estTokens 校准（40-auto-compact.js：中文 1.8→3.2-3.4+usage 对账告警）
     · 68-onboarding.js（Use Case Wizard：3-4 问/Skip/ETA/计量表/杀手特性揭示）
     · R21 GLM web_search 升级结构化 API（60-agent-loop.js web_search 分支）
W11 M4 信任（2 人日）F2 记忆
     · memory_service.py（memory.json 结构化三类+关键词检索+规则提取「以后都…」+用户可查可删）
     · 67-memory.js 管理 UI + 系统提示注入
W12 回归发布（2 人日）
     · 全量门禁+基准链复跑+注入 fixture+审查+打包四 exe+发布说明
```

**关键路径**：W1 guard 扩展 → W2 hybrid → W3-W5 搜索 → W8-W9 Plan-Act → W12 回归。
**可并行**：W6 软件组与 W7 校验组并行；W10 各项（MCP/estTokens/onboarding/GLM）互相独立可穿插；F2 记忆可提前至 W9 后任何时点。
**纪律**：每里程碑结束跑 `pytest + 契约差分 + check_contract + build×2`；不允许未测代码跨里程碑。

## 3. 核心模块与文件结构

### 3.1 新增后端（8 service + 1 目录）

| 文件 | 职责 | 关键导出 |
|---|---|---|
| `backend/services/search_browser.py` | pywebview 次窗口生命周期（独立 profile：`WEBVIEW_DATA_DIR/search_profile`） | `SearchBrowser`（load_url/wait_selector/on_page_data 回调注册/close） |
| `backend/services/search_adapters.py` | 引擎 URL 模板 + **纯函数**解析器（HTML 串 → 结果列表） | `ADAPTERS = {bing: {build_url, parse}, duckduckgo: {...}, baidu: {...}, google: {...}, generic: {...}}` |
| `backend/services/search_extract.py` | readability 风格正文提取 → markdown | `extract_main(html, max_chars) -> str` |
| `backend/services/search_service.py` | 编排：缓存→URL→窗口→解析→过滤→dual-LLM 读取→包裹→审计 | `SearchService.search(query, opts) / open(url, opts) / cache_stats() / cache_clear()` |
| `backend/services/software_service.py` | 注册表+探测+调用+异常矩阵 | `SoftwareService.list()/probe()/call(name,args)/test(name)/save(cfg)` |
| `backend/services/hybrid_router.py` | 任务分类+路由+预算+降级+统计 | `HybridRouter.classify(task)/route(cls)/understand()/validate()/stats()` |
| `backend/services/plan_service.py` | 计划生成/状态机/偏差/检查点调度 | `PlanService.propose(intent)/approve(id)/revise(id)/abort(id)/get(id)` |
| `backend/services/validation_service.py` | 校验器注册表+重试 | `Validators.register(tool, fn)/check(tool, result)->{ok, reason, retry}` |
| `backend/services/memory_service.py` | 结构化记忆 CRUD+检索+注入 | `MemoryService.list()/add()/delete()/retrieve(query)->str` |
| `backend/prompts/` | 版本化提示词（R19）：`system-base.md`/`system-sandbox.md`/`system-local.md`/`efficiency.md`/`compact.md`/`plan-generate.md`/`reflect.md`/`understand.md`/`validate.md` + `manifest.json`（id→version+sha256） | `prompt_loader.load(prompt_id) -> (text, version)` |

### 3.2 修改后端（10 文件）

| 文件 | 改动 |
|---|---|
| `backend/api.py` | 装配 8 个新 service；约 28 新 js_api（全入 `_V12_EXTRA`）；`build_system_prompt` 改读 prompts/ 文件（保留 INTENTIONAL_DELTAS 白名单内的 ws_enabled 段与 local 段）；run_command/run_powershell 已有 sandbox 接线不变；trace_id 生成与传递 |
| `backend/tools_schema.py` | `build(role, ws_on, mcp_tools=None, include_agent=False)`——第三参数；`_AGENT_TOOLS` 列表（browser_search/browser_open/software_call/plan_*/memory_*/clarify）仅 include_agent=True 时追加；默认路径逐字节不变 |
| `backend/services/guard_service.py` | deny 清单（`DENY_OPS` 5 条）+ `allow_rules`（guard.json 增键，模式匹配）+ `task_grant`（进程内 dict：scope/ops/excludes/expires）+ `enforce_exec` 判定链重构为：deny → allow_rules → task_grant → op 档位 → confirm-token；新增 `grant()/revoke()/rules_crud()` |
| `backend/services/mcp_service.py` | `derive_tier` 增楼层规则（工具名/描述含 delete_/drop_/purge_/wipe_ 或 destructive 无 idempotent → always）；`tool_schemas` 记录 schema hash（TOFU：变更→blocked-re-review 状态）；健康度（连续失败计数→ok/degraded/error 三态） |
| `backend/services/local_model_service.py` | readiness 8 项评分（tag 固定/工具能力/schema/迭代上限/路径护栏/结构化错误/日志/keep_alive 提示）；`/api/show` template 探测（Ollama）；`classify_local_error` 不变 |
| `backend/services/sandbox_service.py` | R23 结论落地：若剪贴板 Flag 实测有效→strict 档 `_UI_LEVELS['strict']` 增 READCLIPBOARD/WRITECLIPBOARD（值以实测为准）；文档注释更新 |
| `backend/services/cmd_service.py` | `run_command/run_powershell` 的 sandbox 透传不变；software cli 类复用 `sandbox_service.run_in_sandbox` |
| `backend/paths.py` | 增 `SOFTWARE_FILE`/`HYBRID_FILE`/`MEMORY_FILE`/`SEARCH_CACHE_FILE`/`CHECKPOINTS_DIR`/`PROMPTS_DIR` 常量（模式同 MCP_SERVERS_FILE） |
| `backend/services/config_service.py` | 不动（新配置全部走独立文件） |
| `backend/logging_setup.py` | 不动（harbor.log 现有通道；trace_id 进日志格式串） |

### 3.3 新增前端（6 模块）

| 文件 | 职责 |
|---|---|
| `frontend/src/39-search-panel.js` | 搜索面板（结果列表/原文预览/人工接管按钮/反爬提示）；新 DOM id：`searchPanel`/`searchResults`/`searchTakeover` |
| `frontend/src/64-software-panel.js` | 软件设置面板（探测列表/状态灯/测试调用/自定义向导）；id：`softwarePanel`/`swList` |
| `frontend/src/65-hybrid.js` | 混合路由配置（策略/预算/置信门）+ 会话头本地/云端分账显示；id：`hybridBlock`/`hybridPolicy` |
| `frontend/src/66-plan.js` | 计划卡（步骤 checklist/风险标注/批准/编辑/偏差暂停条/回滚链接）；id：`planCard` |
| `frontend/src/67-memory.js` | 记忆管理（列表/删除/检索测试）；id：`memoryBlock` |
| `frontend/src/68-onboarding.js` | 首次运行向导（欢迎→用途三问→计量表展示→完成）；id：`onboardingOverlay` |

### 3.4 修改前端（10 模块）

| 文件 | 改动 |
|---|---|
| `60-agent-loop.js` | Plan-Act 主循环（understand→plan 提议→批准→act→reflect→deliver）；clarify 分支；web_search 升级 GLM Web Search API 结构化（R21）；trace_id 传递 |
| `25-tool-exec.js` | 新工具分发（browser_*/software_*/plan_*/memory_*/clarify）+ guardToken 透传 + 校验器挂钩（V1） |
| `55-tool-route.js` | `include_agent` 工具域（搜索/软件/计划/记忆的 ROUTE_HINTS）+ EFFICIENCY_PROMPT 改读 prompts/efficiency.md |
| `26-guard.js` | 授权条（scope 选择+TTL+授予/收回）+「升级为规则」+ 规则管理入口 |
| `34-local-model.js` | readiness 面板（8 项评分+低分降级建议）+ keep_alive 引导 |
| `29-mcp.js` | 服务器健康徽标（ok/degraded/error+失败计数） |
| `40-auto-compact.js` | estTokens 比值校准（中文 1.8→3.2-3.4，代码 3.5 保持）+ provider usage 对账（>5% 告警） |
| `100-send.js` | 发送入口：understand→计划提议路由；clarify 表单渲染 |
| `00-state.js` | 新状态字段：`state.plan`/`state.traceId`/`state.searchOpen`/`state.grant` |
| `index.template.html` | 纯新增：搜索面板容器/软件面板/hybrid 区块/记忆区块/onboarding overlay/计划卡样式/授权条样式；set-nav 增导航项 |
| `70-config.js` | 新设置区块接线（软件/混合/记忆） |
| `97-compact.js` / `30-history-shrink.js` | 压缩提示词改读 prompts/compact.md；append 纪律（不重写历史） |

## 4. 关键数据结构

### 4.1 新配置文件（全部独立于 config.json）

```json
// ~/.glm-chat/software.json
{"version":1,
 "presets":{"git":{"kind":"cli","probe":["git","--version"],"verify":"git version",
   "actions":{"status":{"argv":["git","status","--short"],"risk":"read"},
              "commit":{"argv":["git","commit","-m","{message}"],"risk":"mutate",
                        "args":{"message":{"type":"string","required":true,"max":200}}}}},
   "ffmpeg":{...},"7z":{...}},
 "custom":[],
 "detected":{"git":{"path":"...","version":"2.47.1","at":"iso"}}}

// ~/.glm-chat/hybrid.json
{"policy":"auto","budgets":{"understand_ms":5000,"validate_ms":3000},
 "confidence_gate":0.7,
 "classes":{"understand":"local","validate":"local","plan":"cloud","compose":"cloud"}}

// ~/.glm-chat/memory.json
{"version":1,"entries":[{"id":"m_xxx","kind":"preference|convention|path",
  "text":"以后都别用 PowerShell","keywords":["powershell"],
  "source":"explicit|inferred","created":"iso"}]}

// ~/.glm-chat/search_cache.json
{"version":1,"entries":[{"key":"sha1(engine+query+filters)","result":{...},
  "created":"iso","ttl_s":1800}]}
```

### 4.2 guard.json 增键（纯增，旧文件缺省 = 空）

```json
{"allow_rules":[{"id":"r_xxx","op":"run_command","pattern":"git status*",
                 "created":"iso","hits":0}],
 "trusted_ops":[...]}   // 既有键不动
```

### 4.3 进程内状态（不落盘）

```python
# guard_service
self._task_grant = {"scope":"workspace_write",
  "ops":["run_command","run_powershell","write_file","search_replace","append_file"],
  "excludes":["delete_path","kill_process","clipboard_write","take_screenshot","run_admin_command"],
  "granted_at":..., "expires_at":..., "trace_id":...}

# api.py 每任务
trace_id = 't_%s_%s' % (base36(time), rand4)
```

### 4.4 会话状态增字段（sessions.json 纯增，旧会话缺省 = None）

```json
{"plan":{"id":"p_xxx","status":"draft|approved|running|blocked|done",
  "steps":[{"i":0,"title":"读取配置","tools":["read_file"],"risk":"low",
             "status":"pending|doing|done|blocked|skipped"}],
  "checkpoint":"cp_xxx","trace_id":"t_xxx","created":"iso"},
 "checkpoint":{"id":"cp_xxx","kind":"git|files","ref":"...","files":[...],"created":"iso"}}
```

### 4.5 MCP 增字段（mcp_servers.json 纯增）

```json
{"name":"fs","enabled":true,"callTimeout":60,
 "tool_hashes":{"mcp__fs__read_file":"sha256:abc..."},
 "health":{"state":"ok","fails":0,"last_fail":null}}
```

## 5. 接口设计（约 28 个新 js_api，全部 `_V12_EXTRA` 隐身）

| 方法 | 签名 | 返回 |
|---|---|---|
| `browser_search` | `(query, options_json)` options: engine/site/filetype/time_range/lang/max_results/extract | `{ok, results:[{title,url,snippet,date}], from_cache, trace_id}` |
| `browser_open` | `(url, extract_json)` extract: selector/max_chars | `{ok, title, markdown, truncated}` |
| `search_cache_stats` / `search_cache_clear` | `()` | `{entries, hits}` / `{ok}` |
| `software_list` / `software_probe` / `software_call` / `software_save` | `()` / `()` / `(name, args_json)` / `(cfg_json)` | 探测列表 / 重探测 / `{ok, exit_code\|launched, output, error?}` / `{ok}` |
| `hybrid_get_config` / `hybrid_save_config` / `hybrid_stats` | `()` / `(cfg_json)` / `()` | 配置 / `{ok}` / `{local_calls, cloud_calls, degrade_count, tokens:{local,cloud}, saved_est}` |
| `plan_propose` / `plan_approve` / `plan_revise` / `plan_abort` / `plan_get` | `(intent)` / `(plan_id)` / `(plan_id, steps_json)` / `(plan_id)` / `(plan_id)` | 计划卡 / `{ok}` / `{ok}` / `{ok}` / 计划详情 |
| `memory_list` / `memory_add` / `memory_delete` | `()` / `(kind, text)` / `(id)` | 列表 / `{ok,id}` / `{ok}` |
| `guard_task_grant` / `guard_revoke_grant` / `guard_rules_list` / `guard_rule_save` / `guard_rule_delete` | `(scope, ttl_min)` / `()` / `()` / `(rule_json)` / `(rule_id)` | `{ok, expires_at}` / `{ok}` / 规则列表 / `{ok,id}` / `{ok}` |
| `checkpoint_create` / `checkpoint_list` / `checkpoint_rollback` | `(label)` / `()` / `(cp_id)` | `{ok,id}` / 列表 / `{ok, restored:[...]}` |
| `readiness_check` | `()` | `{score, items:[{name,pass,detail}], level}` |
| `clarify_ask` | `(questions_json)`（≤5 问，每题 question/options/default） | 渲染表单（前端） |

**判定链**（guard_service.enforce_exec 重构后顺序，全部模式生效）：
`DENY_OPS → allow_rules 模式匹配 → task_grant（op∈scope 且 ∉excludes 且未过期）→ op 档位（always→confirm-token / session→会话信任 / off→放行）→ 确认弹窗`

## 6. 主要执行流程

### 6.1 Plan-Act 主循环（100-send.js → 60-agent-loop.js → plan_service）

```
用户发送
 → hybrid.classify → understand（本地 5s 预算；超时/不可用→云端；再失败→原样透传）
 → plan_service.propose(intent) → 计划卡（本地生成草稿；complex→云端）
 → 用户：批准 / 编辑后批准 / 拒绝
     └─ L2 授权中 + 计划全 low 风险 → 自动批准路径（授权条可见）
 → Act：按步骤执行，每步工具分发（25-tool-exec）过判定链
     └─ validation_service.check(tool,result) 失败 → reformulate ≤2 → blocked
 → Reflect：hybrid validate（本地 3s）→ verdict+confidence
     └─ <0.7 → 云端复核 / 补做循环
 → Deliver：摘要 + 回滚链接 + trace_id 落审计
```

### 6.2 browser_search（dual-LLM-lite）

```
agent → browser_search(query,opts)
 → search_service：cache 命中？→ 直返（≤300ms）
 → adapters[engine].build_url(query,filters) → search_browser.load_url
 → wait_selector 轮询（≤8s，抗 SPA）→ 页面 JS 抽原始结果
     → window.pywebview.api.on_page_data(json) 回调（禁 evaluate_js 返回值——CSP）
 → hybrid understand（本地读取器）：原始 HTML/JSON → schema 约束结构化结果
     （读取器系统提示：禁祈使句/禁工具名样式输出；输出仅数据）
 → 过滤：域名黑白/时效/必含词/URL 归一去重/相关性重排
 → extract=full → browser_open Top N（search_extract → markdown）
 → 注入包裹：结果包 provenance 分隔 + 「UNTRUSTED DATA」标记进主模型上下文
 → cache 写入 + audit（op=web_search，trace_id）
 → 降级：窗口超时 → urllib 抓 HTML 兜底（非 JS 引擎）/ 验证码特征 → 面板人工接管
```

### 6.3 software_call

```
agent → software_call(name,args)
 → resolve(name)：detected？否 → 人话未安装+官网引导（不自动下载）
 → schema 校验：失败 → 结构化错误+正确示例回显（Agent 自校正）
 → 判定链（含楼层规则：action risk=dangerous→always）
 → cli → sandbox_service.run_in_sandbox(argv,cwd=workspace,timeout)
    gui → ShellExecuteW + FindWindowW 标题核验（≤10s，失败→「已发起未确认」）
    uri → 协议调用
 → 结果结构化 + 错误人话映射（git/ffmpeg 常见码表）
 → audit
```

### 6.4 混合路由与 task grant

```
classify(task) ∈ {understand,validate,plan,compose}
 → policy: auto → understand/validate=local（readiness≥5 才用）/plan/compose=cloud
             saver → 本地优先，compose 按复杂度分档
             quality → 全云端
 → 本地调用带预算；超时/不可用 → 云端降级（stats.degrade_count++）
 
授权条 UI → guard_task_grant(scope,ttl) → 进程内 grant
 → 判定链见 §5；收回按钮 / TTL 到期 / 任务结束 → 自动 revoke
```

### 6.5 检查点

```
plan approved → checkpoint_create：
  git 仓库？→ `git stash create` 记录 ref（不碰工作区状态）
  否则 → 复制计划声明涉及文件至 ~/.glm-chat/checkpoints/<cp_id>/（≤200MB/≤500 文件，超限降级「仅记录清单」）
 → rollback：清单展示 → uiConfirm → 恢复（git：`git checkout <ref> -- <files>`；files：副本回写）
 → 保留策略：默认保留最近 3 份，旧的随新 checkpoint 创建清理
```

## 7. 兼容性与迁移处理

| 面 | 处理方式 |
|---|---|
| js_api 契约 | `build_tools` 默认路径（include_agent=False）逐字节不变——契约差分测试天然通过；28 新方法全入 `_V12_EXTRA`，`get_api_info()` 输出零漂移 |
| config.json | 零写入零读取变更；新配置全部独立文件（software/hybrid/memory/search_cache/checkpoints） |
| guard.json | 纯增 `allow_rules` 键；加载时缺省合并；`trusted_ops`/三档语义不动 |
| mcp_servers.json | 纯增 `tool_hashes`/`health`；旧配置加载时补默认；协议版本不变 |
| sessions.json | 纯增 `plan`/`checkpoint` 字段；旧会话 plan=None → plan_service 走「无计划直跑」兼容路径（等同 v1.7 行为） |
| UI 契约 | 全部新 DOM id/class 纯增；check_contract.py 既有 40 id/13 onclick/43 callApi/39 类/21 变量零改动 |
| VERSION | 1.7.0→1.8.0；`update_service.py` 回退常量同步；安装器 spec 名自动带版本 |
| DeepSeek preset | 36-connect.js PRESETS 更新为 v4-flash/v4-pro；旧配置里的旧型号字符串经 `connectModelValue` 既有过滤逻辑回落官方模型（三轮 S12 已建）；价格表新旧并存 |
| 提示词迁移 | `build_system_prompt` 从硬编码改读 `backend/prompts/*.md`——**输出内容保持逐字一致**（迁移即把现有字符串原样落盘 + manifest 记 v1.0），行为零变化后再迭代 |
| 本地代理 | hybrid 本地调用经 `window.__localProxyBase` 既有分流（10-20 已交付），CORS 不回归 |
| 安装器 | 四 exe 重建（app/uninstaller/setup）；安装/卸载逻辑不变 |
| 测试基线 | 721 passed 零回归是硬门；新增 8 个测试文件（约 200 项） |

## 8. 验证要点（七门 + 基准）

| 门 | 命令/方式 | 通过标准 |
|---|---|---|
| G1 全量测试 | `pytest tests/ -q` | 721 既有 + 新增约 200 全绿 |
| G2 契约差分 | `tests/test_api_contract.py`（legacy vs new 逐字节） | `build_tools` 默认路径 + `get_api_info` + config.json 零漂移 |
| G3 UI 契约 | `python deliverables/design/check_contract.py` | PASS（只增不改） |
| G4 构建幂等 | `node frontend/build.js` ×2 | md5 一致；模块数 43→49 |
| G5 安装器 e2e | `Harbor-Setup-1.8.0.exe --silent --dir <tmp>` → 验证 → `--uninstall --silent` | exit 0 + 注册表四项 + 清理干净 |
| G6 注入 fixture | 构造含「删除工作区」指令的网页 fixture + 含隐藏指令的 MCP 工具 description fixture | 网页：不触发任何工具且被 surface；MCP：楼层规则/扫描拦下 |
| G7 真机冒烟（目标机） | ① WebView2 真实搜索三步 ② Ollama hybrid 全链 ③ git software_call ④ 计划批准→执行→回滚 ⑤ 记忆跨会话 ⑥ onboarding 向导 ⑦ 授权条授予/收回 | 七项全过 |

**基准对比**（G7 附）：3 条标准任务链（纯问答/单文件改/多文件+命令）× v1.7.0 基线 vs v1.8.0——指标：总 token（-15%）、TTFT、cache hit rate、确认弹窗次数（-60%）、任务成功率。

**新增测试文件**：`test_v18_search.py`（适配器 fixture/提取/去重/缓存/dual-LLM 隔离）、`test_v18_software.py`（探测/校验/执行/异常矩阵）、`test_v18_hybrid.py`（路由矩阵/预算/降级/readiness）、`test_v18_plan.py`（状态机/偏差/澄清）、`test_v18_memory.py`（CRUD/检索/注入）、`test_v18_guard_ext.py`（deny/rules/grant/判定链）、`test_v18_mcp_hard.py`（楼层/TOFU/健康度）、`test_v18_prompts.py`（加载/manifest/迁移逐字一致）。

## 9. 风险与止损

| 风险 | 等级 | 止损规则 |
|---|---|---|
| WebView2 搜索窗口时序不稳（S14 类） | 高 | wait_selector≤8s + urllib 兜底 + 人工接管三降级；连续失败转「仅 API 通道」 |
| dual-LLM-lite 本地读取器输出不合规 | 中 | schema 校验失败重试 1 次 → 降级主模型直读（带包裹），不阻塞 |
| 单版本体量大（54.5 人日）质量稀释 | 高 | 四里程碑各设门禁；M3/M4 允许「功能完但 UI 简」交付，P2 项（搜索 API 加速器/健康徽标细化）明确可砍 |
| R23 实测推翻 §17（Flag 无效） | 低 | 结论记录即可，strict 档维持现状，文档修订 |
| 既有 721 测试回归 | 中 | 每里程碑全量跑；契约差分红线不可碰，碰即回滚当批 |

## ⚠️ 假设
- 工作量按 v1.7.0 velocity（721 测试网）估算；54.5 人日含单测不含审查（审查 +5-8 人日另计，沿用 1.3.x 模式）
- W0 的 R23 实测与 R20 校准若结论变化（Flag 有效/DeepSeek 再换代），只影响 strict 档与 preset 两处，不动架构
- 「2 人并行 6-7 周」假设第二人可独立承担 M4 信任棒（MCP/estTokens/onboarding 互相独立）
- prompts 迁移「输出逐字一致」指当前硬编码字符串原样落盘；后续迭代才改内容

## 免责声明
⚠️ 本方案为工程实现规划，基于代码库实测（2026-10-20）与既有方案文档合成；外部技术依据经调研报告引入（URL 见其证据清单）；重要架构决策请由技术负责人审定后开工。
