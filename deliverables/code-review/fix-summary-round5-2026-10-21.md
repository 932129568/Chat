# Harbor 第五轮全库扫描与修复汇总（2026-10-21）

> 前置：round4 修复（906ba1d）并入主线后，代码演进到 v1.7.0（历史存放自选目录/真删会话/导出对话框/W11 记忆结构化/F1 自反思环/readiness 评分/MCP TOFU+health/installer 打包链）。本轮 = 6 路并行逐行复审（backend 41 py + frontend 54 js + installer/ + tools/）→ 85 项去重后发现 → 6 批次修复 → 全量验证。
> 验证终态：**pytest 1083 passed / 1 skipped / 0 failed；check_contract PASS；前端重建 53 模块 14781 行**（唯一波折：SSRF 防护初版 DNS fail-closed 引发一次测试抖动，已改「解析失败放行」口径并复跑确认）。

## 发现总量与分级（去重后）

| 严重程度 | 数量 | 代表项 |
|---|---|---|
| 致命 | 2 | 安装器 GUI 桥未 JSON.parse（向导 100% 不可用）；记忆面板 memoryPanelInit 从未挂载（W11 功能完全不可达） |
| 严重 | 24 | 见下文分批次 |
| 警告 | 30 | last-wins 缺口/退场竞态/Esc 误 abort/锁外探测/样式冲突等 |
| 建议 | 29 | 硬编码毫秒/死常量/跨年时间口径/日志轮转等 |

## 分批次修复明细

### 批次 A：后端安全（plan/guard/api/config，15 项）
- **plan task_id 路径穿越（严重，三份报告共同指向）**：`_safe_tid` 白名单 `^[A-Za-z0-9_-]{1,64}$` 落在 `_task_path/_ckpt_path` 根因处，create/get/update/checkpoint_* 六个入口 + session_purge 全链路覆盖；删除前 realpath 包含校验。原可经 `session_purge(task_ids=['../../..'])` 任意删文件/目录。
- **grant fail-open（严重）**：`_effective_grant` 未映射 op（剪贴板读写/杀进程/截图/搜索/软件调用/MCP）不再被授权静默放行，回落 op 档确认（fail-closed）。
- **save_export_file 任意路径写（严重）**：pick_save_path 登记路径一次性消费，未登记路径拒绝 + audit。
- token detail 绑定补齐（mcp_call arguments 摘要 / software_call software+action / web_search query）；_params_dict 防畸形 JSON 穿透；sessions 路径族纳入 RLock；敏感目录名单按 SYSTEMROOT 动态生成；migrate 源取当前生效文件 + migrated_from 回显；delete_memory 损坏文件人话；session_purge 后 workspace 内存态收口；plan update 非法状态显式报错 + 损坏文件校验 + fio 原子写；checkpoint git 失败不再误报 snapshot 模式；bak 加毫秒戳；测试文件重复类定义清理。

### 批次 B：搜索/软件/混合（23 项）
- **software GUI 启动 cmdline 无引号转义（严重）**：改 `subprocess.list2cmdline`。
- **_call_uri 的 cmd /c start 元字符注入（严重）**：删 cmd 回退，改 ShellExecuteW（rc<=32 转错误）。
- **hybrid get_config NameError（严重）**：source 默认值前置，合法非 dict JSON 不再崩。
- **HTML 深嵌套 RecursionError（严重）**：parse_results/extract_main_content 外层防护，按「无结果」语义走 engine_retry。
- **SSRF 内网防护（严重）**：open_url/browser_open 加 `_is_public_host`（字面 IP 直判 + 解析私网拒绝；**解析失败放行**——初版 fail-closed 在 DNS 抖动时误杀正常搜索并引发测试 flaky，已修订）。
- extract=none/snippet 不再回传 extra.content（契约 + 缓存膨胀双修）；_tasks 32 条淘汰；takeover retries 计数后移 + 检查置位锁化；search_status unknown_task；_read_dom 僵尸线程记忆（_dom_pumpable）；loaded 先订阅后 load；local_proxy 断流即止（_write 返回 bool）+ 回环端口收敛 {11434,1234,8000,8080,1919}；探测移锁外；arg_schema 双层校验；argv 占位符 ⊆ properties；_fill_template KeyError → BAD_PARAMS；version 探测走沙箱限制；关键词词边界；路由日志 2MB 轮转；prompt manifest 穿越防护 + render 单遍替换；exit_code None 判 MALFORMED + 真实 FS 默认。

### 批次 C：MCP/记忆/更新/沙箱（12+2 项）
- **MCP stale 时钟基混用（严重）**：monotonic vs time.time 相差 16 亿秒致每次 call_tool 误触发 relist、工具从工具集闪断——调用点传 `now=time.monotonic()`，实证修复。
- warm 过期条目 pop_expired 显式 close（shutdown/热路径双覆盖）；TOFU 从「面板红字」升级为 call_tool/check_tool 真阻断 + ack 解除；idle 回收 status 复位 stale；alias 完整键消歧。
- memory 淘汰非 dict 崩溃修复 + 循环淘汰保指令类 + total 口径 + ts_iso 跨年比较；delete 方法自足（config_service 侧已接线）。
- update 清理保留已下载未应用包 + check 走 no_redirect/https-only；sandbox save_config 原子写；fio cleanup_stale_tmps 启动接线；另修 _idle_loop 测试注入裸 dict 的 KeyError。

