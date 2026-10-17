# GLM-Chat v1.0.0 产品与架构评审 + 重构方案设计

- 评审对象：`main.py`（1325 行，pywebview 5.4 后端）+ `glm-chat.html`（2401 行，前端单文件）
- 评审角色：产品评审员（gstack-product-reviewer），团队 gstack-glm-refactor
- 评审日期：2026-10-15
- 约束：只评审不改代码；保持 js_api 方法名契约不变；本次目标为「安全且收益大的最小可行重构」

---

## 0. 结论先行（TL;DR）

**一句话判断：v1.0.0 是一个功能野心很大、安全意识不低、但工程结构停留在「单文件脚本」阶段的产品。核心资产是 50 个 js_api 方法的稳定契约；核心负债是 1325 行单类 + 模块级全局状态 + 导入即启动导致的「零可测试性」。**

- 产品维度：功能完备度高（智能体闭环的克制与巧思都在），工程隐患集中在无测试/无日志/前端单文件/schema 双数据源漂移。
- 架构维度：`class Api`（L166-1237）一个类混合 8 类关注点；模块级可变全局 6 处；`except Exception: pass` 16 处；导入 main.py 即创建窗口并 `webview.start()`（L1247/1272/1326），**这是没有任何单元测试的根本原因**。
- 安全维度：文件工具有正经的路径 jail（`_resolve_ws` L188-207，设计良好）；但命令执行面、剪贴板面、截屏面完全没有护栏；`run_command`/`run_powershell` 连后端已有的 RunDeduper 都没接；`copy_into_ws` 的 name 参数未消毒，存在真实的路径穿越写入。
- 重构主张：**门面模式分层（backend/ 拆分 + Api 门面保持契约逐字不变）+ 先补黑盒契约测试安全网 + 顺手修 2 个 P0/P1 安全缺陷**。命令 allowlist、剪贴板/截屏确认等行为变更留给下个迭代做产品决策，本次不碰。

---

## 1. 产品维度评审

### 1.1 功能完备度：高（v1.0.0 作为智能体闭环已经够用）

后端公开方法约 50 个（即 50 个 js_api 调用面），覆盖：

| 域 | 方法 | 备注 |
|---|---|---|
| 配置 | get_config / save_config / get_sessions / save_sessions / get_memory / append_memory | config.json/sessions.json/memory.json 三存储，均在 ~/.glm-chat |
| 文件 | list_dir / read_file / write_file / append_file / search_replace / make_dir / delete_path / move_path / copy_path / get_file_info | 10 个，jail 内 |
| 命令 | run_command / run_powershell / run_admin_command | cmd/PowerShell/提权三档 |
| 剪贴板 | get_clipboard / set_clipboard | ctypes 直接调 Win32 |
| 进程 | list_processes / kill_process | tasklist/taskkill |
| 工作区 | set_workspace / get_cwd / set_session_ws / get_session_ws / get_effective_ws / set_ws_enabled / get_ws_enabled / get_ws_state / set_ws_dir / delete_session_ws / list_recent_ws / pick_folder / copy_into_ws / save_workspace_file / get_worklog / append_worklog | 16 个，全局+会话双模型 |
| 系统 | open_app / open_url / open_billing / take_screenshot / cache_tool_output / read_more / build_system_prompt / build_tools / get_api_info / rpc / clear_caches / set_current_sid | |

**值得肯定的产品克制（这些是深思熟虑过的，重构时不许丢）：**

1. **工具三档权限**：`build_tools(role)` 的 chat/ro/full 三档（main.py L1089-1236）+ 前端 toolMode 联动——纯聊天不发工具。
2. **工具路由省 token**：前端 `routeTools` 按任务域只下发相关工具（html L941/964-967）。
3. **写操作串行保护**：WRITE_SEQ_TOOLS 顺序执行（html L1245-1251），配合 system prompt 硬规则（main.py L1075-1076）。
4. **历史冻结式压缩 + 发送副本瘦身**（html L669-667 shrinkHistoryForApi / compactNow L1986）——缓存友好的压缩思路。
5. **截图 dHash 去重**（html L562-597）——避免重复截图烧 token。
6. **大输出 toolcache 落盘分页**（main.py L144-164/1049-1067）。
7. **append 频控**（10 分钟 6 次，main.py L444-457）、**write_file >20KB 强制走 search_replace**（L429-433）、**读文件指纹缓存**（L64-88/370-373）——都是防 AI 犯错的护栏。
8. **run_admin_command 的 MessageBox 人审**（L644-649）+ UAC 双重确认——方向正确。

