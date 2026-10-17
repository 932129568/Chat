# GLM-Chat 全项目深度代码审查报告

**审查日期**：2026-10-15
**审查范围**：`main.py`、`main_v1.0.0_legacy.py`、`backend/`（25 个 .py）、`frontend/src/`（36 个 .js）、`frontend/build.js`、`index.template.html`、`GLM-Chat.spec`
**审查方式**：5 路并行逐行审查（后端核心层 / 后端基础服务 / MCP+provider+update / 前端核心 / 前端其余），交叉核验调用链
**测试基线**：`pytest tests/ -q` → **151 passed**（本次为只读审查，未改任何代码）
**问题总数**：去重后 **78** 个（致命 2 / 严重 24 / 警告 27 / 建议 25）

> 严重程度定义：致命=可致崩溃/数据丢失/安全失守；严重=明显 Bug 或重大隐患；警告=潜在风险/代码异味；建议=可选优化。
> 标「疑似」者均已附最小验证方法。

---

## 一、致命问题（发版前必须修复）

### C1. `kill_process(pid=...)` 绕过全部进程名保护名单，可强杀系统关键进程
- **位置**：`backend/services/process_service.py:60-71,73-85`；`backend/services/guard_service.py:170-174`
```python
# process_service
if pid is not None:
    if pid_i in PROTECTED_PIDS or pid_i == os.getpid(): ...   # 只查 {0,4,self}
if name:
    if str(name).strip().lower() in PROTECTED_NAMES: ...      # 名单只匹配名字
# guard_service
hit = self._process_protected(detail.get('name')) or self._process_protected(detail.get('pid'))
```
- **描述**：所有名字保护（内置名单、guard 用户名单）都只匹配进程名。按 pid 调用时不传 name：process_service 只拦 PID 0/4/自身；guard 侧把 pid 数字当名字做 fnmatch，永远匹配不上 `lsass.exe` 这类名单项。`_protection_reason` 中 `int(pid)` 失败还会直接放行。
- **后果**：AI 或恶意提示词先 `list_processes` 拿 lsass.exe/csrss.exe 的 pid，再 `kill_process(pid=...)` 即可强杀——杀 lsass 触发系统强制重启。护栏宣称的关键进程保护被完全绕过。
- **修复建议**：kill 前用 pid 反查进程名（`tasklist /fi "PID eq {pid}" /fo csv /nh` 或 psutil），统一走名字名单校验；pid 非数字直接返回错误。
- **置信度**：确认

### C2. clipboard_service 未设 ctypes restype/argtypes，64 位下 GlobalLock 指针截断
- **位置**：`backend/services/clipboard_service.py:19-26, 54-61`
```python
p = k32.GlobalLock(h)          # ctypes 默认 restype=c_int，64 位指针被截断
ctypes.memmove(p, ctypes.create_unicode_buffer(data), size)
```
- **描述**：ctypes 函数默认 `restype=c_int`。`GlobalLock` 返回 64 位指针，高 32 位非零时被截断为 32 位有符号 int，随后 `c_wchar_p(p).value`（读）与 `memmove(p,...)`（写）操作错误地址。
- **后果**：读野内存或 Access Violation 进程崩溃；写路径 memmove 到错误地址 → 内存损坏。同类隐患亦存在于 `cmd_service.py` 的 `MessageBoxW`/`ShellExecuteW`（危害较小）。
- **修复建议**：
```python
from ctypes import wintypes
k32.GlobalAlloc.restype = wintypes.HGLOBAL
k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
k32.GlobalLock.restype = ctypes.c_void_p
k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
u32.GetClipboardData.restype = wintypes.HANDLE
```
- **置信度**：误用确认；是否实际崩溃疑似（取决于堆地址分布，64 位 Python 上 `print(hex(k32.GlobalLock(h)))` 可验证）

---

## 二、严重问题（建议本版本修复）

### S1. `setup_logging` 永远早退，落盘日志完全失效
- **位置**：`backend/logging_setup.py:20` + `:42`（模块级 `addHandler(NullHandler())`）
- **描述**：import 时 L42 已挂 NullHandler；`setup_logging()` 的 `if logger.handlers: return` 恒为真，RotatingFileHandler 永远不会被添加。文件头注释自称"重构补齐日志"，实际全部后端日志仍被静默吞掉。
- **后果**：`glm-chat.log` 永不生成，生产问题不可诊断（叠加 S9 启动无兜底 → 双重失明）。
- **修复**：已初始化判断限定文件 handler：`if any(isinstance(h, RotatingFileHandler) for h in logger.handlers): return logger`；删除重复 NullHandler。
- **置信度**：确认

