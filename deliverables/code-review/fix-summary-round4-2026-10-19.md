# Harbor 第四轮审查修复汇总（2026-10-19）

> 前置：round3 报告（full-code-review-2026-10-18-round3.md）之后，代码经 10-18~10-19 修复 +
> v1.6 开发（沙箱/GitHub Models/MCP resources/导航重构）。本轮先验证 round3 修复正确性
> （14 项干净落地 / 5 项部分 / 5 项未修 / 2 项修复引入新缺陷），再对 66 项新发现逐批修复。
> 验证终态：**pytest 688 passed / 1 skipped；UI 契约 check_contract PASS；前端重建 44 模块 9760 行**。

## 批次 A：命令执行与去重族（cmd_service / api / process / workspace / 前端接线）

| 项 | 修复 | 文件 |
|---|---|---|
| H1 open_app 参数错位 | js_api 层入参对齐 + 护栏 detail 正确取 path | backend/api.py |
| H8 open_app 前端接线 | 26-guard.js GUARD_OP_MAP/LABEL 增加 open_app；25-tool-exec.js executeToolRaw 增加 open_app 分支带 token；设置面板补三档 select（契约纯新增） | 26-guard.js / 25-tool-exec.js / index.template.html |
| H3 dedup_key 归一 | `_dedup_token` 剥首尾引号与 `./` `.\\` 前缀（保留 `..` 父目录语义），与前端键口径逐字一致 | cmd_service.py |
| M3 护栏 cmd 口径 | detail.cmd 取值与 executeToolRaw 一致（cmd/command 双键） | 26-guard.js |
| H7 unmark 键域 | open_app 失败回滚用同一 `'open_app ' + path` 键 | api.py |
| H9 截图 0 值 | `args.left || null` → `?? null` 系（0 坐标不再被吞） | 25-tool-exec.js |
| H10 count('') | 修正为 count('\ufffd')（原恒 len+1，乱码统计失真） | process_service.py |
| H11 daemon Timer | admin 临时文件延迟清理 Timer 置 daemon，防进程退出悬挂 | cmd_service.py |
| H11' save_workspace_file | name 消毒补 `..` 剥离 + 写盘异常保护 | workspace_service.py |
| ~~H15 reject 回滚~~ | **不采纳（误诊）**：check() 拒绝路径本就不改登记态；若拒绝即 unmark 会清除已执行写命令的登记，重蹈 Bug A | — |

## 批次 B：沙箱（sandbox_service）

- **H2 stdin 继承**：CreatePipe SECURITY_ATTRIBUTES.bInheritHandle=TRUE 语义补齐——父侧关写端、读端置不可继承，子进程 stdin 读即 EOF 而非句柄无效。**已实证**：临时脚本真跑沙箱，子进程 `sys.stdin.read()` 正常 EOF。
- **H4 ResumeThread 259 竞态**：返回值 `(DWORD)-1` 判定修正（原 `== -1` 与 c_ulong 比较恒假）。
- **H5 清理次序**：finally 中管道句柄 → 进程/线程句柄 → job.close()（KILL_ON_JOB_CLOSE 最后触发，避免先杀后读的半态）。
- **H6 use_last_error**：`WinDLL(..., use_last_error=True)` + 全部 `ctypes.get_last_error()` 路径收口，错误码不再被 C 库调用覆盖。
- **H13/H14**：签名声明与注释同步修正；cmd_service._exec 沙箱桩退化语义注释补全。
- 测试：test_sandbox.py + test_t9_sandbox_smoke.py 全绿。

## 批次 C：MCP / WebDAV / 本地模型

