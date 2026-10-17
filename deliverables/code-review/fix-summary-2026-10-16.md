# GLM-Chat 代码审查 78 项修复摘要报告

**日期**：2026-10-16 | **依据**：deliverables/code-review/full-code-review-2026-10-15.md（78 项：致命 2 / 严重 26 / 警告 31 / 建议 25）
**版本**：VERSION 1.3.0 → **1.3.1**（硬化补丁）| **测试基线**：151 → **347 passed**（+196 回归用例，全绿）

---

## 📌 TL;DR

78 项中 **77 项已修复并验证**，1 项不修（㊷ CSP——单文件全内联架构下必须 unsafe-inline，无实际防御增益，S19 fail-closed 已闭合真实攻击面）。修复过程中 QA 回归又**新抓到 4 个修复引入/潜伏的真实缺陷**（会话信任不覆盖 always 档、保护名单对相对路径失效、.bat 双重 CR 换行、uiConfirm 自我取消），已全部修复。契约四红线（build_tools 逐字节 / get_api_info / config.json 零污染 / UI 契约只增不改）零漂移。

## 发布门验证（本机实测，2026-10-16）

| 门禁 | 结果 |
|---|---|
| 全量 pytest | **347 passed**（66 契约/安全基线 + 85 v1.3 + 196 审查修复回归），两次全量复跑一致 |
| 契约差分 | test_api_contract.py 逐字节比对 legacy vs new **零漂移** |
| UI 契约 | check_contract.py **PASS**（40 DOM id / 13 onclick / 43 callApi / 39 CSS 类 / 21 变量只增未改） |
| 前端构建 | node build.js 35 模块成功，两次构建 md5 一致（F36245CAC21F519A82B9C6A7A824ABA5） |
| 版本 | APP_VERSION 动态读取验证 = **1.3.1** |

## 一、致命问题（2/2 已修）

| # | 修改内容 | 文件 | 验证 |
|---|---|---|---|
| C1 | kill_process 按 pid 调用时先 resolve_name_by_pid（tasklist /fi "PID eq"）反查进程名再走保护名单；pid 非数字直接报错（原 int() 失败静默放行） | backend/services/process_service.py | test_review_fixes.py::TestC1PidKillBypass 4 用例（含 lsass/csrss 反查拦截、taskkill 不触发断言） |
| C2 | ctypes 全套 restype/argtypes 显式声明（GlobalAlloc/GlobalLock/GlobalUnlock/GlobalFree/Get/SetClipboardData 等），64 位指针不再截断；cmd_service 的 MessageBoxW/ShellExecuteW 同类补齐 | backend/services/clipboard_service.py、cmd_service.py | TestC2CtypesSignatures + 真实机裸复现（GlobalAlloc/Lock/Set 链路实测通过） |

## 二、严重问题（26/26 已修）

