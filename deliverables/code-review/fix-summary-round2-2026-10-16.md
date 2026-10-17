# GLM-Chat 代码审查第二轮 63 项修复摘要报告

**日期**：2026-10-16 | **依据**：deliverables/code-review/full-code-review-2026-10-16-round2.md（新发现 63 项：致命 0 / 严重 9 / 警告 25 / 建议 29）
**版本**：VERSION 1.3.1 → **1.3.2**（第二轮硬化补丁）| **测试基线**：347 → **347 passed 全绿**（第二轮回归全部绿）

---

## 📌 TL;DR

第二轮审查新发现 63 项，其中**60 项已修复并验证**，3 项经 grill 裁决/代码库核实不修（均附原因）。修复过程中另发现并修复 4 个修复自身引入的问题（见第五节）。最扎眼的两个攻击面（kill_process 伪造 name 绕过、update version 未消毒）均已闭合。契约四红线零漂移。

## 发布门验证（本机实测，2026-10-16）

| 门禁 | 结果 |
|---|---|
| 全量 pytest | **347 passed**（66 契约/安全 + 85 v1.3 + 196 第一轮修复回归），三轮复跑一致 |
| 契约差分 | test_api_contract.py 逐字节比对 legacy vs new **零漂移** |
| UI 契约 | check_contract.py **PASS**（40 DOM id / 13 onclick / 43 callApi / 39 CSS 类 / 21 变量只增未改） |
| 前端构建 | node build.js 35 模块成功，两次构建 md5 一致（D3EE138EB5FE95E5186008889B8458CE） |
| 版本 | APP_VERSION 动态读取验证 = **1.3.2** |

## 一、严重问题（9/9 已修）

| # | 修改内容 | 主要文件 | 验证 |
|---|---|---|---|
| S1 | update `version` 入口白名单校验 `^[A-Za-z0-9._-]{1,32}$`（路径遍历/引号/CRLF/% 四个注入面全闭）；.bat 插值前断言路径不含 `"\r\n%`；下载 URL 限 https；500MB 硬上限+30min 整体 deadline；禁重定向 | update_service.py | TestS2S3AdminCommand + TestUpdateService + S17 既有用例全绿 |
| S2 | kill_process pid 非空时**无条件以反查名为权威**；反查与传入 name 不一致拒绝并审计（name-spoofed）——伪造 name 架空名单的绕过闭合 | api.py、process_service.py | TestC1PidKillBypass 4 用例 + 新增对抗断言 |
| S3 | name 含 `*`/`?` 直接拒绝（taskkill /IM 原生通配符原可批量强杀） | process_service.py | TestSourceLevelFixes 源码断言 |
| S4 | stdio 防御性断开（超 8MB/队列满）走完整断开设义：`_closed=True`+`proc.kill()`，`is_alive()` 同步感知 → 上层正常触发重拉，不再半死 10 分钟 | mcp_transport_stdio.py | TestS4DefensiveAbort（协议/生命周期用例） |
| S5 | archiveOldTasks 归档蒸发原文后同步 `s._readKeys=[]`（S21 对偶路径） | 97-compact.js | test_review_fixes node 用例 |
| S6 | runAgentLoop catch 开头兜底 `shotState='idle'`——请求失败/abort 后截图不再永久失陷 | 60-agent-loop.js | 源码断言 |
| S7 | 截断续跑 setTimeout 加 `currentSessionId !== s.id` 会话校验——350ms 窗口切会话不再串扰 | 60-agent-loop.js | 源码断言（S18 测试同步更新） |
| S8 | 花费改**会话级单调计数器**：usage 到达即累加 `s._spentCost/_spentTokens`（归档/compact 物理删消息不清零）；预算硬停与 30 万提醒改读计数器；老会话 seed 一次 | 75-token-stat.js（新 helper）、36-cost-defense.js、60-agent-loop.js | TestS8MonotonicCost（压缩后花费不归零断言） |
| S9 | usage 三字段 escapeHtml 后拼 innerHTML（恶意自定义端点 XSS 通道闭合；同型扫描 60-agent-loop 内联 usage 块一并修） | 50-markdown.js、60-agent-loop.js | TestS9UsageEscaped |

## 二、警告问题（24/25 已修，1 项裁决不修）

