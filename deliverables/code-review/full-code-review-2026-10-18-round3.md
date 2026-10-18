# Harbor v1.5.0 全项目深度代码审查报告（第三轮，2026-10-18）

**审查日期**：2026-10-18
**审查范围**：`main.py`、`main_v1.0.0_legacy.py`、`backend/`（29 个 .py，含 v1.5 新增 mcp_pool/local_model_service/webdav_service/fio）、`frontend/src/`（42 个 .js）、`frontend/build.js`、`index.template.html`、`Harbor.spec`
**审查方式**：5 路并行逐行复审 + 对每处历史修复构造反例证伪 + 2 项浏览器实测（Edge headless，与 WebView2 同引擎）+ 2 项回环实证（MCP 连接池）+ 4 项域名绕过实证
**测试基线**：`pytest tests/ -q` → **551 passed + 10 xfailed**（546 既有 + 本轮新增 5 个通过项锁定正确行为、10 个 xfail 复现已知缺陷；只读审查未改源码）
**配套测试**：`tests/test_v15_known_bugs.py`（两个用户实测 bug 的复现与契约测试）
**问题总数**：**约 90 项**（致命 0 / 严重 15 / 警告 30 / 建议 45）

---

## 〇、两个用户实测 bug 的根因定论

### Bug A：cmd 重复执行 / 反复打开 cmd 窗口

**根因（三层叠加，均已代码级确认）**：

1. **【直接根因】去重器是"单槽 last + 写命令全窗"语义，非紧邻重复全部放行**（`frontend/src/60-agent-loop.js:110-123` + `backend/services/cmd_service.py:67-84`）。
   前端 `cmdDeduper.check()` 只把当前命令与 `last`（单槽）比对；`recent` 全窗只对 WRITE 子串命中的命令生效。因此：
   - 同一批 `Promise.all` 内 `echo 1` → `echo 2` → `echo 1`：第三条与 last（echo 2）不同 → **放行执行第二次**；
   - 跨轮次 `tasklist` → `ipconfig` → `tasklist`：同样放行；
   - 后端 `RunDeduper` 同为 `norm == self._last` 单槽（非写命令），**双层一起失效**。
   - 复现测试：`tests/test_v15_known_bugs.py::TestFrontendCmdDeduper`（node vm 抽取真实源码执行）+ `TestRunDeduperKeyNormalization::test_nonadjacent_duplicate_bypasses_dedup`（均 xfail 复现成功）。
2. **【放大器】两层去重键都是精确字符串，语义等值变体双双绕过**。模型被"与上一条完全相同"拒绝后的标准行为就是改写重试：`del x.txt` → `del ./x.txt` / `del "x.txt"` / `DEL X.TXT` 大小写虽拦、引号与 `./` 前缀均放行（后端 `subprocess_norm` 只剥 chcp/rem 前缀）。`cmd_service.py:72` 的 `first = norm.split(...).strip('"\'').lstrip('./\\')` 计算后**从未使用**——"路径归一"本是设计意图但未接线（死代码即证据）。
3. **【弹窗面】当前代码所有命令执行路径均带 `CREATE_NO_WINDOW`**（`_exec` 两条路径、taskkill/tasklist、MCP stdio 均已核实，测试锁定）。可见 cmd 窗口只可能来自：① `open_app`（`api.py:337-355`）**不在护栏矩阵、无去重**，模型连调 `open_app('x.bat')` 即连开窗口——最符合"反复打开 cmd 窗口"的描述；② 自更新 bat 的 `start '' /min`（设计使然，升级瞬间）；③ `run_admin_command` 的 UAC 确认框（隐藏窗口+原生框，非 cmd 窗）。另 **admin 通道存在二次提权路径**：前端 `callApi` 150s 超时纯 JS 放弃，后端 MessageBox 无限期阻塞，用户超时未点 → 前端报超时 → 模型重试（变体串绕过 dedup）→ 第二个调用排队 → 用户点完第一个框后**第二个原生确认框再次弹出**，两条命令都执行。

**修复顺序**：A-1（deduper 全窗化，前端一行+后端对齐）→ A-2（键归一：引号/`./`/chcp/rem 统一，把死代码 `first` 接线）→ A-3（open_app 纳入护栏+去重）→ A-4（admin 超时与后端轮询口径对齐 + 超时返回不可重试语义）。

### Bug B：文本过长超出文本框

**根因定论（一半证实、一半证伪，均附实证）**：