### 1.2 用户体验与工程隐患

| # | 隐患 | 位置 | 严重度 |
|---|---|---|---|
| P-1 | 前端 2401 行单文件、L418 起一个巨型 `<script>`、78+ 顶层函数、约 15 个全局 `let`（html L421-430）；无模块化、无构建、无 lint、无 test、无 CI（开发说明.txt 只有 PyInstaller 命令） | glm-chat.html 全文 | 🔴 |
| P-2 | **工具 schema 双数据源且已漂移**：后端 build_tools（main.py L1082-1237）vs 前端硬编码 TOOLS（html L432-465）。前端版缺 clipboard/process/memory 工具，read_file 上限描述 2000 vs 后端 20000。后端 build_tools 失败时前端静默降级（html L1023 `catch {}`）——AI 悄悄丢能力，用户无感知 | 两侧 | 🔴 |
| P-3 | **后端零日志**：全文无 `logging` 使用；31 处 `except Exception as e` 只转 JSON error 字符串，无 traceback、无落盘。生产问题只能靠前端 alert（html L643）和「重新打包」提示（html L469-472）兜底，不可诊断 | main.py 全文 | 🔴 |
| P-4 | 16 处 `except Exception: pass` 静默吞错（L39/47/55/62/234/250/258/272/285/597/667/810/842/857/911/965）→ 用户侧表现为「功能神秘失效」（如 recent_ws 损坏后静默清空、ws_enabled 读取失败后静默全开） | main.py | 🟡 |
| P-5 | 错误返回协议不一致：`get_cwd` 返回裸字符串（L307）、`get_worklog`/`get_config` 返回裸文本，其余返回 JSON——前端必须分类处理，集成面脆弱 | main.py | 🟡 |
| P-6 | 命令去重逻辑前后端各一份（main.py L90-127 RunDeduper vs html L973-986 cmdDeduper），且**后端只在 run_admin_command 调用**（L641），run_command/run_powershell 根本没接 | 两侧 | 🟡 |
| P-7 | API Key 明文存 config.json（html L1458 保存、L2353 回填）。设置页有「仅保存在本机」知情提示（html L330），单用户桌面可接受，但报告在案 | html L330 | 🟢 |
| P-8 | 通知手段原始：alert()/confirm()（html 多处）；错误提示靠 AI 读 JSON error key 自愈 | html | 🟢 |

---

## 2. 架构维度评审（code smell 清单，带行号）

### 2.1 单类混合 8 类关注点

`class Api`（main.py **L166-1237**，75 个方法定义，约 50 个公开 js_api 方法）一个类承载：

| 关注点 | 行段 | 应属层 |
|---|---|---|
| 配置 IO | L252-305 | ConfigService |
| 文件操作 | L330-579 | FileService |
| 命令执行 | L581-674 | CmdService |
| 剪贴板 | L676-754 | ClipboardService |
| 进程管理 | L756-801 | ProcessService |
| 会话/工作区状态 | L803-921 | WorkspaceService |
| 截屏/杂项/日志 | L923-1067 | ScreenshotService/ToolcacheService |
| **工具 schema 数据** | L1082-1237 | tools_schema.py（纯数据） |

`build_tools` 把 150 行 JSON schema 字典硬编码在类里——每次改工具都要改这个 1300 行的类。

### 2.2 模块级可变全局状态（跨层耦合）

- `_SESSION_WS = {}`（L21）+ `_WS_LOCK`（L20）：会话→工作区映射。
- `_RT` 对象袋（L138-139）：`{'win','form','core','last_bounds','ws_enabled'}`。
- `_TOOLCACHE_MEM`（L146）、`_TOOL_SEQ`（L147）。
- `api = Api()`（L1247）、`window`（L1272）模块级单例。