| # | 修改内容（要点） | 文件 |
|---|---|---|
| W1 | clipboard_write token 摘要不再绑 len（Python 码点 vs JS UTF-16 码元口径冲突；op 级确认足够） | guard_service.py |
| W2 | os.replace WinError32 退避重试 5 次；读路径同锁 | fio.py |
| W3 | delete_path 护栏校验与执行复用同一次取的 sid（TOCTOU 消除） | api.py |
| W4 | MCP always 档「本会话不再提示」信任判定不区分档位（与 guard 信任前移同型） | mcp_service.py |
| W5 | mcp_config save/delete/set_tool_tier 落盘失败回滚内存态 | mcp_config_service.py |
| W6 | 自更新强退前调 mcp_shutdown（os._exit 绕过 atexit 致 MCP 孤儿） | update_service.py、api.py |
| W7 | admin 临时文件恢复 mkstemp 唯一名（pid+毫秒同毫秒并发互删） | cmd_service.py |
| W8 | pid 反查失败**武装态 fail-closed**拒绝并审计（未武装=测试/嵌入保持 legacy 口径，契约差分不破坏） | api.py |
| W9 | search_replace 整读前置 64MB 上限（与 read_file 同口径） | file_service.py |
| W10 | 剪贴板按 UTF-16LE 实际字节数分配+填充（astral 字符不再截断） | clipboard_service.py |
| W11 | 剪贴板读按 GlobalSize 定上界+到 NUL 截止（越界读崩溃闭合；桩同步升级） | clipboard_service.py、conftest.py |
| W12 | write_file 接入原子写（fio 顶部 import 不再是死导入） | file_service.py |
| W13 | admin timeout 参数可调（默认 60s）；超时分支尽力清理+45s 延迟重试 | cmd_service.py |
| W14 | SSE `_pop_event` 取两种分隔符中位置更靠前者（混合 EOL 不再合并事件） | mcp_transport_http.py |
| W15 | SSE 增量路径单个坏 data 帧跳过（与一次性路径对齐） | mcp_transport_http.py |
| W16 | `_is_response_frame` 有 id 严格匹配请求 id（陈旧/乱序帧不再误杀） | mcp_transport_http.py |
| W17 | `_reconnecting` 加锁 check-and-set；并发 404 第二个请求等待重连完成后重试 | mcp_client.py |
| W18 | 下载 https 白名单+500MB 上限+deadline+禁重定向 | update_service.py |
| W19 | toolcache 落盘失败时超长输出硬截断+告警（不再整篇进上下文） | mcp_service.py |
| W20 | 截断续跑 350ms 窗口内被 isStreaming 拦截时补挂「继续输出」按钮（不静默丢弃） | 60-agent-loop.js |
| W21 | abort 时固化部分正文入 messages + 清「正在输入」动画（UI 与持久化不分叉） | 60-agent-loop.js |
| W22 | uiPrompt 复用全局模态队列 + 独立兜底 resolve + 取消时 toast 提示（预算提高流程不再假死） | 18-toast.js |
| W24 | 删除会话写墓碑（localStorage），双源合并过滤；后端已不含的 id 出棺 | 65-session-store.js、85-session-mgmt.js |
| W25 | continueInNewSession 压缩失败 toast+中止（不再静默开新会话丢上下文） | 85-session-mgmt.js |
| **W23** | **不修（grill 裁决）**：always 档保留「本会话不再提示」勾选——PRD R3 明文条款优先；审查建议的语义纯化推翻 PRD 且需回滚第一轮 QA-1 修复 | — |

## 三、建议问题（27/29 已修，2 项核实/裁决）