- **输入框本身不溢出（证伪）**：Edge headless 实测（与 WebView2 同引擎 Blink）——同构 textarea（max-height:160 + resize:none）在 200 行内容下 `scrollH=3016 > clientH=116` 出现 UA 滚动条；500 字符无空格串 `scrollW == clientW` 自动折行。Chromium 的 textarea 滚动/折行由 UA shadow DOM 提供，**不依赖宿主 CSS overflow 声明**。因此"文本超出输入框"在当前引擎上不可复现；未显式声明 `overflow-y:auto` 属**脆弱性隐患**（换引擎/被全局 CSS 改写时才爆），建议补声明消除隐式依赖。
- **真正的溢出缺口（证实，浏览器实测/代码确认）**：
  1. **`#toastBox`/`.toast`/`.toast-detail` 无 max-height**（`index.template.html:806-819`）：长明细 toast（更新错误全文、WebDAV 冲突列表、MCP 错误）从右下角向上生长，超出视口部分被裁且无滚动，`stay/pinned` 期间持续不可达。多 toast 堆叠更严重。
  2. **`.tool-call-item` 标签缺 `min-width:0`**（`index.template.html:599-602`）：flex 子项默认 min-width:auto，长命令/长路径标签拒绝收缩，被卡片 `overflow:hidden` **无声裁切**——实测 398px 卡片 / 576px 标签 / clipped=true。工具调用卡片的信息丢失（最小窗口宽 860px 下 60 字符等宽标签即触发）。
  3. `.sys-tip` 无 max-width（长路径 tip 冲出视口左缘被裁）；`.hint` 行换行撑高输入区；`.md-body table` 无 overflow 包裹（宽表格撑出聊天区横向滚动）。

**修复顺序**：toast 栈 max-height+overflow → 工具卡片标签 min-width:0 → 输入框防御性声明（overflow-y:auto; overflow-wrap:anywhere）→ sys-tip/hint/table。

---

## 二、严重问题清单（15 项，发版前建议修复）

| # | 位置 | 问题 | 触发条件/后果 |
|---|---|---|---|
| S1 | 60-agent-loop.js:110-123 + cmd_service.py:67-84 | **去重单槽语义**：非紧邻同一条命令（批内/跨轮）双层放行 → 重复执行（Bug A 直接根因，xfail 测试复现） | 模型复述命令/批内穿插 |
| S2 | cmd_service.py:72 + 60-agent-loop.js:115 | **去重键精确字符串**：`del x.txt`/`del ./x.txt`/`del "x.txt"` 变体双层绕过；`first` 归一是死代码 | 模型被拒后改写重试 |
| S3 | 60-agent-loop.js:503-504,620-623 | **暂停留下悬挂 tool_calls**：userStopped break 后只补已执行结果，assistant.tool_calls 与 tool 消息不配平 → 毒化会话，后续每轮 HTTP 400 | 多批任务（含写工具）中点暂停 |
| S4 | 60-agent-loop.js:296-303 | **无 index 端点 tool_calls 全并 idx=0**：name 被覆盖、argsStr 拼接，第二个命令静默丢失（本地/Ollama 场景） | v1.5 主推的本地模型端点 |
| S5 | cmd_service.py:269-304 + 25-tool-exec.js:55 | **admin 150s 前端超时 vs 后端无限期人审**：超时后模型重试排队，第二个原生确认框二次弹出、二次提权执行 | 管理员命令 + 用户确认 >150s |
| S6 | mcp_transport_http.py:183-197,240-289 | **连接池 SSE 响应未排干即归还**：下次复用请求必抛 `CannotSendRequest('Request-sent')`（两次回环实证，含"响应帧后立即结束流"形态；现有测试因 HTTP/1.0 桩不复用而漏检） | 所有 SSE 型 MCP HTTP 服务器 |
| S7 | local_model_service.py:530-532 + webdav_service.py:71-73 | **localhost 豁免用整串子串匹配**：`http://localhost.evil.com/v1` 被当本地放行（4/4 实证），API Key/WebDAV 凭据明文出网 | 配置含 localhost 子串的远端端点 |
| S8 | mcp_pool.py:325-344 + mcp_service.py:453-461 | **WarmRegistry reap 双弹**：reap() 摘除后调用方再 pop() 恒为 None，`stale.close()` 永不执行（"双保险防泄漏"实际反向） | 温启条目 600s TTL 到期 |
| S9 | 36-connect.js:596/618/633 + 486-543 | **切预设不失效在途识别请求**：旧端点模型清单污染新预设下拉（connectCancelIdentify 是死函数） | 识别在途时切换预设 |
| S10 | 32-session-search.js:107-118 + 85-session-mgmt.js:59-63 | **会话搜索跳转系统性失效**：rAF(≈16ms) 早于 140ms 切换过渡，且 assistant/tool 消息从不 stamp midx → 只滚到底/高亮错消息 | 所有跨会话搜索跳转 |
| S11 | 62-mcp-exec.js:56-57 vs 103 | **local 模式"不再提示"信任跨端点泄漏**：勾选写入无条件（读侧却排除 local），切云端预设后免确认持续生效，后端 session_trust 同样放行 | 本地模型勾选信任后切云端 |
| S12 | 70-config.js:6-7/35-40 + 36-connect.js:275 | **`__manual__` 哨兵泄漏**：选"手动输入"不填即发送 → 落盘 config.json、下拉脏选项、API 404；空模型静默回落 glm-5.3-flash 打 localhost | 手动输入态空值发送 |
| S13 | 37-webdav.js:95-123 | **WebDAV 恢复无二次确认**：数据覆盖级操作（config+sessions+审计）零确认，与项目其他破坏性操作的确认惯例不符 | 误点"从备份恢复" |
| S14 | 85-session-mgmt.js:59-62 + 93-97/107-109 | **renderChatHistory 抛错 → 聊天区永久空白**：`.swapping`(opacity:0) 移除与渲染同回调无 finally，坏消息即锁死面板，只能重启 | 持久化数据含畸形消息 |
| S15 | 60-agent-loop.js:253-267 + 697 | **B3 本地等待定时器 AbortError 路径泄漏**（v1.5 新引入）：catch 只清 else 分支，1s 定时器永久存活并永久劫持状态行 | local 模式首字节 >5s 后点停止 |