### S2. `run_admin_command` 的 `%errorlevel%` 解析期展开，"真实退出码"恒为启动前值
- **位置**：`backend/services/cmd_service.py:205`
```python
full_cmd = f'{cmd} > "{tmp_out}" 2>&1 & echo %errorlevel% > "{tmp_exit}"'
```
- **描述**：CMD 对整条 `/c` 命令行先一次性展开所有 `%var%` 再执行，`%errorlevel%` 展开为 cmd 启动时的初始值（恒 0）。模块宣称"透传真实退出码（修 legacy 恒 0）"实际未达成。`cmd /c "exit /b 3 & echo %errorlevel%"` 可本地验证输出 0。
- **后果**：管理员命令失败被误报成功，AI 据此继续错误操作。
- **修复**：改写临时 .bat（bat 内逐行解析无此问题）再 `ShellExecuteW('runas', bat)`；或 `cmd /v:on /c` + `!errorlevel!`（注意引号嵌套）。
- **置信度**：确认

### S3. admin 命令输出"大小不变即完成"误判 + 超时泄漏临时文件
- **位置**：`backend/services/cmd_service.py:209-233`
- **描述**：完成判定只看相邻两次 0.5s 采样文件大小相同——cmd 重定向有缓冲，运行中大小可长期不变，第二轮即误判完成读到空/半截输出，且 `tmp_exit` 未写 → exit_code=None，随后 `os.remove(tmp_out)` 删的是仍在写入的文件（Windows 可抛 Sharing Violation）。超时 return 前不清理 tmp_out/tmp_exit，%TEMP% 泄漏。
- **后果**：管理员命令频繁返回空输出+未知退出码；临时文件泄漏。
- **修复**：以 `tmp_exit` 出现且内容可解析为 int 作为完成信号；超时分支 finally 清理两个临时文件。
- **置信度**：确认

### S4. js_api 无调用来源校验 + 护栏 always/session 档后端零强制（架构性攻击面）
- **位置**：`backend/api.py:154-160,172-198`（`run_command`/`run_powershell`/`run_admin_command`/`kill_process`/`rpc`）；`backend/services/guard_service.py:180-190`
- **描述**：pywebview js_api 对 webview 内所有 JS 可见，后端无来源校验；`enforce_block_only` 只在名单 block 时拦截，always/session 档的确认纯靠前端 UI，注入脚本可伪造；`clipboard_write`/`clipboard_read`/`take_screenshot` 三个 op 在 api.py 完全没有 enforce 挂点；guard 默认名单为空。与前端 S19（markdown 消毒 fail-open）组合即成"远端内容→本机 RCE"完整链路。
- **后果**：任何前端 XSS = 本机任意命令执行/杀进程/触发更新。
- **修复**：① 后端持有会话信任态，always 档要求一次性 confirm token（带 TTL）；② 三个未挂点 op 补 enforce；③ guard 内置关键进程名单默认非空；④ 前端渲染 fail-closed（见 S19）。
- **置信度**：暴露面确认；利用链依赖前端注入点（S19 提供了一个候选）

### S5. `delete_path` 工作区根保护因路径规范化不对称可绕过，可删整个工作区根
- **位置**：`backend/services/file_service.py:297-300`
```python
p = path                                # 已 normcase(realpath(...))，小写
if p == os.path.abspath(cwd) or ...     # cwd 未 normcase/realpath
```
- **描述**：`p` 是全小写规范化结果，`os.path.abspath(cwd)` 含大写（默认 `C:\Users\...`）→ 等式恒不成立；`_resolve_ws` 又显式放行 `abs_p == abs_root` → `delete_path('')` 直达删除分支。未装 send2trash 时降级为 `shutil.rmtree` 永久删除整个工作区。
- **后果**：一条 AI 指令永久删除整个工作区根目录。
- **修复**：`if os.path.normcase(os.path.realpath(cwd)) == p or os.path.dirname(p) == p:`，并同时拒绝 `p == effective_root(sid)`。
- **置信度**：确认