| # | 修改内容（要点） | 主要文件 |
|---|---|---|
| S1 | setup_logging 早退修复：已初始化判断限定 RotatingFileHandler，落盘日志恢复 | backend/logging_setup.py |
| S2 | admin 命令改写临时 .bat 逐行执行拿真实 %errorlevel%（新旧两侧）；**.bat 以 newline='' 写盘**（QA 回归发现：内嵌 CRLF 经默认文本翻译落盘成 \r\r\n） | backend/services/cmd_service.py、main_v1.0.0_legacy.py |
| S3 | admin 完成信号改为 tmp_exit 可解析为 int；finally 清理全部临时文件 | cmd_service.py |
| S4 | **confirm-token 架构**：guard_service 进程内信任态（一次性 token，TTL=60s，绑定 op+detail 摘要，重放即失效）+ 武装标志（窗口就绪才强制，测试环境 legacy 兼容）+ clipboard_read/write/take_screenshot 补 enforce 挂点 + 内置关键进程名单默认非空；前端 26-guard.js 确认流程接 guard_confirm_token/guard_session_trust，各 op 尾参携带 token（旧 exe 兼容留空） | backend/services/guard_service.py、api.py；frontend/src/26-guard.js、25-tool-exec.js、62-mcp-exec.js |
| S5 | delete_path 根保护双侧 normcase(realpath) + 拒绝会话生效根 | backend/services/file_service.py |
| S6 | search_replace：二进制短路 + lossy 拒绝写回 + 原编码预检 + tmp+os.replace 原子写；**写回走 fio.atomic_write_text_mode 复刻 legacy 换行语义保契约** | file_service.py、backend/fio.py（新） |
| S7 | read_file 前置 os.stat 大小上限 + with 句柄 + auto_limit 逻辑修正 | file_service.py |
| S8 | 统一原子写 backend/fio.py（tmp+fsync+os.replace）；config/sessions/memory/guard/ws 状态全部接入；save_sessions 先校验合法 JSON | fio.py + config_service/runtime/guard_service/workspace_service/toolcache/mcp_config_service |
| S9 | main.py 启动 try/except + WebView2 缺失 MessageBox 提示 + 日志兜底 | main.py |
| S10 | toolcache OrderedDict 插入序淘汰 + 磁盘文件同步删除 + 启动清理 | toolcache_service.py |
| S11 | 超时后 taskkill /T /F 杀整棵进程树（模块级 _kill_tree） | cmd_service.py |
| S12 | MCP 断连错误帧先查 error 再校验 id（真实断连原因不再被「id 不匹配」掩盖） | mcp_client.py |
| S13 | HTTP 404 重连加 _retry 标志防无限递归 | mcp_client.py |
| S14 | SSE 增量读帧 + 整体 watchdog（read 到 EOF 不再绕过超时） | mcp_transport_http.py |
| S15 | urllib 禁自动重定向（_NoRedirectHandler），敏感头不再跨域转发 | mcp_transport_http.py、provider_service.py |
| S16 | save_server 未带 tierOverrides 时保留既有值（不再静默清空） | mcp_config_service.py |
| S17 | manifest 缺 sha256 直接拒绝下载（校验前置） | update_service.py |
| S18 | 截断续跑改 setTimeout 延迟到 isStreaming 复位后（死调用复活） | 60-agent-loop.js |
| S19 | renderMd fail-closed：无 DOMPurify/消毒异常 → escapeHtml 纯文本，删裸 marked 分支（XSS→RCE 链闭合） | 50-markdown.js |
| S20 | sendMessage 入口同步置 isStreaming（竞态双循环封堵） | 100-send.js、60-agent-loop.js |
| S21 | compactNow 清 s._readKeys（压缩后 read_file 去重不再说谎） | 97-compact.js |
| S22 | uiConfirm 全局 Promise 队列串行化 + 外部关闭/模态复用兜底 resolve {ok:false}；**追加修复（QA 回归发现）：先取模态再登记兜底 resolve，否则模态残留时新确认被自我取消** | 18-toast.js |
| S23 | 补 `let _auditFilter = 'all'` 声明（审计查看器首开崩溃修复） | 28-audit-viewer.js |
| S24 | zip 改 flate.Unzip 流式解压 + 200MB 累计中止（标志位+外层分块中止——fflate 会吞回调异常，报告原建议的回调抛错不可行，已实测修正） | 90-attachments.js |
| S25 | frozenForm 多模态数组分支移到 user 判断前（图片 base64 不再每轮全量重发） | 35-frozen-compact.js |
| S26 | normalizeSessions 统一归一化（Array/schema 校验、坏条目过滤） | 65-session-store.js |

## 三、警告（31/31 已修）

W1 ok() json.dumps default=str 序列化兜底+ensure_dirs 提前（errors.py/api.py）；W2 spec hiddenimports 补 send2trash/PIL.ImageGrab（GLM-Chat.spec）；W3 指纹缓存/历史加锁+触顶 pop（file_service.py）；W4/W5 legacy 临时文件 NamedTemporaryFile 唯一名+真实退出码透传、模块级副作用收进 main()+__main__ 守卫（main_v1.0.0_legacy.py）；W6 SetClipboardData 失败 GlobalFree+重试+全败明确报错；W7 截图最长边 1920 缩放；W8 append_file 限流触顶仅拒绝不重置；W9 RunDeduper 脱字符剥离+注释降级防呆；W10 无名单操作 list 档降级 confirm；W11 名单 pattern 入库 normcase+normpath、空 path 跳过；W12 审计日志 10MB 轮转+流式读；W13 tasklist 按 OEM 代码页解码；W14 截图保留最近 20 张/7 天+文档风险提示；W15 SSE 流内请求回 -32601/通知分流；W16 SSE 多行 data 聚合+BOM 剥离；W17 stdio 子进程环境白名单透传；W18 readline 上限+队列 maxsize；W19 spawn 前统一 expandvars；W20 get_server deepcopy；W21 解密失败键置空+告警；W22 list_changed 去抖合并刷新；W23 apply 前复核 sha256+bat sentinel+apply 后主动退出；W24 `!resp.ok && status===400`；W25 截图占位 content 字段；W26 切会话清信任态（前后端同步）；W27 增量记忆游标；W28 scheduleRender 按 el WeakSet；W29 localStorage 剔除密钥字段；W30 会话双源按 updatedAt 合并；W31 zip 白名单移出 .env/.reg/.properties。
（每项均有 `修复 Wn` 源码标记可查；警告项回归测试见 test_review_fixes.py 对应类）

## 四、建议（24/25 已修，1 项不修）