### 批次 D：安装器（11 项）
- **GUI 桥返回值未 JSON.parse（致命）**：call 助手统一解析——原向导「安装」按钮永久禁用、进度页秒跳「安装完成」。
- **安装失败显示「✓ 安装完成」**：poll 分支判 res.ok===false → pageError。
- pywebviewready 等待；check_target 不再每次按键建目录；卸载目录解析链（--dir > Uninstall.exe 所在 > 注册表 > 默认）；**卸载器延迟自删**（detached PowerShell 等自身退出后 rmtree，解决映像锁）；install.json 接入定位链；CLI 引号 strip + 空值回落；**push_exe_tmp.py 硬编码 PAT 中和**（改环境变量 GITHUB_TOKEN，空值 exit 2）；gen_api_reference 副作用警告；KNOWN_ISSUES §20 改回 🔴（截图纯黑、GUI 运行时路径未验证）。

### 批次 E：前端核心（18 项）
- **catch 块越域引用 finished（严重）**：计划收尾块移入 try 内——原每次请求失败都二次抛 ReferenceError。
- **会话信任漏登后端（严重）**：勾选「不再提示」后 callApi('guard_session_trust')——原武装后端下全拒。
- **deleteSession 丢守卫（严重）**：恢复 stopPropagation + isStreaming 在途守卫。
- **session_purge taskIds 恒空（严重）**：plan.task_id 批准后落会话 + normalizeSessions 白名单放行——原计划/检查点永不真删。
- **历史目录面板样式三方冲突（严重）**：删动态样式 IIFE（模板官方样式已在位，含 4 个未定义变量致暗色不可读）。
- **记忆面板挂载（致命）**：110-boot loadAll 补 memoryPanelInit。
- **onboarding 早于数据加载（严重）**：移到 loadSessions/connectLoadFromConfig 之后；测试连接改真实 test_provider_endpoint 通道（原调不存在函数永远假成功）；预设表读真 PRESETS；跳过 Key 按钮应用本地预设 + 跳设置。
- **Esc 误 abort 流式（严重）**：浮层守卫（modalRoot 之外的 searchPanel/sc-mask/wsqMenu/ctxMenu/settingsPanel 打开时 Esc 不 abort）。
- 另有：shortcutsInit 双调用清理 + 幂等；模板重复 shortcutsBtn 删除；fx-off 令牌补全 + set-window/modal-card 停列；msg-time 等重复 CSS 清理；msgRecall isStreaming 守卫。

### 批次 F：前端面板（29 项）
- 63-search-panel：finally last-wins（seq 复检）；**接管非终态错误通知 Agent**（原挂起 Promise 永悬，用户 >10min 后点继续 = Agent 假死）；新搜索清洗接管区（取代语义 notify）；href scheme 白名单（javascript: RCE 面）；终态轮询不驱动就绪态；showTakeover 进 captcha 态；stats 序号/死常量/空 query/wire 幂等。
- 64-software-panel：**测试调用在途保护 + 定时器句柄覆盖泄漏**（旧 interval 永不清 + 新时钟被旧 finally 清掉）；未知 status 转义。
- 65-hybrid：readiness 死 id providerModel 修复 + 本地预设前置校验 + r.model 展示；NaN 输入校验回弹；hybridSave catch 回弹；readiness 序号。
- 67-plan-card：**rbTwice 三连点重复回滚**（执行分支即禁用）；**批准被 isStreaming 吞**（前置守卫）；allDefault 死参；三个 Show 在途保护（旧 Promise reject 不永久挂起）；300ms 令牌化；回滚结果精确匹配；files 死参删除。
- 69-memory-panel：**删除前重取 + 身份校验**（后端淘汰/去重致索引漂移删错条目）；信封错误显示；分级开关；确认文案 <br>。
- 29-mcp 删除独立 busy + 静默反馈；34-local-model 原型链防护 + 探测落盘；37-webdav 加载失败也建脏检查基线；38-ws-quick 退场竞态 + 委托 try/finally；72-shortcuts 幂等 + 转义；90-attachments 退场竞态 + null 守卫；95-compress 3s 兜底；27-update 轮询续试；16-panel-fx null 守卫。

## 验证

- `pytest tests/ -q`（Git Bash）：**1083 passed, 1 skipped, 0 failed**（skipped 为需真实 Ollama 的环境用例）
- `deliverables/design/check_contract.py`：PASS（js_api 差分零漂移 + UI 契约五大维度）
- 前端 `node frontend/build.js`：53 模块 → 14781 行，vm 沙箱测试全绿
- 安装器 `tests/test_installer.py`：13 passed（含 e2e 静默装卸）
- SSRF 修订后搜索子集复跑：127 passed

## 遗留（需真机/用户环境）

1. **PAT 吊销**：push_exe_tmp.py 曾含硬编码 GitHub PAT（从未入 git 历史，但随开发包分发过）——请到 GitHub Settings 吊销该 token，脚本已改环境变量。
2. **安装器 GUI 全链路**：桥 JSON.parse/错误页/自删已修，但「选目录→安装→立即运行→ARP 卸载」需交互式会话真机重走（本沙箱 WebView2 全黑，KNOWN_ISSUES §20 已记 🔴）。
3. 3 项前端疑似项（按钮文案回滚/mcpResBusyUri 连点/localLoadModels stale 复位）均有兜底，待真机观察。
4. exe 重打包 + 推送：待用户终端执行（本会话 git fetch/push 被代理损坏）。