---

## 三、警告问题清单（30 项，摘要）

**命令/去重族**：
- W1 前端 `check()` 执行前登记：失败/被护栏拒绝后合法重试被误拦（60-agent-loop.js:118）
- W2 后端 deduper 进程级不重置（仅 clear_caches 清），跨任务"上一条"假拒绝；前端 per-task 预记账，两层生命周期不一致（cmd_service.py:137 / api.py:96-99）
- W3 前端 WRITE 子串误报：`type third.txt`（含 rd）、`chcp 65001`（含 cp）、`findstr guard`（含 rd）被判写命令误拦（60-agent-loop.js:111）
- W4 前端 WRITE 表缺后端 11 个动词（md/ri/ni/erase/cp/regedit…），口径分叉
- W5 admin 键域 `'[admin] '` 前缀：换通道重放前端误拦/后端放行方向不一（cmd_service.py:265）
- W6 `clear_caches`（压缩/切会话时调）洗掉后端 cmd_deduper，跨轮写命令去重被压缩清白（97-compact.js:169）
- W7 admin bat 对畸形命令降级：未闭合引号致重定向失效走 60s 超时；mbcs 不可表字符静默 `?`（cmd_service.py:280-283）
- W8 run_admin_command 前端无 timeout 入口（W13 的"可调"是死参数）（25-tool-exec.js:55）

**窗口/进程族**：
- W9 `open_app` 无护栏无去重，模型可反复触发弹窗/打开 bat（api.py:337-355）
- W10 process_service `_decode_console` 的 `s.count('')` 应为 `s.count('\ufffd')`——"替换符最少"启发式名存实亡（实测 count('')==len+1），早退分支死代码（process_service.py:50）
- W11 save_workspace_file 无异常保护且未消毒 `..`，OSError 穿透 js_api 桥（workspace_service.py:249-257）

