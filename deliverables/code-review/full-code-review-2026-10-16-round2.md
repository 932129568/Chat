# GLM-Chat 全项目深度代码审查报告（第二轮，2026-10-16）

**审查日期**：2026-10-16
**审查范围**：`main.py`、`main_v1.0.0_legacy.py`、`backend/`（含新增 `fio.py`）、`frontend/src/`（36 个 .js）、`build.js`、`index.template.html`
**背景**：10-15 第一轮审查发现 78 项问题；10-16 凌晨代码被大量修改（修复第一轮发现）。本轮审查**当前代码状态**：验证修复正确性、发现修复新引入的缺陷与上轮遗漏。
**审查方式**：5 路并行逐行复审，对每处修复构造反例证伪。
**测试基线**：`pytest tests/ -q` → **347 passed**（较上轮 151 增加 196，修复带测试，只读审查未改码）

## 本轮结论摘要

- **第一轮主干修复绝大多数正确落地**：78 项中约 60 项经逐条核对确认修复正确无误伤（详单见文末「已验证修复清单」）。
- **新发现问题 63 项**：致命 0 / **严重 9** / 警告 25 / 建议 29。
- **最扎眼的形态**：① C1 进程保护修复只堵了"只传 pid"的常规路径，**伪造 name 与 taskkill 通配符两个绕过仍可击穿名单**；② update 的 `version` 字段在 sha256 强制化之后成为**唯一未消毒的攻击面**（路径遍历 + .bat 注入）；③ 前端修复"修了点、漏了对偶路径"（compactNow 修了但 archiveOldTasks 漏了）；④ 成本熔断被自己的压缩机制架空。

---

## 一、致命问题

**本轮无致命问题。**（第一轮两项致命 C1/C2 均已修复，但 C1 修复不完整——见 S2/S3。）

---

## 二、严重问题（9 项，建议发版前修复）

### S1. update 的 `version` 字段全程未消毒：路径遍历 + .bat 命令注入
- **位置**：`backend/services/update_service.py:132,152,199-224`；入口 `backend/api.py:441`
```python
tmp_path = os.path.join(UPDATE_DIR, 'glm-chat-%s.exe.tmp' % (version or 'new'))
...
script = (... 'copy /y "{new}" "{old}" ...').format(pid=pid, old=old_exe, new=new_exe, ...)
```
- **描述**：version 来自 manifest（网络）或 js_api 入参，无任何字符校验。三攻击面：① `version='..\..\x'` 路径遍历写出 UPDATE_DIR；② 含 `"` 闭合批处理引号注入命令；③ 含 `\r\n` 注入整行批处理 / 含 `%FOO%` 被展开。sha256 只管下载内容，管不到文件名/脚本插值这个元数据通道。
- **后果**：恶意/被劫持的 manifest 源可在用户点"立即更新"时以用户权限执行任意命令。
- **修复**：入口校验 `^[A-Za-z0-9._-]{1,32}$`；.bat 插值前断言路径不含 `"`、`\r`、`\n`、`%`。
- **置信度**：确认

### S2. kill_process：同时传 pid + 伪造 name，pid→name 归一化被完全架空（C1 修复绕过）
- **位置**：`backend/api.py:226-230`；`backend/services/process_service.py:134-139`
```python
if not detail['name'] and pid is not None:        # 只在 name 为空时才反查
    resolved = self._process.resolve_name_by_pid(pid)
```
- **描述**：schema 允许 pid/name 同传。传 `pid=<lsass 的 pid>, name='notepad.exe'`：api 层跳过反查，guard 校验伪造名，service 层同样跳过，`taskkill /PID <lsass> /F` 直指真实目标。确认弹窗展示的也是伪造名。
- **后果**：内置+用户进程名单可被伪造参数完全绕过，C1 修复形同虚设。
- **修复**：pid 非空时**无条件**以反查结果为权威；反查与传入 name 不一致即拒绝；反查失败 fail-closed 拒绝（同时修 S3 的 fail-open）。
- **置信度**：确认