Api 方法直接穿透访问全局袋：`_RT['ws_enabled']` 出现 7 次（L189/883/888/902/918/1090 + L54/61 存取函数），`_RT['win']` 由 app 层写（L1280）。**门面层知道运行时的全部秘密，任何 service 都无法独立测试。**

### 2.3 导入即启动 = 零可测试性（最重要的一条）

import `main.py` 会顺序执行：L134 建目录 → L141-142 加载工作区状态 → L1247 `api = Api()`（构造里读 config.json、建 workspace）→ L1270 写 api 日志 → L1272 `create_window` → **L1326 `webview.start()`**。意味着不可能 `import main` 做单元测试，只能整机跑 exe。**v1.0.0 没有任何自动化测试，这是结构性原因，不是团队懒。**

### 2.4 错误处理三轨制 + 静默吞错

- 16 处 `except Exception: pass`（行号见 1.2 P-4）；
- 31 处 `except Exception as e` → `json.dumps({'error': str(e)})`（可接受的 IPC 协议，但不落日志等于自断线索）；
- 若干裸字符串返回（get_cwd L307、get_worklog L959、get_config L253）与 JSON 协议混杂；
- `send2trash` 的 ImportError 走 L525-526，`os.replace` 失败走 L38-39——**安全相关的失败路径反而在静默降级**。

### 2.5 复制粘贴与重复定义

- 输出截断逻辑在 `run_command`（L602-605）与 `run_powershell`（L626-629）逐行复制；
- 命令去重前后端各一份（见 P-6）；
- 工具 schema 前后端各一份（见 P-2）。

### 2.6 命名不一致 + 契约三处漂移

- Python 方法 `get_clipboard`/`set_clipboard`（L697/712）vs schema 名 `clipboard_read`/`clipboard_write`（L1174-1180）；
- Python `append_memory(entry_json)`（L813）vs schema 参数 `content`（L1190-1193）；
- 全靠前端 dispatcher 遮盖：html L623-624（clipboard 改名）、L641（append_memory 转 JSON 串位置参数）。
**契约事实上有三份定义：Python 方法签名、后端 build_tools schema、前端 executeTool 适配表。改任何一份不同步另两份，线上就是「is not a function」。**

### 2.7 并发隐患

- `RunDeduper.check`（L109-124）无锁读写 `_last`/`_recent`——pywebview 多线程并发调用下竞态；
- `_RT['ws_enabled']` 无锁读写（L883/888 vs L883 自身）；
- `_TOOLCACHE_MEM` 借用 `_WS_LOCK`（L157）——锁名误导，实际是两不相关的东西共用一把锁；
- `_append_hist`（L174/449-451）无锁；
- config.json 读-改-写竞态（L261-277 save_config vs L241-250 _save_workspace），并发时可互相覆盖。

### 2.8 自省反噬

`get_api_info`（L315）与 `_write_api_log`（L1260）都靠 `dir(self)` 枚举公开方法——Api 表面任何变动会静默改变对外自省结果；同时 Api 实例挂着公开可变属性（L168-175：config_dir/config_path/cwd/file_fp/cmd_deduper），与 L137 注释「绝不挂到 Api 实例上（防 pywebview 遍历 CLR 崩溃）」**自相矛盾**——file_fp/cmd_deduper 是非可序列化对象挂在 js_api 实例上，这是 pywebview WebView2 桥接已知的雷区（v1.0.0 未炸属于幸运，重构应顺手私有化）。

---

## 3. 安全维度评审

**威胁模型先说清**：这不是一个假设攻击者的场景。智能体编码助手的内在信任链是「工作区内容 → AI 决策 → 本机用户权限执行」。提示注入（恶意 README、代码注释、依赖文档诱导 AI 调用工具）是真实攻击路径。判断标准：**AI 被劫持后，攻击者能拿走/破坏什么。**

### 3.1 命令执行面（风险最高）