### S6. `search_replace` 编码回写可致用户文件不可逆损坏
- **位置**：`backend/services/file_service.py:259-276`
- **描述**：① GBK 文件插入 GBK 无法编码字符（emoji 等）→ `errors='replace'` 静默写成 `?` 且无告警；② 既非 UTF-8 也非 GBK 的文件（UTF-16 无 BOM 等）解码成含 U+FFFD 的乱码，命中即以 UTF-8 写回全毁；③ 无 read_file 的 `b'\x00'` 二进制短路；④ 截断式直写非原子。write_file 有 >20KB 拒绝保护，search_replace 无任何编码护栏。
- **后果**：中文环境常见 GBK 源码被静默引入 `?`；二进制/UTF-16 文件全毁。
- **修复**：`_decode_bytes` 返回 `lossy` 标志，lossy 即拒绝写回；写回前 `new_text.encode(enc)` 预检；统一 tmp+os.replace 原子写。
- **置信度**：确认

### S7. `read_file` 整文件读入内存，无大小上限
- **位置**：`backend/services/file_service.py:175-179`
- **描述**：无 `os.stat` 前置检查，二进制短路发生在读完之后；BUDGET=240000 只限返回部分不限读入部分。AI 对 10GB 日志调 read_file → 主进程 OOM/崩溃。`open(...).read()` 未用 with。另 auto_limit 逻辑与注释自相矛盾（注释称"≤2000 行一次读全"，实际 1500 行文件只读 800 行需二轮）。
- **修复**：先 `os.stat`，超阈值（如 64MB）拒绝并提示分页读取；with 管理句柄；auto_limit 改为 `limit = 1200 if total > 2000 else 2000`。
- **置信度**：确认

### S8. 全部配置/会话/状态文件"截断式直写"，崩溃即损坏且恢复能力参差
- **位置**：`backend/runtime.py:55-64`；`config_service.py:56,87,105,128`；`guard_service.py:118`；`workspace_service.py:51,153`；`toolcache/mcp_config_service` 同模式
- **描述**：config.json/sessions.json/memory.json/guard.json/session_ws.json 等均 `open('w')` 原地截断写，无 tmp+os.replace。写一半断电 → 半截 JSON。且恢复能力最差恰是最关键的：config.json 损坏静默回退 `{}`（配置全丢）、sessions.json 损坏波及整个会话列表；`save_sessions` 还不校验前端传入字符串是否合法 JSON。
- **修复**：统一 `_atomic_write(path, text)`（tmp+fsync+os.replace）；`save_sessions` 先 `json.loads` 校验。
- **置信度**：确认

### S9. main.py 启动路径无异常兜底（叠加 S1 后启动失败零痕迹）
- **位置**：`main.py:84-109`
- **描述**：`webview.create_window`/`webview.start()` 无 try/except；WebView2 Runtime 缺失时进程静默退出，console=False + 日志失效 → 用户双击 exe "什么都没发生"。
- **修复**：try/except + MessageBox 提示安装 WebView2 + 日志（依赖 S1 修复）。
- **置信度**：确认

### S10. toolcache 磁盘文件永不删除 + 淘汰键字典序错乱
- **位置**：`backend/services/toolcache_service.py:31-39`
- **描述**：① 淘汰只 pop 内存映射，`TOOLCACHE_DIR` 下 .txt 从不删除，磁盘无限膨胀；② `sorted(self._mem)[0]` 按字符串排序，`'tc10_x' < 'tc2_x'`，seq≥10 后淘汰的反而是较新缓存。
- **修复**：`OrderedDict` + `popitem(last=False)`，淘汰时同步 `os.remove(fp)`；启动清理过期文件。
- **置信度**：确认

### S11. subprocess 超时只杀 shell 本身，孙进程成孤儿且可能二次阻塞
- **位置**：`backend/services/cmd_service.py:121-123,148-149,166-168`
- **描述**：`subprocess.run(timeout=)` 超时只 kill 直接子进程（cmd/powershell），孙进程（start 拉起的程序、编译、pip）Windows 下不被回收；且超时后 communicate 等管道 EOF，孙进程继承 stdout 不退则二次阻塞远超 timeout。
- **修复**：Popen + Job Object（KILL_ON_JOB_CLOSE），或超时后 `taskkill /T /F /PID <pid>` 杀整树。
- **置信度**：确认（Windows 文档化行为）