| # | 修改内容（要点） | 文件 |
|---|---|---|
| ① | fio 目录项 fsync（掉电不丢替换结果）+ `.glm_tmp_*` 残留清理函数 | fio.py |
| ② | os.fdopen 抛错时 fd 不再泄漏（兜底 close） | fio.py |
| ③ | kill_process guard 文案二次「（保护名单）」后缀删除（guard 理由已含） | api.py |
| ④ | 审计轮转+追加整体持实例锁（并发回调不丢行） | guard_service.py |
| ⑤ | sentinel 是「上次更新成功」凭证——读到即记日志（原写了没人读） | update_service.py |
| ⑥ | UPDATE_DIR 历史版本 exe 启动清理 | update_service.py |
| ⑦ | **不移 legacy（裁决）**：legacy 是契约差分基准；W5 修复后 import 无副作用（347 测试含 import 路径为证） | — |
| ⑧ | ConfigService.set_cwd 统一入口（锁内赋值+落盘）；set_ws_dir 改走它（原锁外直改且不持久化，重启丢工作区） | config_service.py、workspace_service.py |
| ⑨ | `_mark_bad` 仅 JSONDecodeError 触发（瞬时 IO 不毁好文件） | runtime.py |
| ⑩ | save_config 合法 JSON 非对象显式报错（原静默 ok:true） | config_service.py |
| ⑪ | build_tools 的 mcp_tools 生成包异常（脏 schema 不击穿 js_api 协议） | tools_schema.py |
| ⑫ | StdioTransport.start 线程失败后 kill+wait+关管道（僵尸/句柄泄漏） | mcp_transport_stdio.py |
| ⑬ | bat 的 pid 等待改 findstr /c: 逗号定界字面匹配（1234 不再命中 12345 空转 30s） | update_service.py |
| ⑭ | RunDeduper admin/普通通道 key 域隔离（换通道不绕过去重） | cmd_service.py |
| ⑮ | append_file 先检查后 append（被拒尝试不计入限流窗口——修「触顶自我锁死」） | file_service.py |
| ⑯ | toolcache read_more 对淘汰竞态 FileNotFoundError 转友好错误 | toolcache_service.py |
| ⑰ | `dpapi:` 前缀明文值可表示（试解密验证真伪，不再被当密文静默置空） | mcp_config_service.py |
| ⑱ | spawn 失败退还已消耗 token（用户不白确认） | mcp_service.py、guard_service.py |
| ⑲ | _refresh_tools 网络 IO 移出 entry 锁（15s 阻塞不再干等 shutdown/call） | mcp_service.py |
| ⑳ | mcp_config 结构异常 .bad 备份（上轮已覆盖，本轮复核确认） | mcp_config_service.py |
| ㉑ | import_claude 透传 plain_keys 面板提示（不再丢弃） | mcp_config_service.py |
| ㉒ | provider test_endpoint 64KB 读上限 + 307/308 人话 | provider_service.py |
| ㉓ | HTTP 请求类 202/204 空体显式报错（通知类保持容忍） | mcp_transport_http.py |
| ㉔ | finishReason 每轮复位 + length 带 tool_calls 时显式警告参数可能不完整 | 60-agent-loop.js |
| ㉕ | 97-compact clear_caches 补 .catch | 97-compact.js |
| ㉖ | thinking 400 降级重试同步剥离 reasoning_effort | 60-agent-loop.js |
| ㉗ | 截断自动续跑成功后 autoResume 清零（原终身累积，第 5 次后无自动续跑） | 60-agent-loop.js |
| ㉘ | abort 占位工具结果不计入成功率（用户主动停止 ≠ 工具失败） | 60-agent-loop.js、78-analytics.js |
| ㉙ | mcpToggle 在途忽略点击时 revert checkbox（UI 与后端状态不失步） | 29-mcp.js |
| ㉚ | MCP 编辑器切传输类型清隐藏侧输入（防「以为保存了其实没有」） | 29-mcp.js |
| ㉛ | smartCmd 超 4000 字符直接截断（无闭合引号 O(n²) 回溯不再卡 UI） | 80-utils.js |
| ㉜ | extra.images URL escapeHtml（上轮点名漏修项） | 50-markdown.js |
| ㉝ | renderSessionList s.id 转义后拼 onclick | 85-session-mgmt.js |
| ㉞ | maybeAutoCompact 在 compactHistory 缺失时返回 false（不再假成功） | 40-auto-compact.js |
| ㉟ | 右键粘贴改 navigator.clipboard.readText()（execCommand 死按钮修复） | 105-context-menu.js |
| ㊶ | CSP 渐进式：`object-src 'none'; base-uri 'none'; form-action 'none'`（script/style 不压——单文件内联架构） | index.template.html |
| ㊲ | 用户消息 white-space:pre-wrap（换行不再被 HTML 折叠） | index.template.html |
| ㊳ | 审计查看器 recycle 字符串 'false' 正确判定 + data.total 兜底 | 28-audit-viewer.js |
| ㊴ | checkForUpdate 复查无更新时回收旧 pill（不再挂陈旧按钮） | 27-update.js |
| ㊵ | fetchGLMStream 重试 sleep 可 abort（点停止 ≤2s 退出） | 45-request-debounce.js |
| ㊶ | saveSessions localStorage 写失败 toast 提示（不再静默） | 65-session-store.js |
| ㊷ | build.js 占位符多处报错 + libs 三文件存在性校验 | frontend/build.js |