| 项 | 事实 | 评级 |
|---|---|---|
| `run_command`（L582-588） | `subprocess.run('chcp 65001 >nul & ' + str(cmd), shell=True, cwd=root)`——任意 cmd 以当前用户完整权限执行，**无任何过滤、无去重、无频控**（cmd_deduper 全类只在 run_admin_command L641 被调用） | 🔴 |
| `run_powershell`（L614-622） | `-NoProfile -ExecutionPolicy Bypass -Command`——任意 PowerShell，同样裸奔 | 🔴 |
| jail 不覆盖命令 | `_resolve_ws` 只保护文件工具；命令的 `cwd=root` 不限制路径访问——`type %USERPROFILE%\.ssh\id_rsa`、`curl` 外传均不受阻 | 🔴 |
| RunDeduper 可绕过 | ① 只与「上一条完全相同」比较（L116），命令前加 `rem `、加个参数即过；② WRITE_VERBS 只查首 token（L114-115），`cmd /c del ...` 首 token 是 `cmd`，写命令重复拦截直接失效 | 🟡 |
| `open_app`（L984-999） | 绝对路径不进 jail，`os.startfile(path)` 可启动任意文件（.bat/.lnk 即点即执行） | 🟡 |
| `kill_process`（L785-801） | `taskkill /F /T` 无保护名单，可杀任意进程（含自身、安全软件进程） | 🟡 |
| `run_admin_command`（L638-674） | 有 MessageBox 人审（L644-649）+ UAC 双确认，**方向正确**；但：① 恒返回 `exit_code: 0`（L668/672），失败被掩盖；② ShellExecuteW 是异步的，60s 轮询超时后返回「命令已执行，输出读取超时」（L672）——命令可能还在跑，状态不确定；③ %TEMP% 固定名输出文件（L650）可被同机程序预判 | 🟡 |

**判断**：命令面目前完全依赖「AI 不学坏 + 工作区内容干净」。对个人本地工具这是可辩护的产品选择（用户自备 Key、自己负责），但评审意见必须记录在案，并作为 v1.1 的 P0 候选。

### 3.2 `_resolve_ws` 路径 jail（L188-207）：强点与弱点

**强点（设计得好，重构原样保留）：**
- 去引号 strip（L194）防 `"path"` 绕过；
- UNC `\\` 开头不 lstrip、盘符 `C:` 保留（L197）——两者最终都过不了前缀检查；
- `realpath` 先解析再 `normcase` 前缀比较（L201-203）——symlink/junction 逃逸在解析后即被拦截；
- `abs_root + os.sep` 防 `C:\ws` vs `C:\ws-evil` 前缀误判；
- `..` 经 realpath 逻辑归一，无法 climbs out。