### S3. kill_process name 通配符绕过：taskkill /IM 原生支持 `*`
- **位置**：`backend/services/process_service.py:146-149`；`backend/services/guard_service.py:184-197`
- **描述**：`taskkill /IM` 原生接受通配符，而名单只做精确包含/fnmatch 字面匹配。`kill_process(name='*')` 杀当前用户能杀的一切（含自身——自身保护只在 pid 路径）；`name='svchost*'` 杀所有 svchost 实例。
- **后果**：保护名单对按名强杀整体失效，批量终止进程致系统不稳定。
- **修复**：name 含 `*`/`?` 直接拒绝，提示先 list_processes 确认确切名；更稳：先 tasklist 枚举将命中的实际进程逐个过名单。
- **置信度**：确认（taskkill 通配语义为文档化行为）

### S4. stdio 防御性断开（超 8MB/队列满）后传输"半死"永不恢复
- **位置**：`backend/services/mcp_transport_stdio.py:130-146`；`backend/services/mcp_client.py:301-304`
- **描述**：W18 修复引入的主动 break 只退读线程，不杀子进程、不置 `_closed`。队列满时 EOF 哨兵 1 秒放弃；`is_alive()` 看 `proc.poll()` 仍存活 → dispatcher 0.5s 空转死循环；此后请求全走满 60s 超时；`_get_or_spawn` 永不触发重拉，该服务器瘫痪至 idle 600s 回收。
- **后果**：防 DoS 护栏本身制造持久可用性故障——流氓服务器一个超长帧瘫痪该 MCP 服务器 10 分钟。
- **修复**：主动 break 统一走断开设义（`_closed=True` + `proc.kill()`），或 `_reader_dead` 标志让 is_alive 返回 False 触发重拉。
- **置信度**：确认

### S5. archiveOldTasks 归档删除原文后不清已读去重集（S21 的对偶路径遗漏）
- **位置**：`frontend/src/97-compact.js:14` + `frontend/src/60-agent-loop.js:384-391`
- **描述**：compactNow 已修（清 `s._readKeys`），但每轮都可能触发的 `archiveOldTasks`（user 消息 >8 条）同样蒸发含文件原文的消息，却不清 `_readKeys`。归档占位语让 AI "重新 read_file"，去重器答"原文仍在上下文中，禁止重读"——两句都是谎言。
- **后果**：长会话后 AI 无法重读任何归档前文件 → 反复重试触发熔断，或凭记忆编造内容。
- **修复**：archiveOldTasks splice 成功后 `s._readKeys = []`；彻底方案是把 readFileSet 挂到 s 上。
- **置信度**：确认

### S6. shotState 卡在 'sending'：请求失败/abort 后截图永久失陷
- **位置**：`frontend/src/60-agent-loop.js:124-131,223-226`
- **描述**：`shotState='sending'` 只在收到 usage 帧时复位。HTTP 错误或 abort → catch 后永远停在 'sending'，此后 `pendingShots.length && shotState==='idle'` 恒假，截图不发送不清除无任何提示。
- **后果**：截图功能在当前会话静默报废，AI 永远"没收到图"。
- **修复**：catch 分支开头兜底 `if (shotState==='sending') shotState='idle';`。
- **置信度**：确认

### S7. 截断自动续跑的 350ms setTimeout 跨会话污染
- **位置**：`frontend/src/60-agent-loop.js:310`
- **描述**：截断 break → finally 复位 isStreaming → 用户 100ms 内切会话（switchSession 只挡 isStreaming 放行）→ 350ms 后定时器触发 `continueLastGeneration(旧s)`：后端 sid 被改指新会话、旧会话续写气泡渲染进新会话视图、旧会话被静默改写。
- **后果**：跨会话内容串扰 + 后端会话态错配。
- **修复**：`setTimeout(() => { if (currentSessionId !== s.id) return; continueLastGeneration(s, apiKey); }, 350);`
- **置信度**：确认