### S12. MCP：`_fail_pending` 注入的错误帧 id=None 被 `_unwrap` 误判，真实错误被掩盖
- **位置**：`backend/services/mcp_client.py:227-228` + `:323-330`
- **描述**：断连时注入 `id: None` 错误帧，`_unwrap` 先校验 id → `str(None) != str(rid)` → 抛"响应 id 不匹配"，永远到不了 error 分支。所有断连场景用户看到的都是无意义的 id 不匹配，`last_error` 被污染。
- **修复**：`_unwrap` 先查 `error` 再校验 id（规范允许错误帧带 null id）。
- **置信度**：确认

### S13. MCP：HTTP 404 会话过期重试可无限递归
- **位置**：`backend/services/mcp_client.py:185-200` + `:254-265`
- **描述**：`_initialized` 握手后恒 True；`_reconnect()` 内部 initialize 再遇 404 会递归进入重试分支，无次数上限，约 330 层后 RecursionError 才被兜底，每层都发网络请求放大故障时延。
- **修复**：加 `_retry` 内部标志，重试路径再 404 直接抛。
- **置信度**：确认

### S14. MCP：SSE 响应 `resp.read()` 读到 EOF，60s 超时名存实亡
- **位置**：`backend/services/mcp_transport_http.py:59,75`
- **描述**：`urlopen(timeout=)` 只是单次 socket 操作超时；`resp.read()` 阻塞到 EOF，服务器每隔 <timeout 秒发一行 keepalive 注释即可让 read 永不返回。恶意/异常 MCP 服务器可让 tools/call 无限期挂起并占住调用线程。
- **修复**：增量读（read1/按行），拿到首个完整 data 帧即 close 返回；加整体 watchdog。
- **置信度**：确认

### S15. urllib 自动重定向跨域转发 Authorization / Mcp-Session-Id（两处）
- **位置**：`backend/services/mcp_transport_http.py:54-59`；`backend/services/provider_service.py:57-62`
- **描述**：urllib 的 redirect_request 把原始全部 headers（含用户配置的 Authorization、会话 id、API Key）复制到重定向请求且不区分跨主机。恶意/被入侵端点返回 302 指向攻击者域名即窃取凭证。provider_service 还不限制 scheme，http:// 端点下密钥明文出网无提示。
- **后果**：DPAPI 保护的凭证在网络层明文泄露给第三方。
- **修复**：禁用自动重定向（自定义 handler）或重定向剥离敏感头；非 https 端点显式警告。
- **置信度**：确认

### S16. MCP `save_server` 全量重建 record，`tierOverrides` 可被静默清空
- **位置**：`backend/services/mcp_config_service.py:134,166-175,203`
- **描述**：`_normalize` 只透传白名单键；面板保存若不带 `tierOverrides` → `cfg.get('tierOverrides') or {}` → 用户逐工具档位覆盖全部丢失，任何扩展键同命运。
- **修复**：`'tierOverrides' not in cfg` 时保留 `existing.get('tierOverrides')`。
- **置信度**：服务层确认；是否触发取决于 Api 层是否总传全量（疑似，可用不含 tierOverrides 的保存用例验证）

### S17. update：manifest 缺 sha256 时完全跳过完整性校验，仍可 apply
- **位置**：`backend/services/update_service.py:145`
```python
if sha256 and digest.lower() != sha256.lower():
```
- **描述**：sha256 为空/缺失时短路跳过校验，状态照样 done，apply 畅通。manifest 源可配置，若是 http 源则 TLS 与哈希双无。
- **后果**：被入侵/降级源场景下可安装任意 exe。
- **修复**：sha256 缺失直接拒绝下载；校验前置。
- **置信度**：确认

### S18. 前端：`finish_reason='length'` 自动续跑是死调用，截断输出永不继续
- **位置**：`frontend/src/60-agent-loop.js:300-305` + `100-send.js:82-85`
- **描述**：`continueLastGeneration` 第一行 `if (isStreaming) return;`，调用点仍在 runAgentLoop 的 try 块内（isStreaming 未复位），async 函数首 await 前同步执行 → 立即返回什么都不做；且走 `autoResume<=5` 分支连手动「继续输出」按钮都不渲染。
- **后果**：用户得到永久截断回复且无任何续跑入口。
- **修复**：`setTimeout(() => continueLastGeneration(s, apiKey), 350)` 延迟到 finally 复位之后。
- **置信度**：确认（控制流可静态推导）