**弱点：**
1. **只覆盖文件工具**（list_dir/read_file/write_file/append_file/search_replace/make_dir/delete/move/copy/get_file_info），命令面、截屏、剪贴板、进程面不在内（见 3.1）。
2. **`copy_into_ws`（L937-949）name 参数未消毒**：`name` 直接拼进目标路径（L944），`name="..\\..\\evil.exe"` 即跳出 attachments 目录写到任意位置。对比 `save_workspace_file`（L221）有 `re.sub(r'[\\/:*?<>|]', '_', ...)` 消毒——**同一文件两个函数两个标准，这是真实可用的路径穿越写入漏洞，定级 P0。**
3. TOCTOU：检查与使用之间可替换 symlink（本地单用户场景风险低，记录即可）。
4. `set_session_ws`/`set_ws_dir` 允许把「监狱的门」设到任意目录——设计如此（用户主动选目录），但配合 rpc（L318）意味着 AI 可先把全局工作区切到 `C:\` 再操作，「jail」形同虚设。**注意：这是设计意图与 AI 可调用性之间的张力，不是代码 bug。**

### 3.3 剪贴板 / 截屏权限面

- `get_clipboard`（L697-710）：读取全系统剪贴板（可能含密码、token），截断 30KB；`set_clipboard`（L712-754）：覆写剪贴板。两者对 AI 完全开放，**无用户确认环节**。
- **外传链完整存在**：`run_powershell` 可执行 `Invoke-WebRequest` + `get_clipboard` 内容 → 剪贴板里的任何秘密可被提示注入诱导外传。
- `take_screenshot`（L1016-1040）：`ImageGrab.grab(all_screens=True)` 全屏截取（含其他应用窗口，可能含隐私内容），base64 dataUrl 经前端（html L1029）作为 image_url **直接发送到智谱 API（open.bigmodel.cn）**——截图/剪贴板内容随对话出境。产品上有知情（设置页 Key 提示），但**无控制手段**（无「截屏前确认/脱敏」开关）。合规上值得在设置页明示。
- 落盘面：config.json（含 API Key）、sessions.json、memory.json、截图、worklog 全部明文在 `~/.glm-chat`（L23-26）。单用户桌面可接受，登记在案。

### 3.4 AdminCommand 确认机制评价

MessageBoxW（L644-649）展示完整命令文本 + 4 项按钮（是/否）+ UAC（L653 runas）——在桌面端这是**力所能及范围内较好的设计**。但必须指出两点：① 它只覆盖 admin 一条路径，`delete_path` 的永久删除、`kill_process /F` 等破坏性操作反而无人审；② 确认框防不住「看起来无害的命令」（被注入的 AI 会措辞），人审的有效性随命令复杂度衰减。**安全等级不一致是当前最大的架构级安全问题。**

### 3.5 安全修复清单（按优先级）

| 级别 | 问题 | 位置 | 修复方向 |
|---|---|---|---|
| **P0** | copy_into_ws name 未消毒，路径穿越写入 | main.py L937-949 | 复用 L221 的消毒正则 + 禁止 `..`；本次必修 |
| P1 | run_command/run_powershell 未接 RunDeduper（后端已有现成组件没用） | L582/614 | 接上 L641 同款 check；属行为变更（更严格），需产品决策——**列入可选** |
| P1 | run_admin_command 恒 exit_code 0 / 异步状态不明 | L668/672 | 透传真实退出码或明确标注「结果未知」 |
| P2 | 剪贴板读/截屏无确认 | L697/1016 | v1.1 候选：设置项「敏感操作前确认」 |
| P2 | kill_process 无保护名单 | L785 | system/csrss/explorer/自身 pid 黑名单 |
| P2 | delete_path 无 send2trash 时静默永久删除 | L525-530 | 返回中升级警示等级（已有 mode 文本，AI 侧易忽略） |

---

## 4. 重构方案

### 4.1 目标目录结构

```
GLM-Chat/
├── main.py                    # 极薄入口（<60 行）：只做装配 + 启动，无业务逻辑
├── glm-chat.html              # 前端（本阶段不动）
├── libs/
└── backend/
    ├── __init__.py
    ├── paths.py               # 路径常量与 frozen 判定（_CFG_DIR/_webview_data/get_html_path）
    ├── runtime.py             # _RT 收敛：RuntimeState（win/form/core/ws_enabled）+ 锁
    ├── errors.py              # ok()/err() 统一 JSON 协议（输出与现状逐字节一致）
    ├── api.py                 # Api 门面：50 个 js_api 公开方法签名不变，内部纯委托
    ├── services/
    │   ├── config_service.py      # config.json / sessions.json / memory.json
    │   ├── file_service.py        # 文件 10 件套 + FileFingerprintCache + _resolve_ws
    │   ├── cmd_service.py         # run_command/run_powershell/run_admin_command + RunDeduper + 截断
    │   ├── clipboard_service.py   # get/set clipboard（Win32 ctypes）
    │   ├── process_service.py     # list_processes/kill_process
    │   ├── workspace_service.py   # 会话工作区 16 件套 + recent + worklog + copy_into_ws/save_workspace_file
    │   ├── screenshot_service.py  # take_screenshot
    │   └── toolcache_service.py   # cache_tool_output/read_more + _cache_output
    └── tools_schema.py        # build_tools 唯一数据源（role→schema，纯函数无状态）