### S8. 预算硬停与 30 万提醒可被压缩/归档"洗白"（成本熔断架空）
- **位置**：`frontend/src/36-cost-defense.js:14-20` + `75-token-stat.js:6-23` + `97-compact.js:14,70-75`
- **描述**：`calcUsage` 只对 `s.messages` 现存 usage 求和；archive/compact 物理删除带 usage 的历史消息 → cost 回落到预算下，硬停永不触发。反例：预算 ¥0.5 花到 ¥0.6 暂停 → 触发 archive 或手动压缩 → 显示花费归零 → 继续烧。
- **后果**：R4 成本防御核心机制被自身压缩机制架空。
- **修复**：花费改会话级单调计数器 `s._spentCost`/`s._spentTokens`（写 usage 时累加，归档/compact 不清），硬停与提醒改读计数器。
- **置信度**：确认

### S9. addMessage 的 extra.usage 三字段未转义直拼 innerHTML（自定义端点可借此 XSS）
- **位置**：`frontend/src/50-markdown.js:72-76`
```js
extraHtml += `<div class="usage-info"><span>输入 <b>${u.prompt_tokens}</b></span>` + ...
```
- **描述**：usage 来自 API 响应（历史回放也走此路）。自定义 OpenAI 兼容端点时代，"API 响应"完全不可信：恶意端点返回 `{"usage":{"prompt_tokens":"<img src=x onerror=...>"}}` 即注入。pywebview 下 XSS = 全部 js_api 本地能力。
- **后果**：远程端点 → 本地任意代码执行通道。
- **修复**：三字段经 `escapeHtml(String(v ?? ''))`。
- **置信度**：确认（利用需恶意端点，故不定致命）

---

## 三、警告（25 项）