### S19. 前端：renderMd 消毒失败 fail-open 到裸 marked，构成 XSS→RCE 通道
- **位置**：`frontend/src/50-markdown.js:13-17`
```js
if (window.marked && window.DOMPurify) { try { return DOMPurify.sanitize(marked.parse(text||'')); } catch(e){} }
if (window.marked) { try { return marked.parse(text||''); } catch(e){} }   // 未消毒
```
- **描述**：purify.min.js 加载失败或 sanitize 抛异常 → 落到未消毒分支写 innerHTML。模型输出是半不可信输入（提示注入可诱导 `<img onerror>`），pywebview 下 XSS = 拿到全部 js_api 本地能力（与 S4 闭环）。
- **修复**：fail-closed——没有 DOMPurify 就不用 marked：`return '<p>' + escapeHtml(text||'') + '</p>'`。
- **置信度**：确认

### S20. 前端：sendMessage→runAgentLoop 竞态可起两个并发 Agent 循环
- **位置**：`frontend/src/100-send.js:2-3,80` + `60-agent-loop.js:3-6`
- **描述**：`isStreaming` 在 runAgentLoop 内两个 `await`（桥往返数 ms~数十 ms）之后才置位；sendMessage 自身也有前置 await。Enter 长按连发/快速双击可在置位前通过守卫。
- **后果**：双循环写同一 `s.messages`：消息交错、tool 配对错乱、计费翻倍、去重失效。
- **修复**：sendMessage 入口同步置 `isStreaming = true`。
- **置信度**：确认

### S21. 前端：compactNow 清消息但不清 `s._readKeys`，压缩后 read_file 去重返回谎言
- **位置**：`frontend/src/97-compact.js:70-77` + `60-agent-loop.js:68,377-384`
- **描述**：压缩把含文件原文的消息换成 ≤200 字纪要，但 `_readKeys` 未清；之后 read_file 同路径被去重拦截并告知"原文仍在上下文中，禁止重读"——实际已不在。
- **后果**：压缩后 AI 无法再获取文件内容，只能凭纪要臆测 → 幻觉/错误补丁。
- **修复**：compactNow 中 `s._readKeys = []`。
- **置信度**：确认

### S22. 前端：同一批并发工具触发多个 uiConfirm，单例模态互相覆盖，Promise 永不 resolve
- **位置**：`frontend/src/60-agent-loop.js:371-375` + `18-toast.js:53-103` + `26-guard.js:79` + `62-mcp-exec.js:58`
- **描述**：批划分只按 WRITE_SEQ_TOOLS 切串行点；`kill_process`/`clipboard_*`/`take_screenshot`/所有 mcp 工具都不在列表。LLM 同批发出两个受护栏工具 → 两个 `await uiConfirm` 并发 → 第二次 `_modalRoot().innerHTML=...` 覆盖第一个模态，第一个 Promise 的 resolve 随 DOM 销毁 → Promise.all 永不 settle → isStreaming 永远 true，**应用卡死只能重启**。
- **修复**：uiConfirm 加全局队列串行化；关闭模态时以 `{ok:false}` 兜底 resolve 挂起确认。
- **置信度**：确认（机制确定，触发频率取决于 LLM 同批输出）

### S23. 前端：`_auditFilter` 从未声明，审计查看器首次打开必崩
- **位置**：`frontend/src/28-audit-viewer.js:58,85`（全项目 grep 无 let/const/var 声明）
- **描述**：读取未声明变量抛 ReferenceError，`openAuditViewer` 首次执行即崩，面板永远停在"加载中…"。PRD Q6 功能开箱即坏。
- **修复**：文件顶部 `let _auditFilter = 'all';`
- **置信度**：确认