| 项 | 修复 |
|---|---|
| N1 连接池脏归还 | `_post_pooled` 成功路径 healthy=True 仅在响应完整消费后置位；异常路径 healthy=False 直接弃连接 |
| N1' SSE 排干 | `_read_sse` 命中响应帧后 `_drain_sse` 排干剩余流（同一 watchdog 上限，途中帧继续 dispatch）再归还——消除 CannotSendRequest('Request-sent') |
| N13 SSE buf 上限 | read1 缺失桩退化 + buf 上限保护 |
| N14 错误体上限 | `e.read()` 全读 → `read_cap` 限量（mcp_transport_http / local_model_service / provider_service 三处） |
| N2 warm 误杀 | `_idle_loop` reap 返回 (server, client) 对直接 close（原 pop 恒 None 永不关闭）；`_get_or_spawn` 命中/重拉路径正确更新 last_used 与 warm 注册 |
| N3 _normalize 密文 | dict 值不再 `str()` 强转，保持结构化（DPAPI 密文字典不再被损坏） |
| N12 import 键域 | 空值 env 条目=删键口径统一；import_claude 结构校验前置 + 落盘失败回滚内存态 |
| N4/N15 端口逃逸 | webdav urlsplit 端口 ValueError 捕获；`..` 路径穿越拒绝（_normalize_config） |
| N10 256MB 截断 | 下载侧 Content-Length 超 cap 预检 + 截断检测拒落盘（首版用 baseline 对拍误杀正常冲突流，已改截断自检口径，test_v15_wire 全绿） |
| N9 DPAPI 明文告警 | _record_for_io 口径核实安全（get_config 已解密），无回归 |
| N5 GitHub tool_capable | 目录硬编码 True → model_meta() 前缀推导（DeepSeek-R1 等不再误报支持工具） |
| N16/N17 reconnect | _reconnecting 置位/复位全程锁内；等待方超时上限与 owner 路径清理 |
| N18 resources/read | 500 防御 + audit 归因 + OUTPUT_CACHE_LIMIT 口径 |

## 批次 D：前端核心（agent-loop / toast / 瘦身管线 / send）

- **fe-H1 悬挂 tool_calls 配平**：`fillMissingToolResults(s)` 提取为共享函数，暂停 break 与 AbortError 双路径共用（会话毒化→持续 400 的根治）。
- **fe-H2 toast 死循环**：队列溢出让路逻辑补无 close 句柄分支的直接移除 + break 兜底。
- **fe-H3 __tool 豁免**：30-history-shrink 瘦身跳过 `__tool === 'read_file'/'read_more'`（去重键不被改写）；35-frozen-compact 复制保留 `__tool` 标记。
- **M 系**：shotState 'sending' 双路径复位（成功推标记消息 + catch 复位）；`_clearWaitTimer` 流正常结束也清理；recentSigs 交替检测口径修正；append_memory 只追加增量事实（memFlushed 游标）。
- **L 系**：uiPrompt 兜底 resolve 登记；工具卡片 `.tool-call-item>span` 补 `min-width:0`+省略号（长命令标签不再无声裁切）；`.tool-spinner` flex-shrink:0。
- **Bug B 收尾**：toast 容器/明细 max-height 与工具卡片 CSS 在前批已落。

## 批次 E：前端 v1.6 新模块（r4b 复审 6 项确认全修）

1. **[严重] mcpDeleteServer 首点必崩**：`_busy` 惰性初始化前置（29-mcp.js:159）——未点过开关直接删除时 undefined.has 抛 TypeError。
2. wsQuickRefresh 第二个 await 后补 seq 复检（last-wins 闭环，38-ws-quick.js）。
3. 头部状态区刷新挂点：updateBrandModel 尾部 + `__hitRate` 赋值后调 `navRenderHeaderStatus()`（原只渲染一次永久陈旧）。
4. 空态引导刷新：updateBrandModel + sendMessage 首条消息后调 `navUpdateEmptyGuide()`（老设置入口配 Key 路径不再卡遮层）。
5. 36-connect 识别/测试 Key 前置门统一 `meta.key_required` 判据（DeepSeek/Moonshot/Qwen/GitHub Models/自定义空 Key 不再直发请求 401）。
6. saveWebdavConfigNow 返回成败，导出/恢复在自动保存失败时中止（不再用旧配置执行数据主权操作）。

疑似项 3 条（按钮文案回滚/mcpResBusyUri 连点/localLoadModels stale 复位按钮）记录待验证，均有 btn.disabled 等兜底，不阻塞。

## 验证

- `pytest tests/ -q`：**688 passed, 1 skipped**（修复全程无回归；round3 的 10 个 xfail 此前已全部转正）
- `check_contract.py`：PASS（五大约束全保留；新增均为契约允许的纯增量）
- 沙箱 stdin 修复：真实 Win32 实证脚本通过
- 前端：`node frontend/build.js` 重建 9760 行