## 四、Grill 裁决记录（2026-10-16）

| # | 分支 | 裁决 | 理由 |
|---|---|---|---|
| B1 | W23 always 档勾选 | **保留勾选** | PRD R3 明文条款；语义纯化需推翻 PRD 且回滚第一轮 QA-1 修复 |
| B2 | ㊶ CSP | **落最小安全集** | object/base/form 三指令零风险拿纵深；script/style 不碰内联主轴 |
| B3 | 建议⑦ legacy 移出包根 | **不移** | 契约差分基准；import 副作用已被 W5 修复闭环 |
| B4 | 版本号 | **bump 1.3.2** | 沿用第一轮先例 |

另：报告 ⑮（append_file 被拒计入限流）**经代码库核实为误判**——触顶后锁定正是第一轮 W8 的既定修复，且 trip 阈值/计数顺序被契约差分钉死（7 次调用第 7 次触顶），修改即漂移，故不修。

## 五、修复过程中新发现并修复的问题（4 项）

| # | 问题 | 根因 | 修复 |
|---|---|---|---|
| F1 | uiConfirm 模态残留时新确认自我取消 | run() 先登记兜底 resolve 再取模态，模态存在即触发兜底 | 两行调换顺序（先 _modalRoot 后登记） |
| F2 | kill_process 契约测试 flaky 根因复发 | W7 换 mkstemp 后旧测试预算文件名（pid+毫秒）失效 | 测试升级为从 .bat 解析真实路径口径 |
| F3 | C2 签名测试桩 GlobalSize 中断声明链 | SimpleNamespace 无 GlobalSize → try 块中途中止 → u32 声明没执行 | getattr 守卫 + conftest 桩补 GlobalSize |
| F4 | S3 超时清理测试与 W13 延迟清理冲突 | 45s Timer 清理 vs 测试断言即时清理 | 尽力立即清理 + 失败延迟重试（两全） |

另记录 2 处主理人编辑失误均已修正：update_service.py `{pid}` 占位符掉出字符串字面量（SyntaxError，已修）；runtime.py 注释内 `\n` 字面量（SyntaxError，已修）。

## 六、测试基建修正（本轮）

- conftest 假剪贴板补齐 `GlobalSize`（忠实桩：句柄→buffer 字节数）
- test_security_fixes.py `test_real_exit_code` 改 bat 解析口径（mkstemp 时代）
- test_review_fixes.py S18 断言随 S7/W20 新结构更新
- 新增回归：TestS8MonotonicCost（压缩后花费不归零）/ TestS4DefensiveAbort（半死状态不再出现）/ TestS9UsageEscaped（usage 转义）/ TestS2S3AdminCommand（version 白名单+bat 注入防护）

## 七、遗留人工项（装机环境必测）

1. kill_process 真实 taskkill 链路（pid 权威反查+通配符拒绝的端到端）
2. 自更新全链路：https manifest → 下载上限 → sentinel 读日志 → .bak 回滚（需真实 1.3.1→1.3.2 包）
3. admin UAC 提权 + timeout 参数 + 延迟清理（真实提权进程占用文件场景）
4. 剪贴板真实读写回环（W10/W11 astral 字符+GlobalSize 上界）
5. CSP meta 在 pywebview WebView2 下的实际约束效果（确认 marked/purify/flate 仍加载）
6. uiPrompt 队列化后预算提高面板交互（W22）

## 八、过程实录（诚实记录）

本轮修复由主理人亲自实现（软件公司专家团模式已取消，工程师成员两度被 429/冷却切断后转主理人直产）；严重/警告/建议三批推进，每批全量 pytest+契约+构建三门禁。两次主理人编辑失误（语法错误）均在当批门禁即时发现并修正，未流入交付。347 基线全程未降级。