| # | 位置 | 问题 | 修法要点 |
|---|---|---|---|
| W1 | api.py:213 + guard_service.py:292 | clipboard_write confirm-token 摘要的 len 口径：Python 码点数 vs JS UTF-16 码元数，含 emoji 时确认后仍被拦（**严重疑似**，待前端验证） | detail 不绑 len 或后端按 utf-16-le 长度对齐 |
| W2 | fio.py:23,50 | os.replace 对"正被读取的目标文件"在 Windows 必 WinError 32 无重试（原子写新回归：偶发保存失败） | replace 重试 5 次退避；读路径加同一把锁 |
| W3 | api.py:162-168 | delete_path 护栏校验与执行两次取 current_sid，会话切换 TOCTOU 使名单与目标脱钩 | 复用第一次取的 sid |
| W4 | mcp_service.py:317-326 | MCP always 档"本会话不再提示"写入信任集却永不生效（guard 已修的同型遗漏） | 查信任不区分档位，或 always 档不登记 |
| W5 | mcp_config_service.py:227-267 | save/delete/set_tool_tier 先改内存、落盘失败不回滚，内存态与磁盘分裂 | 失败回滚内存态 |
| W6 | update_service.py:240-245 | apply_update 用 os._exit(0) 自杀绕过 atexit，MCP 子进程成孤儿残留 | Timer 回调先执行 mcp_shutdown 再退出 |
| W7 | cmd_service.py:269-278 | admin 临时文件名从 mkstemp 回退为 pid+毫秒，同毫秒并发互删对方文件（已修问题回潮） | 恢复 mkstemp 或加 secrets.token_hex |
| W8 | api.py:227-230 + process_service.py:136 | pid→name 反查失败时两层均 fail-open 放行 | 反查失败 fail-closed 拒绝并审计 |
| W9 | file_service.py:302-303 | search_replace 整读文件无大小上限（S7 只修了 read_file），2GB 日志即 OOM | 同口径 64MB 前置拦截 |
| W10 | clipboard_service.py:80-92 | set_clipboard 按 Python 码点数分配 UTF-16 缓冲，emoji 等 astral 字符静默截断 | 按 `data.encode('utf-16-le')` 实际字节数分配 |
| W11 | clipboard_service.py:52 | 剪贴板读对非 NUL 终止数据无界读，病态源程序可致越界读崩溃 | GlobalSize 限上界 + wstring_at 定长读 |
| W12 | file_service.py:16,254 | write_file 仍截断式直写（顶部 atomic_write_text 成死导入，佐证原计划接入） | 切换 atomic_write_text（参数逐字节一致） |
| W13 | cmd_service.py:287-315 | admin 固定 60s 轮询，超时后删除仍被提权进程占用的临时文件，TEMP 泄漏 | 超时分支延迟清理 + admin 加 timeout 参数 |
| W14 | mcp_transport_http.py:181-188 | SSE `_pop_event` 分隔符优先级错误：混合 EOL 流两事件被合并解析失败 | 取两个分隔符中位置更靠前者 |
| W15 | mcp_transport_http.py:166 | SSE 增量路径单个坏 data 帧杀死整个请求（与一次性路径 skip 坏帧行为不一致） | 捕获 HttpTransportError 记日志 continue |
| W16 | mcp_transport_http.py:211-214 | `_is_response_frame` 不匹配请求 id，陈旧/乱序帧误杀请求 | 匹配 id 或 id=None+error，不匹配帧跳过 |
| W17 | mcp_client.py:82,206-217 | `_reconnecting` 无锁，并发 404 双重握手或旁路请求误失败 | 锁内 check-and-set；等待者重连完成后重试 |
| W18 | update_service.py:87,133-148 | 下载 URL 无 scheme 白名单、无大小上限、跟随默认重定向，慢速流可写满磁盘 | https 白名单 + 500MB 硬上限 + 整体 deadline + 禁重定向 |
| W19 | mcp_service.py:578-584 | toolcache 写盘失败时超长输出完全不截断直接进上下文 | else 分支硬截断 + 告警 |
| W20 | 60-agent-loop.js:300-318 | 350ms 窗口内发新消息，截断续跑被 isStreaming 静默丢弃且无手动按钮兜底 | 拦截时补挂"继续输出"按钮 |
| W21 | 60-agent-loop.js:543-551 | abort 时 AI 气泡不清理：typing-dots 永久残留 / UI 与持久化历史分叉 | AbortError 分支清理或固化部分正文入 messages |
| W22 | 18-toast.js + 29-mcp.js 等 | uiPrompt/各面板模态未入确认队列：挂起的 uiConfirm 被兜底 deny（无提示），反向 uiPrompt 的 Promise 永不 settle（预算提高流程假死） | uiPrompt 复用队列；兜底取消时 toast 提示 |
| W23 | 62-mcp-exec.js:38,82 + 26-guard.js:85 | "本会话内不再提示"勾选无视 always 档位语义，always 被实质降级为 session（疑似，走向取决于后端） | verdict.tier==='always' 时不展示勾选框 |
| W24 | 65-session-store.js:42-48 + 85-session-mgmt.js:117 | 双源合并使"删除会话"在后端写失败时下次启动复活（修复引入的镜像缺陷） | 删除走专用后端接口 delete_session |
| W25 | 85-session-mgmt.js:8-12 | continueInNewSession 静默吞压缩失败照旧开新会话，用户丢失上下文无察觉 | catch 后 toast + 中止 |

## 四、建议（29 项，按模块一行一条）