### S24. 前端：zip 附件解压后无总量上限，zip bomb 耗尽内存
- **位置**：`frontend/src/90-attachments.js:32-41`
- **描述**：`flate.unzipSync` 一次性全量解压进内存，50MB 上限只查压缩前；2MB/文件与 100KB 合并上限都在解压之后。高压缩率包可解压至数 GB（代码注释自知"假死"但防线无效）。
- **修复**：用 `flate.Unzip` 流式回调按累计大小中止（超 200MB 抛错）。
- **置信度**：确认

> 另两项严重归入 S25/S26：
> - **S25** `frontend/src/35-frozen-compact.js:4,11-16`：frozenForm 第 4 行对 user 无条件 return，使 U8 多模态压缩分支成死代码——**图片 base64 每轮全量重发**，token 成本远超设计。修复：数组分支移到 user 判断之前（只压 image_url/video_url part）。确认。
> - **S26** `frontend/src/65-session-store.js:6,10`：loadSessions 无 `Array.isArray`/schema 校验，`{}` 通过 parse 后 `sessions.find` 崩；不校验 `s.messages` → `75-token-stat.js:30` 等处级联 TypeError。修复：normalizeSessions 统一归一化。确认。

---

## 三、警告（27 项，摘要+位置+修法要点）

| # | 位置 | 问题 | 修法要点 |
|---|---|---|---|
| W1 | api.py:53-71 + errors.py:10-12 | `errors.ok()` 无序列化兜底，不可序列化 payload 穿透 js_api 破坏返回协议；Api.__init__ 末尾才 ensure_dirs | `json.dumps(..., default=str)`；ensure_dirs 提前 |
| W2 | GLM-Chat.spec:9 | hiddenimports=[]，懒加载的 send2trash/PIL 在 frozen 包中静默缺失 | hiddenimports 补 send2trash、PIL.ImageGrab，frozen 实测 |
| W3 | file_service.py:22-54,63,234 | FileFingerprintCache 与 _append_hist 无锁（pywebview 多线程回调竞态），hist 键只增不删 | 加 RLock；触顶用 pop 非置空 |
| W4 | legacy:650-668 | legacy admin 临时文件仅按 pid 命名，同进程并发必撞；恒返回 exit 0 | 归档不修；若发布则 NamedTemporaryFile |
| W5 | legacy:1246-1326 | legacy 模块级副作用：import 即弹窗阻塞 | 归档不修；防误 import 加 `__main__` 守卫说明 |
| W6 | clipboard_service.py:67-83（+legacy:735-742） | SetClipboardData 返回值不检查，失败时 GMEM 泄漏；6 次全败返回"已写入"误导文案 | 检查 NULL→GlobalFree→重试；区分未写入/未验证 |
| W7 | screenshot_service.py:31-35 | 多屏 4K 截图 base64 数 MB 经 js_api 桥返回，桥接卡顿风险 | 最长边 1920 缩放后编码 |
| W8 | file_service.py:233-240 | append_file 限流触顶即重置，实为"每 7 次拦 1 次"，与文案承诺不符 | 触顶仅 return err 不重置，或令牌桶 |
| W9 | cmd_service.py:48-53 | RunDeduper 可被 `d^el` 等 CMD 脱字符绕过，注释却宣称"堵绕过" | 注释降级为防呆；token 先剥 `^` |
| W10 | guard_service.py:165-179 | 无名单操作（clipboard/screenshot）设 'list' 档语义等同 off，UI 误导 | 无名单操作隐藏 list 选项或降级 confirm |
| W11 | guard_service.py:126-133 | 名单 pattern 不做 realpath 归一，写法差异即静默失效；path 为空时 abspath('') 落到 CWD 误伤 | pattern 入库统一 normcase(realpath)；空 path 跳过 |
| W12 | guard_service.py:203-226 | 审计日志无轮转，read_audit 全量读内存 | 10MB 轮转；deque(maxlen) 流式读 |
| W13 | process_service.py:35-37 | tasklist 输出 UTF-8→GBK 启发式回退误判，进程名乱码致过滤/按名 kill 失效 | 按 OEM 代码页优先解码 |
| W14 | screenshot/clipboard | 截图永久留存 ~/.glm-chat/screenshots 无清理；剪贴板可能含密码 | 保留最近 N 张/7 天；文档明示风险 |
| W15 | mcp_client.py:185-200 | HTTP 模式 SSE 流中服务器请求/通知不处理（首帧 notification 即 id 不匹配报错） | 循环读帧：notification 交 _handle_frame，请求回 -32601 |
| W16 | mcp_transport_http.py:91-102 | SSE 解析不支持多行 data/BOM，仅取首帧 | 按空行切事件聚合 data 行；剥 BOM |
| W17 | mcp_transport_stdio.py:36-38 | 子进程完整继承 os.environ，环境变量密钥泄漏给不可信 MCP 服务器 | 默认白名单透传（PATH/SystemRoot/TEMP 等） |
| W18 | mcp_transport_stdio.py:91 + queue 无 maxsize | 超长单行/通知洪泛无内存上限（远程 DoS） | readline(limit) 超限断开；队列设 maxsize |
| W19 | mcp_config_service.py:290 vs mcp_service.py:404 | precheck 做 expandvars、实际 spawn 不做，含 %VAR% 命令预检通过启动失败 | spawn 前统一 expandvars |
| W20 | mcp_config_service.py:109 | get_server 浅拷贝，嵌套 dict 共享引用可绕锁污染内存配置 | copy.deepcopy |
| W21 | mcp_dpapi.py:116-118 + mcp_config_service.py:111-117 | 解密失败兜底返回 `dpapi:密文串` 当真实密钥下发子进程 | 解密失败键置 ''，仅经 decrypt_failed 告警；加密失败明文落盘需面板可见提示 |
| W22 | mcp_service.py:425-433 | list_changed 通知无去抖，每条起一个刷新线程（自我 DoS） | entry 级 refreshing 标志+合并 |
| W23 | update_service.py:173-198 | apply 前不复核哈希（TOCTOU 篡改窗口）；bat 等 PID 复用/30s 强替失败静默；apply 后进程不退出致必然失败（疑似需验证 js_api 退出链路） | apply 开头重算 sha256；bat 写 sentinel；apply 后主动退出 |
| W24 | 60-agent-loop.js:159-163 | `resp.ok && resp.status===400` 恒假死分支，thinking 降级重试永不生效 | 改 `!resp.ok && resp.status===400` |
| W25 | 60-agent-loop.js:220 | 截图占位消息写错字段 `text` 而非 `content`，混入空 user 消息 | 改 content |
| W26 | 62-mcp-exec.js:33,71 | mcpTrusted 文案"本会话内不再提示"实为进程级永久信任，切会话不清 | newSession/switchSession 中 clear，与文案对齐 |
| W27 | 60-agent-loop.js:517-519 | 每轮工具调用 append_memory 全量 taskFacts，记忆文件二次方膨胀挤占 prompt | 只追加增量（_memFlushed 游标） |