**MCP 族**：
- W12 `_normalize` 对落盘加密结构（dict 形态）执行 `str(v)`，密钥被静默损坏为 repr（mcp_config_service.py:167-168）
- W13 SSE 增量读 buf 无容量上限（时间 watchdog 不防容量，本地高速发送方可 OOM）（mcp_transport_http.py:245）
- W14 HTTPError 错误体 `e.read()` 全量读后才截断（mcp_transport_http.py:134 / provider_service.py:97 / local_model_service.py:488）
- W15 webdav 非法端口 URL 抛未捕获 ValueError（export 无兜底）（webdav_service.py:216,332-335）
- W16 import_claude 落盘失败不回滚内存态（mcp_config_service.py:332-362）
- W17 webdav DPAPI 不可用明文落盘密码无告警（webdav_service.py:527-528）
- W18 webdav 备份 >256MB 静默截断：manifest 记全量 sha、上传截断内容、恢复侧对拍必过 → 备份静默损坏（webdav_service.py:346,434-439）
- W19 webdav remote_path 未校验 `..`，服务端侧路径穿越（webdav_service.py:85-88,219）
- W20 stdio `_defensive_abort` 后 `close()` 短路：不 wait 不收管道（mcp_transport_stdio.py:128-137,190-193）
- W21 mcp_pool 的 ConcurrencyLimiter/stale/backoff 配置键入库但无生产调用方（max_concurrency 等零效果，docstring 过时）（mcp_pool.py:80,116,127）
- W22 池 close 后 in-flight release 复活 idle 条目（mcp_pool.py:277-286）
- W23 池探活仅查 `sock is None`，服务端已关的连接识别不出（与 S6 叠加放大伪失败）（mcp_pool.py:202-211）
- W24 `_get_or_spawn` 崩溃重拉后不更新 warm 登记（mcp_service.py:481-495）
- W25 `forget()` 与 `_get_or_spawn` 竞态泄漏孤儿 client（疑似，需压力验证）（mcp_service.py:392-399）
- W26 webdav keep_both 秒级同名覆盖；local_wins 冲突不实际上传（plan 语义误导）（webdav_service.py:454-475）

**前端渲染/存储族**：
- W27 墓碑清理把"后端读取失败"误判"后端已无此会话"，已删对话可复活（65-session-store.js:44-58）
- W28 continueInNewSession 在生成中静默跳过压缩仍开空会话（85-session-mgmt.js:9-19 + 97-compact.js:116）
- W29 escapeHtml 不转义引号，`_escId` 只补单引号，onclick 属性上下文存在注入面（当前 id 规则不可触发，纵深防御缺口）（50-markdown.js:7-11 / 85-session-mgmt.js:206）
- W30 compactHistory 逐消息原地压缩无逐消息防护，单条坏消息中断整个 Agent 轮次（97-compact.js:196-205）
- W31 `.session-acts` 重复 CSS 定义：后块 `display:none` 覆盖修复版，hover 淡入回归为瞬现（index.template.html:362-371，出货产物同病）
- W32 护栏设置 UI 缺 run_command/run_powershell/run_admin_command 三档下拉——命令护栏对终端用户不可达，只能手改 guard.json（index.template.html:1438-1454 vs 26-guard.js:186-195）

**v1.5 新模块族**：
- W33 多本地服务器同时探测：localLoadModels 并发错配清单/缓存/base（34-local-model.js:151-169）
- W34 GLM 判据双轨制：填官方域名的自定义预设走 GLM 发送层但 UI 按非 GLM 显隐，用户填的三价实际不生效（71-provider.js:53 vs 36-connect.js:461）
- W35 webdav 导出/恢复使用后端已存配置，UI 未保存的改动静默失效（37-webdav.js:73,100）
- W36 更新下载可重入：并发双轮询+双 pinned 进度 toast（27-update.js:65-100）
- W37 旧配置迁移分支把 provider_name 有效但 base 为空的配置强并为 GLM 并落盘（36-connect.js:746-753）

---

## 四、建议问题清单（45 项，一行一条）