**后端核心/update**：① fio 缺目录 fsync 且 `.glm_tmp_*` 残留无清理路径；② fio os.fdopen 自身抛错时 fd 泄漏（一行可修）；③ api.py kill_process 给 guard 文案二次追加"（保护名单）"重复后缀；④ guard 审计轮转与并发 append 有丢行窗口且只保留一代；⑤ update sentinel 写了没人读（失败静默）、.bak 下次启动无条件删除毁掉回滚保险；⑥ UPDATE_DIR 历史 .exe 永不清理；⑦ legacy 文件仍带 import 期副作用且内含全部已修旧 bug（建议移出包根或加导入护栏）；⑧ ConfigService.cwd 锁外赋值与锁内保存无原子性、set_workspace/set_ws_dir 口径不一；⑨ runtime._mark_bad 对瞬时 IO 错误无差别改名毁好文件（应仅 JSONDecodeError）；⑩ save_config 对"合法 JSON 但非对象"仍静默 ok:true；⑪ build_tools 的 mcp_tools 生成未包异常，脏 schema 可击穿 js_api 协议；⑫ StdioTransport.start 线程启动失败 kill 后未 wait/未关管道；⑬ bat 的 `tasklist | find "{pid}"` 子串匹配（1234 命中 12345）空转 30s。
**基础服务**：⑭ RunDeduper 对 admin/普通通道 key 域不同，换通道绕过写去重（有人审兜底）；⑮ append_file 被拒绝的尝试也计入限流窗口，触顶后自我锁死超时；⑯ toolcache 淘汰删文件与 read_more 并发读竞态产生无主文件。
**MCP**：⑰ `dpapi:` 前缀的合法明文值无法表示，被静默置空下发；⑱ call_tool 的 token 在 spawn 失败时被白消耗；⑲ _refresh_tools 持 entry 锁做 15s 阻塞网络 IO；⑳ mcp_config 结构异常分支无 .bad 备份即覆盖；㉑ import_claude 丢弃 plain_keys 提示；㉒ provider test_endpoint 读全量无上限、307/308 无人话；㉓ HTTP post 对请求返回 202 空体时静默得 None。
**前端**：㉔ finishReason 跨轮次残留 + 'length' 带 tool_calls 时截断参数靠正则猜；㉕ 97-compact.js:80 clear_caches 未接 .catch（85 已修此处漏）；㉖ thinking 400 降级重试不剥离 reasoning_effort；㉗ s.autoResume 成功后不清零终身累积；㉘ abort 占位工具结果污染成功率统计；㉙ mcpToggleServer 在途忽略点击致 checkbox 状态失步；㉚ MCP 编辑器切传输类型未清另一方残留键（疑似）；㉛ smartCmd 正则对无闭合引号超长输入 O(n²) 回溯；㉜ extra.images 仍未转义（上轮点名未修，当前靠 dataURL 巧合兜底）；㉝ renderSessionList 的 s.id 仍未转义拼 onclick（上轮点名未修）；㉞ maybeAutoCompact 在 compactHistory 缺失时返回 true 假成功；㉟ 右键"粘贴"死按钮（execCommand('paste') 无效，可改 navigator.clipboard）；㊶ index.template.html 无 CSP 纵深（建议 object-src 'none' 等渐进式）；㊲ 用户消息换行被 HTML 折叠（缺 white-space:pre-wrap）；㊳ 审计查看器 recycle==='false' 字符串比较布尔失效、data.total 未兜底显示 undefined；㊴ checkForUpdate 复查无更新时旧 pill 不回收；㊵ fetchGLMStream 重试 sleep 不响应 abort（停止延迟≤2s）；㊶ saveSessions 的 localStorage 写失败完全静默；㊷ build.js 只替换首个占位符且不校验 libs 四个文件存在性。

---

## 五、已验证修复清单（第一轮问题，本轮逐条核对修复正确，抽样 60 项）