> 另四项警告并入：W28 `50-markdown.js:19-24` scheduleRender 全局单 `_rafPending` 丢帧（按 el 用 WeakSet）；W29 `70-config.js:47` api_key/provider_key 明文双写 localStorage（剔除密钥字段仅走后端）；W30 `65-session-store.js:2-29` 会话双写读后端优先、后端写失败时新会话静默回退（按 updatedAt 合并两源）；W31 `90-attachments.js:36` zip 白名单含 .env/.reg/.properties 密钥直发云端（移出白名单+敏感内容掩码）。

---

## 四、建议（25 项，一行一条）

**后端核心**：① runtime.win/form/core/last_bounds 只写不读死状态（删或补消费者）；② `open(...).read()` 多处未用 with；③ legacy `_TOOL_SEQ` 自增非原子（归档不修）。
**基础服务**：④ file_service/workspace_service 尾部 `time_time()` 包装函数动态 import 应改顶部 import；⑤ `p.strip().strip('"')` 只剥一层引号；⑥ save_config 解析失败静默返回 ok:true 应显式报错；⑦ guard 把 pid 当名字 fnmatch，用户名单含 `*` 时误伤一切（与 C1 合并修）。
**MCP/update**：⑧ `_request` 的 `timeout or CONNECT_TIMEOUT` 吞 0 值；⑨ tools_list_changed 标志置位后永不复位；⑩ HTTP is_alive() 恒真无快速失败；⑪ 关闭会话不发 HTTP DELETE（服务端会话泄漏）；⑫ HTTPError 分支丢 Mcp-Session-Id；用户 headers 可覆盖协议头；⑬ stdio start() 线程启动失败泄漏子进程；⑭ close() 与 send() 无互斥；⑮ args 字符串 `split()` 破坏带空格参数（改 shlex posix=False）；⑯ 配置损坏不留备份即覆盖；⑰ DPAPI LocalFree 依赖二次加载 kernel32；⑱ mcp_service 无锁读多字段快照可撕开；⑲ idle 扫描 `min(30,1.0)` 恒 1s 与常量意图不符；⑳ idle 用 time.time() 非单调时钟；㉑ 超时文案硬编码 60 秒、-32601 文案错配 tools/call；㉒ tool_schemas 重名 `_2` 后缀与派发反解一致性疑似（需核 js_api 派发）；㉓ provider test_endpoint 200 但结构异常静默吞错；㉔ 默认 manifest URL 是占位假仓库 + 版本回退常量 1.2.2 会过期（发布 checklist）；㉕ 旧 exe `.bak` 永久残留。
**前端**：㉖ archiveOldTasks while 回退是死代码；㉗ runAgentLoop 前 27 行在 try 外，throw 变 unhandled rejection 且 isStreaming 卡死；㉘ regenerate 重渲染只恢复 user 消息，历史 assistant 从界面消失（警告级 UI）；㉙ 提前 return/break 路径留永久"正在输入"三点动画；㉚ 工具流式聚合依赖 tc.index，缺 index 的兼容端点合并错乱（疑似）；㉛ 工具结果截断假设 content 为字符串，MCP 数组型 content 绕过截断（疑似）；㉜ MCP 开关/测试无在途保护连点并发写；㉝ 右键菜单 enabled 死字段 + execCommand('paste') 在 WebView2 无效；㉞ callApi 竞速定时器不 clearTimeout + backendErrorMsg 死代码；㉟ Esc 与模态冲突误 abort 流式生成；㊱ executeToolRaw 缺 path 传 undefined、`timeout||60` 吞 0、catch 输出 `{}`；㊲ newSession/switchSession 的 callApi 未 await 无 rejection 处理；㊳ switchSession 先赋值后校验存在性；㊴ token 统计硬编码"约 2.9 折"与实际价格脱钩；㊵ 更新 toast 60s 后消失进度不可见；㊶ build.js 无产物语法校验、无模块内 `</script>` 检查（ASI 靠运气）；㊷ index.template.html 无 CSP（纵深防御缺失，需渐进式）；㊸ maybeAutoCompact 失败也盖冷却戳 + compactHistory 传参形态不一致。