```

### 4.2 模块职责与方法清单

| 模块 | 职责（单一责任） | 方法 |
|---|---|---|
| `paths.py` | 所有路径常量与 PyInstaller frozen 适配 | `config_dir/config_path/recent_ws_file/session_ws_file/ws_enabled_file/toolcache_dir/webview_data_dir/get_html_path()` |
| `runtime.py` | 进程级可变状态的唯一所有者（win/form/core/ws_enabled） | `get/set_ws_enabled/snapshot()`，内部持锁 |
| `errors.py` | IPC 错误协议 | `ok(payload_dict)->str`、`err(msg)->str`（即 `json.dumps({'error': msg}, ensure_ascii=False)`） |
| `api.py` | **门面**：对外契约层，零业务逻辑，每个方法 ≤3 行（转调 service + 返回） | 现有 50 个公开方法，**签名与名字一个不改** |
| `config_service.py` | 三个 JSON 存储的读/合并/写 | `get/save_config/get/save_sessions/get/append_memory` |
| `file_service.py` | jail 内文件 CRUD + 指纹缓存 | `resolve_ws/list_dir/read_file/write_file/append_file/search_replace/make_dir/delete_path/move_path/copy_path/get_file_info/short_path` |
| `cmd_service.py` | 三类命令执行 + 去重 + 输出截断落盘 | `run_command/run_powershell/run_admin_command/check_dup` |
| `clipboard_service.py` | Win32 剪贴板读写 | `read/write` |
| `process_service.py` | 进程枚举与强杀 | `list/kill` |
| `workspace_service.py` | 全局+会话双模型工作区、recent、worklog、附件导入、原生选目录 | `set_workspace/save_ws_file/get_effective_root/set_session_ws/get_session_ws/set_ws_enabled/get_ws_enabled/get_ws_state/set_ws_dir/delete_session_ws/touch_recent/list_recent/pick_folder/copy_into_ws/save_workspace_file/get_worklog/append_worklog` |
| `screenshot_service.py` | 截屏 + base64 | `take_screenshot` |
| `toolcache_service.py` | 大输出落盘分页 | `cache/read_more` |
| `tools_schema.py` | build_tools 数据 | `build(role, ws_on)->str`（内容从 L1082-1237 逐字搬迁） |

**依赖方向**：api.py → services → (runtime/paths/errors)；service 之间不互相调用（workspace_service 被 file_service/cmd_service 需要的 `_effective_root` 通过构造注入的 `root_provider` 回调获取，避免循环依赖）。**explicit over clever：用显式构造注入，不用 service locator。**

### 4.3 js_api 契约约束（重构的生命线——违反即全线返工）

1. **方法名、参数个数、位置顺序、返回「JSON 字符串」的协议一个都不能变。** 前端 `callApi` 全部按位置传参（html L607-641），且按 `window.pywebview.api.<name>` 直调。改名/改参序/改返回类型 = 前端 dispatcher 50 处全改。
2. **适配层的三个「方言」必须原样保留**：`get_clipboard`/`set_clipboard`（schema 里叫 clipboard_read/write，main.py L1174-1180）、`append_memory` 位置参数传 JSON 串（L813 签名 vs L1190 schema 的 content）。这三个名字是契约的既成事实，**借重构「顺手改名」是被禁止的**。
3. **Api 门面保持「方法-only」表面**：不新增公开属性。现有 4 个公开可变属性（L168-175）下沉为私有或移入 service——消除 pywebview 桥接枚举非序列化成员的潜在崩溃面。
4. `rpc`（L318）通用分发保留（前端极少用，但属公开契约）。
5. `get_api_info`/`_write_api_log` 依赖 `dir()` 自省——保持 Api 公开方法集合不变，日志内容即不变。
6. `_RT['win']` 写入与 `window.events.loaded` 装配留在 main.py 入口，不动。
7. `build_tools` 的**文案内容逐字搬迁不改写**（AI 已适配 v1.0.0 措辞，改文案 = 行为漂移，需单独评估）。

### 4.4 明确不建议动的部分

| 部分 | 理由 |
|---|---|
| PyInstaller 打包命令与 `--add-data "glm-chat.html;." "libs;libs"` 布局（开发说明.txt L15/18） | backend/ 是常规纯 Python 包，PyInstaller 自动收集 hidden import 风险为零（无动态 import，除 L521 send2trash 可缺省）；打包流程零改动 |
| 前端 glm-chat.html | 契约不变 → 前端零改动。前端拆分是独立项目，另立迭代 |
| `_resolve_ws` 判定算法（L188-207） | 安全关键且现状正确，只补测试不改逻辑（copy_into_ws 消毒属修 bug，除外） |
| send2trash 可选依赖行为 | 产品行为，保留 |
| 工具 schema 语义与文案 | 见 4.3-7 |

### 4.5 分级重构清单

**低风险（行为逐字节不变，纯搬运 + 机械化）：**
- L1：抽 `paths.py`（常量 + get_html_path）。
- L2：抽 `runtime.py`（_RT dict 的 key 不改，加锁收敛）。
- L3：`errors.py` 统一 ok()/err()，所有返回路径改走它——**用快照测试保证输出字符串逐字节一致**。
- L4：`FileFingerprintCache`/`RunDeduper`/`_decode_bytes`/截断辅助 原位搬进 services 模块。
- L5：`build_tools` 内容搬 `tools_schema.py`，`build(role, ws_on)` 纯函数化（ws_on 由 Api 传入，不再内部摸 `_RT`）。

**中风险（外部行为等价，但触及并发/状态所有权，需快照+定向测试）：**
- M1：`_SESSION_WS`/`_TOOLCACHE_MEM`/`_append_hist`/`ws_enabled` 收进 service 实例，统一锁策略（修 2.7 全部并发项）。
- M2：Api 门面化 + 8 个 service 拆分——重构主体。
- M3：Api 公开属性私有化（L168-175）。
- M4：**P0 安全修复：copy_into_ws name 消毒**（向后兼容：只挡穿越路径）。
- M5：run_admin_command 真实退出码/状态标注（修 3.5-P1，返回值形态微调——属行为变更，**需产品决策后单独提交**）。
- M6：（可选）run_command/run_powershell 补接 RunDeduper——行为变更（重复命令会被拒），**与 M5 同批决策**。

**高风险（本次不做，记录为 v1.1 候选）：**
- H1：命令执行 allowlist/工作目录强制/频控。
- H2：剪贴板读、截屏前用户确认 + 设置项。
- H3：kill_process 保护名单。
- H4：前端 TOOLS 删除、全面只信后端 schema（消双数据源，需与 M2 联调）。
- H5：引入 logging 框架 + 错误协议 JSON 化（前端同步改）。
- H6：前端模块化拆分。

### 4.6 分步实施顺序（每步可独立验证）

| 步骤 | 内容 | 独立验证方法 |
|---|---|---|
| **Step 0** | **契约测试安全网**：`tests/test_api_contract.py`，不起窗口，`Api()` 构造注入临时 workspace（monkeypatch paths），对 50 个方法各录 1-2 个典型调用的返回快照（subprocess/ctypes/PIL/shutil 全部打桩），`build_tools` 三种 role 输出全文 diff 为零 | `pytest` 全绿；**此步不绿不进 Step 1** |
| Step 1 | L1+L2：paths.py + runtime.py | python main.py 冒烟（起窗即关）+ 快照测试全绿 |
| Step 2 | L3：errors.py 统一返回 | 快照 diff 为零 + 冒烟 |
| Step 3 | L4：utility 类/函数搬迁 | 快照 + py_compile |
| Step 4 | M2 前半：config/file 两个 service + Api 门面对应方法委托 | 快照 + 手动走查（设置页保存/读文件/写文件） |
| Step 5 | M2 后半：cmd/clipboard/process/workspace/screenshot/toolcache 六个 service | 快照 + 手动走查（每个工具至少一次真实调用） |
| Step 6 | M1：状态收编 + 锁统一 | 快照 + 冒烟 |
| Step 7 | L5+M4：tools_schema.py + copy_into_ws 消毒 | build_tools 输出 diff 必须**为零**；copy_into_ws 定向测试 3 例 |
| Step 8 | main.py 入口瘦身 + api.py 定稿 | PyInstaller onefile 构建 + exe 冒烟（打包命令不变） |
| Step 9 | M3：公开属性私有化 | get_api_info 方法列表 diff + 快照 |

---

## 5. 最小可行重构范围（本次 = 安全且收益大，控制范围）

**定义：只做「行为可证明不变 + 修复已确认缺陷」的重构。任何需要产品决策的行为变更，划出范围。**

### 本次做（MUST）

| # | 项 | 来源 | 为什么值得 |
|---|---|---|---|
| 1 | Step 0 契约快照测试 | 架构 2.3 | 没有它，后面 9 步全是赌。这是本次最重要的交付物 |
| 2 | Step 1-3（paths/runtime/errors） | 架构 2.2/2.4 | 纯搬运、零行为变化、立刻让 main.py 可被 import |
| 3 | Step 4-5（Api 门面 + 8 services） | 架构 2.1 | 重构主体收益：可测试、可定位、改一个工具不再动 1300 行类 |
| 4 | Step 6（状态收编 + 锁统一） | 架构 2.7 | 修并发隐患，外部行为不变 |
| 5 | Step 7-L5（tools_schema 单文件） | 产品 P-2 | schema 从「类里 150 行」变独立数据文件，diff 可审 |
| 6 | Step 7-M4（copy_into_ws 消毒） | 安全 P0 | 已确认的路径穿越写入漏洞，修复向后兼容 |
| 7 | Step 8-9（入口瘦身 + 属性私有化） | 架构 2.8 | 收尾：消除 pywebview 桥接潜在雷区 |

### 本次不做（明确划界，防止范围蔓延）

- run_admin 退出码修正（M5）、命令去重补接（M6）——**行为变更，需 team-lead 与用户确认后单独提交**；
- 3.5 表中 P2 及以下全部（剪贴板/截屏确认、kill 保护名单、永久删除警示）；
- 前端任何改动（glm-chat.html 一个字节不动——这是契约不变的红线证明）；
- 打包命令/发布流程任何改动；
- logging 框架、错误协议 JSON 化、schema 文案改写。

**范围判据（Kill criteria）**：若 Step 0 契约测试两周内无法对 50 个方法达到 80% 快照覆盖，立即收缩为「只做 Step 1-3 + M4」，放弃 service 拆分——即最小重构退化为「可 import + 修 P0」，也比带着侥幸心理大拆好。

### 验证方案（每步复用）

1. `python -m py_compile main.py backend/**/*.py`；
2. `pytest tests/ -q`（Step 0 产出的快照，行为守门员）；
3. `build_tools` 输出与 v1.0.0 产物的 `diff` 必须为空；
4. `python main.py` 冒烟：起窗 → 设置 Key → 发消息 → 走一遍文件/命令/截屏工具 → 关窗；
5. PyInstaller onefile（开发说明.txt 原命令）构建 + exe 冒烟。

---

## 6. 总体结论

- **产品判断**：GLM-Chat 的 v1.0.0 在「AI 桌面智能体」这个品类里功能密度很高，护栏设计（三档权限、串行写、频控、去重、人审）体现了真实的使用经验。主要欠账在工程质量：无测试、无日志、双数据源、单文件前端。
- **架构判断**：分层重构的路径清晰、契约边界明确（50 个 js_api 方法名不变 → 前端零改动 → 重构风险被压到「快照测试能守住的范围内」。
- **安全判断**：`_resolve_ws` 是合格的 jail；最大缺口是命令/剪贴板/截屏三面无护栏 + `copy_into_ws` 一个可立即利用的路径穿越。**P0（copy_into_ws 消毒）建议随本次重构带上，其余安全增强留给 v1.1 做产品决策。**
- **给 team-lead 的执行建议**：任务 #2（重构）严格按 4.6 的 Step 0-9 顺序执行，Step 0 未绿不动 Step 1；任务 #3（QA）以快照测试 + 手动工具走查为回归基线。

---

*评审报告完。评审员：gstack-product-reviewer。本报告只作评审与方案，未改动任何项目代码文件。*