**后端**：S1 日志早退（FileHandler 类型判定）✓；S2 admin 退出码（bat 逐行 echo）✓；S3 完成信号改 tmp_exit 可解析 ✓；S4 护栏武装+一次性 token（TTL+摘要绑定+用后销毁）✓；S5 删除根目录双侧 normcase ✓；S6 编码 lossy 拒写+预检 ✓；S7 read_file 64MB 预检 ✓；S8 配置全链路 fio 原子写 ✓；S10 toolcache OrderedDict+删盘+stale 清理 ✓；S11 超时 taskkill /T 杀树 ✓；C1 pid→name 反查链路已建（但不完整，见 S2/S3/W8）✓；C2 ctypes restype/argtypes 全补 ✓；W6 SetClipboardData 失败释放+全败报错 ✓；W3 指纹/限流/去重加锁 ✓；W9 CMD 脱字符剥离 ✓；W10 无名单操作 list 档降级 confirm ✓；W11 名单 pattern 归一化 ✓；W12 审计 10MB 轮转+流式读 ✓；W13 OEM 优先解码 ✓；W14 截图缩放+留存清理 ✓。
**MCP**：S12 _unwrap 先 error 后 id ✓；S13 404 递归守卫（单线程）✓；S14 SSE 增量读+watchdog ✓；S15 禁重定向（mcp+provider）✓；S16 tierOverrides 保留 ✓；S17 sha256 强制 ✓；W23 apply 前复核哈希 ✓；W19 expandvars 统一 ✓；W20 get_server 深拷贝 ✓；W21 解密失败置空+面板提示 ✓；W22 list_changed 去抖 ✓；⑭ stdio 写锁互斥 ✓；⑫ 协议头防覆盖 ✓；⑪ close 发 DELETE ✓；⑬ 启动失败 kill 子进程 ✓；.bat mbcs 编码中文路径 ✓。
**前端**：S18 setTimeout 350ms 续跑 ✓（引入 S7/W20）；S19 renderMd fail-closed ✓；S20 入口同步置 isStreaming ✓；S21 compactNow 清 _readKeys ✓（遗漏 archiveOldTasks → S5）；S22 uiConfirm 队列（证伪通过：真串行、fail-safe deny）✓；S23 _auditFilter 声明 ✓；S24 zip 流式解压 200MB 上限+白名单剔除 .env/.reg ✓；S25 多模态压缩分支上移 ✓；S26 normalizeSessions schema 归一 ✓（引入 W24）；W24 400 死分支 ✓；W25 content 字段 ✓；W26 mcpTrusted 切会话清空 ✓；W27 记忆增量追加 ✓；W28 scheduleRender WeakSet ✓；㊱ callApi 定时器清理 ✓；W29 密钥不再写 localStorage ✓；Esc 分层 ✓；右键 enabled ✓；build.js 产物语法校验+`</script>` 拦截 ✓；regenerate 全量回放 ✓。

---

## 六、审查总结

- **整体评分**：**82/100**（第一轮 68 → 本轮 82；修复质量高且带测试，但缺横向同型扫描）
- **主要风险**：进程保护名单仍有两个完整绕过（S2 伪造 name、S3 通配符）；update version 是 sha256 时代唯一未消毒的攻击面（S1）；stdio 半死状态让防 DoS 护栏反噬可用性（S4）；成本熔断被压缩机制架空（S8）。
- **优先修复 Top 8**：
  1. **S2+S3+W8** 一并修（kill_process 统一权威反查+拒通配符+fail-closed，约 1 天含测试）
  2. **S1** update version 白名单校验（半小时）
  3. **S9** usage 转义（10 分钟）
  4. **S4** stdio 断开语义（半天）
  5. **S5** archiveOldTasks 清 _readKeys（一行）
  6. **S6** shotState 失败复位（一行）
  7. **S7** 续跑定时器会话校验（一行）
  8. **S8** 会话级单调花费计数器（半天）
- **方法论建议（给维护者）**：本轮 63 项中约 1/3 是"修复了 A 路径漏了对偶路径 B"（compactNow/archiveOldTasks、85/97 的 catch、guard/MCP 的信任语义、read_file/search_replace 的上限）——建议每个修复落地前做一次同型代码全局搜索。
- **正向评价**：第一轮修复带 196 个新测试且主干零误伤；fio 原子写、护栏 token 化、ctypes 签名补全、SSE 增量读+禁重定向等修复工程质量在线。