**命令/去重**：① `cmd_service.py:72` first 死代码随 S2 接线或删除；② 去重键与 pickCmd 取值口径不一致（falsy 穿透，60-agent-loop.js:529 vs 25-tool-exec.js:37）；③ guard_check 每命令一次 RPC，off 档可本地短路（26-guard.js:89）；④ get_clipboard 截断后 len 口径不一致（clipboard_service.py:78-79）；⑤ append_memory 非对象入参裸异常串（config_service.py:136-146）；⑥ logging_setup 冗余死分支（logging_setup.py:23-26）；⑦ set_workspace 不更新 recent（api.py:114-122 vs workspace_service.py:165-175）；⑧ pickTimeout 只认 number，字符串超时被吞（25-tool-exec.js:39）。
**MCP**：⑨ `_unwrap` 对缺 id 响应放行（mcp_client.py:270）；⑩ timeout or DEFAULT 吞 0 值（mcp_client.py:163,166）；⑪ test_server 持锁 45s 阻塞 shutdown/call（mcp_service.py:120-152）；⑫ _load 结构异常不留 .bad 备份（mcp_config_service.py:82-94）；⑬ local_model urllib.parse 隐式导入（:237）；⑭ call_tool 每调两次 get_server deepcopy+解密热路径（:284-357）；⑮ stdio EOF 但进程不退时 recv 恒 None 空转（mcp_transport_stdio.py:114-126）；⑯ _close_client 不传 name 短窗持死 client（mcp_service.py:121）；⑰ mcp_call_timeout 依赖面板缓存，未开过设置面板时 per-server callTimeout 失效（62-mcp-exec.js:23-33）；⑱ mcpDeleteServer 无 busy 保护双击双确认（29-mcp.js:139-152）；⑲ mcp_servers.json 结构异常无 .bad（同型，mcp_config_service.py）；⑳ webdav restore plan 不含 only_local 上行需口径说明。
**前端交互**：㉑ switchSession 流式静默 return 无反馈（85:43）；㉒ deleteSession 删当前会话会杀死当前生成（85:195-202）；㉓ viewImage 叠加层无上限无 Esc（50-markdown.js:53-60）；㉔ clipboard.writeText 无 .catch（50-markdown.js:45-48,126 / 60:383）；㉕ 截图 abort 后 pendingShots 不清致重发+重复 note（60:676 vs 316-318）；㉖ addSysTip 2200ms 硬编码违反 MOTION 令牌纪律（80-utils.js:69）；㉗ toggleTheme/MOTION 兜底路径无 typeof 守卫（15-theme.js:18）；㉘ B2 400 `/tool|function/i` 误判掩盖真实错误（60:229-232）；㉙ updateLiveTokenStat 10s 定时器与流式态抢写同一状态行（75-token-stat.js:113）；㉚ 存储热路径全量重算：每轮 saveSessions 全量序列化+每按键全量成本估算（65:73-86 / 76:44-59）；㉛ lastToolSig 死变量（60:124,631）；㉚ saveSessions 无并发串行化，旧快照可后落盘（65:68-87）；㉝ switchPanel newEl 无 null 守卫（16-panel-fx.js:32-34）；㉞ build.js libs 校验漏 highlight.min.js + replace 的 `$` 序列坑（build.js:52-57）；㉟ 右键菜单定位硬编码 150/180 钳制（105-context-menu.js:72-73）；㊱ smartCmd 残余 O(n²) 回溯（80-utils.js:40-43）；㊲ dHashOfDataUrl 无防护路径 Promise 不 settle（20-screenshot-dedup.js:5-18）；㊳ initCustomSelect catch 半态双 UI（10-custom-select.js:30-32）；㊴ setInterval(updateLiveTokenStat) 回调无 try/catch（75:113）；㊵ 原地压缩不重渲染致 midx 错位（97:79-88 / 30:106）；㊶ addSysTip 调用守卫不一致（40-auto-compact.js:84 vs 91）；㊷ APP_VERSION 前端永无定义，导出 MD 页脚恒显 "v1.4"（85-session-mgmt.js:145）；㊸ 70-config.js:63 catch 分支回退含密钥写 localStorage（概率近零）；㊹ 76-cost-estimate.js:10 ` unauthorized` 前导空格致 401 不命中。
**CSS/溢出（Bug B 收尾）**：㊺ 输入框补 `overflow-y:auto; overflow-wrap:anywhere` 防御性声明；㊻ .sys-tip 补 max-width+word-break；㊼ .hint 行 min-width:0+ellipsis；㊽ .md-body table 加 overflow 包裹或 table-layout:fixed。
**v1.5 新模块**：㊾ ctx 徽标小数不取整两套舍入（34-local-model.js:132 vs 36-connect.js:248）；㊿ MCP 列表失败渲染成"还没有服务器"空态 + 导入 r.total 无兜底（29-mcp.js:25-28,451）；51 `_escId` 补双引号转义（85:206）；52 audit 非数组 entries TypeError（28-audit-viewer.js:89-95）；53 modelSelect change 双绑定 + connectManualPrefill 死变量（110-boot.js:25-29 vs 36-connect.js:811,152）；54 localProbeNow 无 busy 守卫 + localLoadModels 未 await 火跑（36-connect.js:586-605 / 34-local-model.js:142-212）；55 wsQuickRefresh 无 seq/在途保护（38-ws-quick.js:59）；56 set-nav 自动编号族可撞手写 id（33-set-nav.js:18）；57 formatTime(undefined) 显示 NaN（32-session-search.js:73）。

---