① runtime 死状态删除（win 保留：武装需要）② open() 补 with ③ legacy _TOOL_SEQ 加锁 ④ 尾部动态 import 提顶部 ⑤ 多层引号剥离 ⑥ save_config 解析失败显式报错 ⑦ pid 不再当名字 fnmatch ⑧ timeout or 吞 0 修正 ⑨ list_changed 标志复位 ⑩ HTTP is_alive 快速失败 ⑪ 关闭发 HTTP DELETE ⑫ HTTPError 保留 Session-Id+用户头不覆盖协议头 ⑬ stdio 线程启动失败回收子进程 ⑭ close/send 互斥 ⑮ args 用 shlex posix=False ⑯ 配置损坏留 .bad 备份 ⑰ DPAPI kernel32 单次加载 ⑱ 快照读加锁 ⑲ idle 扫描间隔修正 ⑳ 单调时钟 ㉑ 超时文案按实际值/-32601 文案修正 ㉒ 重名 _2 后缀派发一致性核实 ㉓ test_endpoint 结构校验报错 ㉔ manifest 占位发布 checklist ㉕ 旧 exe .bak 清理 ㉖ 死代码删除 ㉗ runAgentLoop 前置入 try ㉘ regenerate 重建全部历史 ㉙ 提前 return 清动画 ㉚ 缺 index 退单块聚合 ㉛ 数组 content 截断前归一 ㉜ MCP 开关在途保护 ㉝ 右键菜单死字段启用+execCommand 注释 ㉞ callApi clearTimeout+死函数删除 ㉟ Esc 模态优先 ㊱ executeToolRaw 边界 ㊲ callApi 补 catch ㊳ switchSession 先校验 ㊴ 折扣实时计算 ㊵ 更新 toast pinned ㊶ build.js 语法校验+`</script>` 检查 ㊸ 冷却戳仅成功盖+传参统一。
**㊷ CSP 不修**：单文件全内联架构下 CSP 必须 unsafe-inline，无实际防御增益；真实防线是 S19 fail-closed（已修）。

## 五、QA 对抗回归新抓到的 4 个真实缺陷（修复引入/潜伏，已全部二次修复）

| # | 缺陷 | 根因 | 修复 |
|---|---|---|---|
| QA-1 | 「本会话内不再提示」对 always 档失效 | enforce_exec 只在 session 档查信任 → 前端勾选后跳过弹窗、后端仍拒绝 | guard_service.enforce_exec 信任检查前移到档位判定之前（PRD R3 承诺对齐） |
| QA-2 | 保护名单对相对路径永不命中（v1.2 潜伏） | api.delete_path 传原始相对路径，_path_protected 的 abspath 落进程 CWD | api 侧 resolve_abs 按会话工作区解析绝对路径随 detail.abs_path 传入，guard 优先用之（token 摘要仍绑定原始 path，前后端口径不变） |
| QA-3 | .bat 落盘 \r\r\n（双重 CR） | 内嵌 CRLF 的串经 open('w') 默认换行翻译二次翻译 | cmd_service + legacy 两侧 bat 写入改 newline='' |
| QA-4 | uiConfirm 模态残留时新确认自我取消 | run() 先登记兜底 resolve 再调 _modalRoot，模态存在即触发兜底 | 调换两行顺序（先取模态后登记） |

## 六、测试基建修正（QA 半成品接力 + 忠实桩升级）

QA 工程师在 503 中断前写完 70KB 测试文件但未能完成调试；16 个失败全部裁定归属并修复：**测试侧 12 处**（C2 桩函数共享对象/S2 bat 文本模式读/token 重放漏写首耗/GUARD_FILE 常量名/建议① docstring 误匹配/S11 模块级函数名/死代码计数口径/S19 沙箱缺 __mkEl/S21 缺 AbortSignal/S23 筛选语义期望/S24 renderPreview 桩被源文件函数声明覆盖+缺 TextDecoder/S25 重复声明）+ **harness DOM 语义修正**（remove 后 getElementById 应返 null、appendChild 按 id 注册、modalRoot 全局开弹计数）+ **conftest 假剪贴板升级为忠实内存实现**（真实 buffer+句柄表+写入记录，reset_home 复位——对齐 C2 后真实 int 指针语义，支撑 W6 回读校验的差分一致性）。

## 七、发现项（留档，未修——保契约优先）

**legacy search_replace 累积换行污染**：bytes 解码不翻译换行 + 写回文本模式翻译，导致同一文件每次 search_replace 后 \r\n→\r\r\n 递增（实证 26→28→30 字节）。新实现为保契约差分逐字节一致，以 fio.atomic_write_text_mode 复刻该语义。**建议**：未来版本立项为 INTENTIONAL_DELTA（契约测试登记例外+结构断言）后首次修好它——属有意行为变更，需单独裁决。

## 八、遗留人工项（装机环境必测）

1. 起窗冒烟：S4 token 确认流端到端（弹窗→勾选信任→切会话失效）、审计查看器首开、截断续跑按钮
2. exe 打包 + 自更新实测（W2 hiddenimports 后 send2trash/PIL 在 frozen 包内可用性验证）
3. run_admin_command 真实 UAC 链路（S2/S3 的 .bat 路径本环境无法提权实测）
4. 剪贴板真实读写回环（C2/W6 在真实 Windows 剪贴板上）

## 九、过程实录（诚实记录）

工程师两度被模型配额 429 切断（reasoning/lite 轮换完成前后端两批）；QA 三度中断（冷却/503），其 70KB 测试文件遗留 16 个失败由主理人逐一裁定归属并完成修复（源码缺陷转修复、测试半成品修正）；QA 最终报告因中断未送达，本摘要的验证结论以 347 测试全绿 + 主理人逐项抽检为准。