---

## 五、审查总结

- **整体评分**：**68/100**
- **主要风险**：两条护栏绕过（C1 pid 强杀、S5 删工作区根）+ 一条 XSS→RCE 架构链（S4+S19）+ 一个 ctypes 定时炸弹（C2），是"安全承诺与实现不符"的系统性短板；前端四个严重问题全部集中在异步时序（S18/S20/S21/S22），会直接造成应用假死或资金浪费。
- **优先修复 Top 10**（建议按序）：
  1. **C1** kill_process pid 归一化（半天）
  2. **C2** clipboard ctypes restype（1 小时）
  3. **S5** delete_path 根保护 normcase（半小时）
  4. **S19** renderMd fail-closed（半小时）
  5. **S23** `_auditFilter` 声明（一行）
  6. **S18** 截断续跑 setTimeout（一行级）
  7. **S22** uiConfirm 串行队列（半天）
  8. **S1** logging 早退（半小时，否则其余修复无日志可看）
  9. **S2** admin 退出码 .bat 化（半天）
  10. **S8** 统一原子写（半天，惠及所有配置面）
- **正向评价**：重构版在锁（RuntimeState/GuardService/ToolcacheService）、错误协议（errors.ok/err 统一 JSON）、路径监狱（_resolve_ws 的 realpath+normcase 前缀判定正确）、护栏分层、成本防御熔断、双写持久化等设计上明显高于一般个人项目；契约测试基线 151 passed 提供了可靠的回归保障。
- **证伪门禁说明**：所有标"确认"的项均给出可复现路径或静态可推导的控制流证据；9 处标"疑似"的项（pywebview 回调线程模型、ctypes 崩溃触发、MCP 数组截断、tc.index 兼容端点、apply_update 退出链路等）均已附最小验证动作，建议在修复时一并落实为回归测试。