## 五、功能测试证据（本轮新增，tests/test_v15_known_bugs.py）

| 测试 | 类型 | 结果 | 证明 |
|---|---|---|---|
| TestCmdExecutionWindow::test_run_command_popen_hidden_and_single | 通过 | ✅ | run_command 一次调用只执行一次子进程，且 Popen 带 CREATE_NO_WINDOW（窗口安全+单次执行契约锁定） |
| TestCmdExecutionWindow::test_run_powershell_popen_hidden | 通过 | ✅ | PowerShell 同样隐藏窗口 |
| TestDecodeConsole::test_gbk/utf8_chinese_process_name | 通过 | ✅ | 中文进程名两种编码均正确解码（W10 的现状未爆雷锁定） |
| TestFrontendCmdDeduper::test_first_and_second_pass | 通过 | ✅ | 前两条不同命令放行（防修复误伤） |
| TestRunDeduperKeyNormalization（3 项） | xfail | 🔴 复现成功 | 变体/非紧邻重复当前放行（S1/S2 缺陷实证） |
| TestFrontendCmdDeduper（3 项，node vm 真实源码） | xfail | 🔴 复现成功 | 前端 deduper 同样放行（S1/S2 缺陷实证） |
| TestTextOverflowCss（4 项） | xfail | 🔴 复现成功 | 输入框/toast/工具卡片的溢出声明缺失（Bug B 缺口实证） |

**说明**：xfail(strict=False) 项断言的是"修复后应有的正确行为"，当前失败转 xfail；缺陷修复后自动 XPASS 不报错，届时摘除标记转正。前端测试从 `60-agent-loop.js` 正则抽取真实 `cmdDeduper` IIFE 源码在 vm 执行，非复刻伪实现。

**未能闭环的验证（需目标机）**：真实 WebView2 窗口的输入框/工具卡片视觉确认（本轮用 Edge headless 同引擎代理）；admin 二次提权端到端（需 UAC 实点）；MCP 连接池 SSE 修复后的真实服务器联调；`open_app` 弹窗面需模型实调。

---

## 六、审查总结

- **整体评分**：**84/100**（第三轮 82 → 84；前两轮修复经证伪抽查大面积真实成立，无假修复）
- **主要风险**：① 去重器语义缺陷（S1/S2）是用户实测"重复执行"的直接根因，且是两层同构失效；② 暂停悬挂 tool_calls（S3）会毒化会话导致持续 400；③ MCP 连接池 SSE 未排干（S6）是 Streamable HTTP 主流形态下的必发故障且被测试基建系统性漏检（HTTP/1.0 桩不复用）；④ localhost 子串绕过（S7）让 https 强制这一文档化安全控制完全失效。
- **优先修复 Top 10**：
  1. S1 deduper 全窗化（前端 `recent.has(key)` 无条件化 + 后端同口径，约 2 小时含测试摘 xfail）
  2. S2 键归一（引号/`./`/chcp/rem 统一，把 `first` 死代码接线，约 2 小时）
  3. S3 暂停 tool_calls 配平（抽 fillMissingToolResults，约 1 小时）
  4. S7 localhost hostname 精确比较（半小时，4/4 实证的安全控制失效）
  5. S6 连接池 SSE 排干/不健康归还（半天，含 HTTP/1.1 keep-alive 回归桩）
  6. S4 无 index 端点按 id/name 切块（2 小时）
  7. S11 local 信任读写判据对称（1 小时）
  8. Bug B 收尾：toast max-height + 工具卡片 min-width:0（1 小时，纯 CSS）
  9. S9 切预设失效在途识别（1 小时）
  10. S12 `__manual__` 哨兵过滤（半小时）
- **方法论沉淀（给维护者）**：本轮约 1/3 问题是"修复补丁之间的接缝"——单槽去重与全窗承诺、last-wins 与切预设、local 读写判据对称、renderChatHistory 与脏数据。两个可复用的检查动作：① 每个去重/缓存类修复，构造"非紧邻重复+语义等值变体"两条反例；② 每个 UI 状态机修复，画"所有写入点 × 所有退出路径"矩阵查漏复位（shotState/localWaitTimer/mcpTrusted 三处同病）。
- **正向评价**：v1.5 新增模块（mcp_pool/local_model/webdav/connect）分层与纯函数内核质量高；前两轮 78+63 项修复经本轮证伪抽查大面积真实成立；测试基线 546 → 551+10 xfail，已知缺陷已有可执行复现（修复后自动转正）。
