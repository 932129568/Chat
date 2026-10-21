# Harbor macOS 内置 AI 浏览器 · 开发方案（v1.9.0「Mac 版」）

**日期**：2026-10-21
**类型**：技术选型 + 架构设计 + AI 驱动集成 + macOS 适配 + 100 批次实施计划
**基线**：v1.8.0 迭代方案（Windows 搜索浏览器四件套已落地：search_browser/search_adapters/search_extract/search_service + browser_search/browser_open/browser_takeover js_api）
**状态**：v1.0（待技术负责人审定）

---

## 📌 TL;DR

- **一句话**：把已验证的 Windows 搜索浏览器泛化为**跨平台 AI 驱动浏览器模块**（`backend/services/browser/`），新增 macOS WKWebView 后端（PyObjC），Agent 经「导航/等待/提取/交互」四原语直接驱动；同步移植 macOS 平台服务（Keychain 替代 DPAPI、Seatbelt 替代 Job Object、CG 截屏、废纸篓、`~/Library/Application Support` 路径），并以 .app + 签名 + 公证 + DMG 完成分发闭环。
- **关键技术判断**：① pywebview 在 macOS 走 Cocoa/WKWebView（PyObjC 9.x），与 Windows EdgeChromium 同 API 面——**抽象层只包「会话/等待/提取」三件套，平台差异关进两个后端**；② 提取通道继续走 **js_api 回调**（Windows WebView2 的 execute 受 CSP unsafe-eval 约束，macOS WKWebView 的 evaluateJavaScript 是原生 API 不受页面 CSP 约束——但回调是唯一两平台都安全的公约数）；③ macOS 沙箱用 **sandbox-exec（Seatbelt SBPL）**，默认拒绝+白名单，且**子进程树继承策略**——文件系统/网络隔离比 Windows Job Object 更强（Job 不管文件和网络）；④ 打包必须过 **codesign（由内而外签每个 Mach-O）+ notarization（ZIP 提交+stapler）+ DMG**，$99/年开发者账号是硬成本。
- **总量**：100 个工作包（10 里程碑），预估 **42-48 人日**（含 macOS 真机验证窗口）；关键路径 = 平台抽象层 → macOS 浏览器后端 → 平台服务移植 → 打包公证。

---

## 1. 技术选型

| 方案 | 评估 | 结论 |
|---|---|---|
| **pywebview + WKWebView（PyObjC）** | 与 Windows 端同 API 面（create_window/load_url/evaluate_js/js_api）；零打包浏览器内核（.app 仅 +40MB PyObjC）；系统 WebKit 随 OS 更新 | **选定**。抽象层两后端（win/mac），headless 兜底 |
| 内嵌 Chromium（CEF/Electron） | 违背「零依赖/小体积」铁律；CEF 授权与打包复杂度高 | 弃选 |
| 纯 HTTP 抓取（无渲染） | 无法驱动需要 JS 的站点；丢失「浏览器」本质 | 仅作 CI/无显示环境的兜底后端 |
| 原生 Swift/AppKit 重写 | 双代码库维护，违背单 Python 代码库策略 | 弃选 |

**PyObjC 依赖面**（macOS 专属，按 extras 隔离安装，Windows 端零感知）：pyobjc-core、pyobjc-framework-Cocoa、Quartz、WebKit、Security、UniformTypeIdentifiers（≥9.0）。

---

## 2. 系统架构

```
┌─────────────────────────────────────────────┐
│ Agent 工具面（AI 驱动层）                     │
│  browser_navigate / browser_wait / browser_extract │
│  browser_click / browser_fill / browser_screenshot │
│  guard 三档 + 沙箱 + 审计 + trace_id           │
├─────────────────────────────────────────────┤
│ BrowserService（会话编排）                     │
│  会话生命周期 / 等待策略（选择器+DOM 稳定）/    │
│  提取管线（js_api 回调 → dual-LLM-lite 读取器） │
│  反爬检测 / 人工接管 / 缓存（TTL 分级）          │
├──────────────┬──────────────┬────────────────┤
│ BrowserSession│ BrowserSession│ HeadlessSession│
│ (Win/WebView2)│ (Mac/WKWebView)│ (urllib 兜底)  │
│ edgechromium  │ cocoa+PyObjC  │                │
├──────────────┴──────────────┴────────────────┤
│ 平台服务抽象层（PlatformServices）             │
│  Secrets: DPAPI(win) / Keychain(mac)          │
│  Sandbox: JobObject(win) / Seatbelt(mac)      │
│  Screen: ImageGrab(win) / CGDisplay(mac)      │
│  Trash:  send2trash(win) / NSFileManager(mac) │
│  Paths:   ~/.glm-chat(win) / ~/Library/App    │
└─────────────────────────────────────────────┘
```

**目录结构**（新增 `backend/services/browser/` 包，Windows 现有四件套迁入）：

```
backend/services/browser/
  __init__.py          # 平台探测 + 后端选择（win/mac/headless）
  session_base.py      # BrowserSession 抽象基类 + 等待/提取骨架
  session_win.py       # WebView2 后端（自 search_browser.py 迁入泛化）
  session_mac.py       # WKWebView/PyObjC 后端（新增）
  session_headless.py  # urllib + adapters 兜底（CI/无显示）
  service.py           # BrowserService（自 search_service.py 扩为通用）
  adapters/            # 引擎适配器（自 search_adapters.py 迁入）
  extract.py           # 正文提取（自 search_extract.py 迁入）
```

---

## 3. AI 驱动集成方式

### 3.1 工具面（6 个新 js_api，全进 `_V12_EXTRA`）

| 工具 | 参数 | guard 档 | 说明 |
|---|---|---|---|
| `browser_navigate` | url, wait_selector?, timeout | session | 导航+等待就绪；回 page_title/url |
| `browser_extract` | selector? / mode(snippet\|full) | session | 提取结构化结果（markdown+links） |
| `browser_click` | selector / text | always | 点击元素（写操作，截图确认前后态） |
| `browser_fill` | selector, text | always | 表单填写（敏感字段走 guard） |
| `browser_screenshot` | full_page? | session | 页面截图（复用截屏管线） |
| `browser_close` | session_id | — | 关闭会话 |

### 3.2 提取通道（跨平台安全公约数）

```
Agent → browser_extract
  → 页面 JS 采集（querySelectorAll + 序列化）
  → window.pywebview.api.on_extract(json) 回调   ← 两平台都不受页面 CSP 约束
  → dual-LLM-lite：本地模型解析为结构化结果（schema 约束，无指令权）
  → provenance 包裹（来源 URL + 「UNTRUSTED DATA」标记）后进主模型上下文
```

**macOS 特有说明**：WKWebView 的 `evaluateJavaScript:completionHandler:` 是原生 API 不受页面 CSP 约束；但 Windows WebView2 的 ExecuteScript **受** unsafe-eval 约束——回调是唯一双平台安全通道，架构上不搞平台分歧。

### 3.3 等待策略（三保险，抗 SPA）

1. `wait_selector`（显式选择器，≤8s）
2. DOM 稳定性（innerText 长度三连稳 ×500ms）
3. 硬超时兜底 + 输出校验（拒含 "loading" 的残留，重试一次）

---

## 4. macOS 兼容性策略

### 4.1 平台服务映射（PlatformServices 抽象）

| 能力 | Windows 现状 | macOS 方案 | 迁移风险 |
|---|---|---|---|
| 密钥存储 | DPAPI（ctypes crypt32） | **Keychain C API via ctypes**（SecKeychainAddGenericPassword/FindGenericPassword） | Tahoe 26.x 的 `security` CLI 已坏（挂起/exit 36）——**必须走 C API 不走 CLI**；打包应用以自身 bundle-id 获得稳定 ACL；SSH 会话需 GUI 上下文（errSecInteractionNotAllowed）——首次写入引导用户在桌面会话完成 |
| 沙箱 | Job Object | **sandbox-exec + SBPL**（deny default；放行系统读/工作区读写/网络策略 none\|loopback\|full） | SBPL 配置错误会误伤合法请求——每平台一套最小 profile + 自检（尝试违规操作验证被拦）；macOS 无 rlimit 硬限制（pre_exec 的 fork 在多线程进程有险）——资源限制降级为「监控+告警」并文档化 |
| 截屏 | PIL.ImageGrab | screencapture CLI / CGDisplayCreateImage via Quartz | 权限弹窗（Screen Recording）需引导；TCC 权限在 .app 打包后才稳定 |
| 废纸篓 | send2trash | NSFileManager trashItemAtURL（PyObjC）或 `osascript` | 无 |
| 数据目录 | `~/.glm-chat` | **`~/Library/Application Support/Harbor`**（macOS 规范） | 旧版无 Mac 版，无迁移负担；Windows 路径不动（CONFIG_DIR_NAME 红线） |
| 更新 | .bat 自替换 | .app 内替换 + 重新签名提示（未签名 app 更新后 Gatekeeper 报警） | 公证后的 app 内二进制替换会破坏签名——更新策略改为「整包 .app 替换 + 提示重新允许」 |

### 4.2 打包与分发链

```
PyInstaller --windowed → Harbor.app（Info.plist: CFBundleShortVersionString/
  NSHighResolutionCapable/NSSupportsAutomaticGraphicsSwitching）
  → codesign 由内而外（find Mach-O → 逐个 --options=runtime → 整体签）
  → ditto -c -k ZIP → xcrun notarytool submit --wait → xcrun stapler
  → create-dmg / hdiutil → Harbor-<ver>.dmg（拖拽安装体验）
```

---

## 5. 性能优化策略

| 场景 | 策略 |
|---|---|
| 浏览器会话冷启 | 会话池预热（首个导航前 500ms 建窗）；空闲 60s 回收 |
| 多标签/多会话 | 单 WKWebView 进程模型天然多进程（WebKit 进程池），单会话内存 ~80-150MB；上限 3 并发会话 |
| 提取带宽 | js_api 回调只回传序列化结果（不回整页 HTML）；adapter 版本入缓存键；RSS 优先（4KB vs 100KB） |
| Retina/外接显示器 | hidpi 缩放由 WKWebView 原生处理；截图按 point 坐标（非 pixel）避免 2x 偏移 |
| Apple Silicon | PyObjC 9.x 原生 arm64；PyInstaller 目标架构按构建机（CI 用 arm64 runner） |
| 内存基线 | 启动常驻 <150MB（对齐 v1.8 竞品基线）；浏览器会话按需装卸 |

---

## 6. 100 批次实施计划（10 里程碑 × 10 包）

> 每包：编号 / 任务 / 交付物 / 依赖。P0 不可裁剪，P1 尽力，P2 可砍。

### M0 · 平台抽象层（W1，10 包，P0）

| # | 任务 | 交付物 | 依赖 |
|---|---|---|---|
| 0.1 | 建 `browser/` 包 + `__init__.py` 平台探测（sys.platform → win/mac/headless） | 包骨架 | — |
| 0.2 | `session_base.py`：BrowserSession 抽象（navigate/wait/extract/screenshot/close 签名 + 超时/错误 taxonomy） | 基类 | 0.1 |
| 0.3 | `PlatformServices` 抽象（Secrets/Sandbox/Screen/Trash/Paths 五接口） | 抽象 | 0.1 |
| 0.4 | Windows 平台服务实现落地（DPAPI/JobObject/ImageGrab/send2trash 包适配器） | win impl | 0.3 |
| 0.5 | 搜索四件套迁入 browser/ 包（search_browser→session_win，search_service→service） | 迁移 | 0.2/0.4 |
| 0.6 | 迁移回归：既有 browser_search/browser_open 测试全绿 | 测试 | 0.5 |
| 0.7 | `__init__.py` 导出 + api.py import 路径更新 | 接线 | 0.5 |
| 0.8 | 会话状态机设计文档（created→navigating→ready→extracting→closed） | 文档 | 0.2 |
| 0.9 | headless 后端骨架（urllib + adapter 复用） | 后端 | 0.2 |
| 0.10 | M0 出口：全量测试 + 契约差分 + 构建幂等 | 门禁 | 0.1-0.9 |

### M1 · macOS 浏览器后端（W1-W2，15 包，P0）

| # | 任务 | 交付物 | 依赖 |
|---|---|---|---|
| 1.1 | PyObjC 环境隔离安装方案（extras: pywebview[cocoa]；Windows 端不装） | 依赖声明 | 0.1 |
| 1.2 | `session_mac.py`：NSWindow + WKWebView 创建（PyObjC 桥） | 后端 | 0.2/1.1 |
| 1.3 | WKWebViewConfiguration：独立 data store（会话 cookie 隔离）+ jsBridge 注册 | 后端 | 1.2 |
| 1.4 | load_url + 导航委托（didFinishNavigation/didFail） | 后端 | 1.2 |
| 1.5 | evaluateJavaScript 等待原语（选择器轮询 + DOM 稳定） | 后端 | 1.4 |
| 1.6 | js_api 提取桥（on_extract 回调 + 主线程派发） | 后端 | 1.3 |
| 1.7 | 页面截图（WKWebView takeSnapshotWithCompletionHandler） | 后端 | 1.4 |
| 1.8 | click/fill 原语（evaluateJavaScript 派发 + 前后态截图） | 后端 | 1.5 |
| 1.9 | 下载拦截（默认禁；ALLOW_DOWNLOADS=False 语义对齐） | 后端 | 1.2 |
| 1.10 | 外链策略（target=_blank → 系统浏览器） | 后端 | 1.2 |
| 1.11 | 会话池（预热/空闲 60s 回收/上限 3） | 后端 | 1.2 |
| 1.12 | headless 后端完整化（urllib 抓取 + adapter 解析 + 超时） | 后端 | 0.9 |
| 1.13 | 后端选择逻辑（无显示环境自动降级 headless + 日志） | 后端 | 1.12 |
| 1.14 | macOS 后端冒烟（CI 无显示→headless；Mac 真机→WKWebView） | 冒烟 | 1.2-1.12 |
| 1.15 | M1 出口：三后端一致性 fixture 测试（同 HTML → 同结构化输出） | 门禁 | 1.13 |

### M2 · AI 驱动工具面（W2-W3，15 包，P0）

| # | 任务 | 交付物 | 依赖 |
|---|---|---|---|
| 2.1 | 6 个 js_api 定义（navigate/extract/click/fill/screenshot/close）+ _V12_EXTRA | 接口 | 0.7 |
| 2.2 | guard 矩阵接线（click/fill=always，其余 session）+ token 透传 | 安全 | 2.1 |
| 2.3 | 工具 schema（strict：additionalProperties:false + enum + required） | schema | 2.1 |
| 2.4 | 服务端校验（schema 双门 + isError 回传 + 重试上限 1） | 校验 | 2.3 |
| 2.5 | dual-LLM-lite 读取器（本地模型解析原始→结构化 JSON，无指令权） | AI | 1.6 |
| 2.6 | provenance 包裹（来源 URL + UNTRUSTED DATA 标记） | 安全 | 2.5 |
| 2.7 | 等待策略三保险落地（选择器/DOM 稳定/硬超时+输出校验） | 引擎 | 1.5 |
| 2.8 | 反爬检测（验证码特征 → browser_takeover 人工接管） | 引擎 | 1.4 |
| 2.9 | 缓存分级 TTL（新闻 5min/通用 1h/百科 24h）+ URL 归一化 + 适配器版本入键 | 缓存 | 0.9 |
| 2.10 | 工具描述三段式（触发/语义/排除）+ consolidate 检查 lint | 提示词 | 2.3 |
| 2.11 | EFFICIENCY_PROMPT 增浏览器工具铁律（先 extract 后 click；禁循环刷新） | 提示词 | 2.10 |
| 2.12 | AGENTS.md 最小可运行示例（降低「JSON 跑不起来」工单） | 文档 | 2.1 |
| 2.13 | trace_id 贯穿（navigate→extract→审计） | 可观测 | 2.1 |
| 2.14 | 前端工具分发（25-tool-exec 新分支 + agentGuardCheck 复刻） | 前端 | 2.2 |
| 2.15 | M2 出口：注入 fixture（毒网页零触发）+ 全量门禁 | 门禁 | 2.1-2.14 |

### M3 · macOS 平台服务移植（W3-W4，15 包，P0）

| # | 任务 | 交付物 | 依赖 |
|---|---|---|---|
| 3.1 | macOS Keychain 服务（ctypes Security C API：add/find/delete） | secrets | 0.3 |
| 3.2 | Secrets 抽象切换（DPAPI↔Keychain 按平台；迁移工具：Windows 已有 DPAPI 值不动） | secrets | 3.1 |
| 3.3 | Keychain 边界测试（GUI 会话依赖/ACL/ Tahoe CLI 坏绕验证） | 测试 | 3.1 |
| 3.4 | sandbox-exec 后端（SBPL 生成器：deny default + 白名单模板） | sandbox | 0.3 |
| 3.5 | SBPL 最小 profile（系统读/工作区读写/网络策略 none-loopback-full） | sandbox | 3.4 |
| 3.6 | 沙箱自检（尝试违规读写/网络 → 验证被拦；airlock 模式） | 测试 | 3.5 |
| 3.7 | 子进程树继承验证（sh -c 嵌套逃逸测试） | 测试 | 3.5 |
| 3.8 | 截屏服务 macOS 后端（CGDisplayCreateImage via Quartz；TCC 权限引导） | screen | 0.3 |
| 3.9 | 废纸篓 macOS 后端（NSFileManager trashItemAtURL） | trash | 0.3 |
| 3.10 | 路径层（CONFIG_DIR_NAME 平台分支：~/Library/Application Support/Harbor） | paths | 0.3 |
| 3.11 | 路径迁移测试（Win 路径零变化断言 + Mac 新路径断言） | 测试 | 3.10 |
| 3.12 | 进程服务 macOS 后端（ps/NSTask 枚举替代 tasklist） | process | 0.3 |
| 3.13 | 自更新策略调整（.app 整包替换 + Gatekeeper 重新引导；去掉 .bat 语义） | update | 3.10 |
| 3.14 | 通知服务 macOS 后端（NSUserNotification 替代 Windows toast；权限引导） | notify | 0.3 |
| 3.15 | M3 出口：平台服务五接口双端一致性 + 全量门禁 | 门禁 | 3.1-3.14 |

### M4 · 打包与分发（W4-W5，10 包，P1）

| # | 任务 | 交付物 | 依赖 |
|---|---|---|---|
| 4.1 | macOS build spec（--windowed + BUNDLE + Info.plist 三键） | spec | 0.10 |
| 4.2 | 图标资产（.icns 从 harbor-icon.png 生成） | 资产 | 4.1 |
| 4.3 | PyInstaller macOS 构建（arm64）+ 冒烟启动 | 构建 | 4.1/4.2 |
| 4.4 | codesign 脚本（由内而外：find Mach-O → 逐个签 → 整体签 + hardened runtime） | 签名 | 4.3 |
| 4.5 | entitlements（App Sandbox 评估：不开——需文件/网络全权；记录决策） | 配置 | 4.4 |
| 4.6 | notarytool 公证流水线（ZIP 提交 + wait + stapler + 失败日志） | 公证 | 4.4 |
| 4.7 | DMG 制作（create-dmg/hdiutil + 拖拽安装布局） | 分发 | 4.6 |
| 4.8 | 未签名降级路径（文档化 Gatekeeper「Open Anyway」引导） | 文档 | 4.3 |
| 4.9 | 版本号注入（VERSION → CFBundleShortVersionString 一致性断言） | 构建 | 4.1 |
| 4.10 | M4 出口：.app 签名验证（spctl）+ DMG 挂载安装冒烟 | 门禁 | 4.7 |

### M5 · 性能优化（W5，10 包，P1）

| # | 任务 | 交付物 | 依赖 |
|---|---|---|---|
| 5.1 | 会话池预热（首个导航前建窗；量化冷启耗时） | 优化 | 1.11 |
| 5.2 | 空闲回收 60s + 内存基线测试（常驻 <150MB） | 优化 | 1.11 |
| 5.3 | 提取带宽优化（只回传序列化结果；禁整页 HTML 回传） | 优化 | 1.6 |
| 5.4 | 多会话并发上限 3 + 排队策略 | 优化 | 1.11 |
| 5.5 | Retina 截图坐标修正（point 坐标系） | 优化 | 1.7 |
| 5.6 | 提取管线批处理（Top N 结果并行提取，上限 3） | 优化 | 2.5 |
| 5.7 | 缓存命中率面板（hit rate + 节省 token 估算） | 可观测 | 2.9 |
| 5.8 | 首 Token/导航 P50/P95 基准脚本 | 基准 | 5.1 |
| 5.9 | Apple Silicon 原生构建验证（无 Rosetta 依赖断言） | 构建 | 4.3 |
| 5.10 | M5 出口：性能基准报告（对齐竞品基线三项） | 门禁 | 5.1-5.9 |

### M6 · 安全加固（W6，10 包，P0）

| # | 任务 | 交付物 | 依赖 |
|---|---|---|---|
| 6.1 | SBPL profile 评审（最小权限：无 network 默认；工作区外零写） | 安全 | 3.5 |
| 6.2 | 网络策略三档（none/loopback/full）+ 默认 loopback | 安全 | 3.5 |
| 6.3 | 提取内容注入防御复核（provenance + 二元信号 + 弱评估器熔断） | 安全 | 2.6 |
| 6.4 | click/fill 前后态截图审计（防「点了什么没说」） | 审计 | 2.8 |
| 6.5 | 敏感字段识别（password/token 类 selector → always 档 + 掩码） | 安全 | 2.2 |
| 6.6 | 会话 cookie 隔离验证（独立 data store 断言） | 测试 | 1.3 |
| 6.7 | 沙箱逃逸测试集（符号链接/junction/管道继承/环境变量注入） | 测试 | 3.6 |
| 6.8 | Keychain ACL 审计（打包应用身份稳定 + 无明文回落） | 审计 | 3.2 |
| 6.9 | 威胁模型文档（macOS 特有了：TCC 权限滥用/AppleEvent/LaunchAgent） | 文档 | 6.1 |
| 6.10 | M6 出口：安全测试全绿 + 威胁模型评审 | 门禁 | 6.1-6.9 |

### M7 · 测试矩阵（W6-W7，5 包，P0）

| # | 任务 | 交付物 | 依赖 |
|---|---|---|---|
| 7.1 | 单元：session_mac 全原语（Mock PyObjC 层，CI 可跑） | 测试 | M1 |
| 7.2 | 契约：6 新 js_api 差分（get_api_info 逐字节 + config.json 零污染） | 测试 | 2.1 |
| 7.3 | 集成：headless 后端全工具链（CI  nightly） | 测试 | 1.12 |
| 7.4 | 平台：Keychain/Seatbelt 真机测试（仅 macOS runner） | 测试 | M3 |
| 7.5 | M7 出口：三平台测试矩阵报告 | 门禁 | 7.1-7.4 |

### M8 · 真机验证（W7-W8，5 包，P1）

| # | 任务 | 交付物 | 依赖 |
|---|---|---|---|
| 8.1 | MacBook 冒烟：导航→等待→提取→点击→截图 全链路 | 冒烟 | M2/M3 |
| 8.2 | 权限流：TCC（截屏/文件）+ Keychain 首次写入引导 | 冒烟 | M3 |
| 8.3 | Gatekeeper 全流程：未签名→Open Anyway；签名→直开 | 冒烟 | M4 |
| 8.4 | 性能实测：冷启/导航/提取三基准（对标 Windows） | 基准 | M5 |
| 8.5 | 回退验证：无网络/无权限/沙箱拒闯三异常路径 | 冒烟 | M6 |

### M9 · 发布与文档（W8，5 包，P1）

| # | 任务 | 交付物 | 依赖 |
|---|---|---|---|
| 9.1 | README/官网 Mac 安装指引（DMG 拖拽 + 权限说明 + 常见问题） | 文档 | M4 |
| 9.2 | KNOWN_ISSUES 更新（Mac 已知项：Keychain SSH 限制/更新签名/沙箱无 rlimit） | 文档 | M8 |
| 9.3 | API 参考重新生成（tools/gen_api_reference.py） | 文档 | 7.2 |
| 9.4 | 发布四件套：.app/.dmg/校验和/发布说明 | 发布 | 4.10 |
| 9.5 | M9 出口：发布评审 + 归档 | 门禁 | 9.1-9.4 |

---

## 7. 关键依赖与并行面

- **关键路径**：M0 → M1 → M2 → M3 → M4 → M8 → M9（约 8 周单人 / 5 周双人）
- **可并行**：M5 性能优化与 M6 安全加固并行；M7 测试矩阵随各里程碑滚动；文档（M9.1/9.2）可提前
- **外部硬依赖**：Apple Developer Program 账号（$99/年，M4 前必须到位）；macOS 真机（M8）；arm64 CI runner（M5.9）
- **Windows 端零影响承诺**：M0 迁移回归 + M7.2 契约差分双重保证；`sys.platform` 分支外无行为变化

## 8. 风险与验证

| 风险 | 等级 | 缓解 | 验证 |
|---|---|---|---|
| PyObjC 版本碎片化（9.x 多框架） | 中 | extras 锁定最低版本；CI 双 Python 验证 | M7.4 |
| Keychain 在 SSH/无 GUI 会话拒写（-25308） | 中 | 首次写入引导桌面会话完成；明确错误码人话 | M3.3/8.2 |
| 公证流程卡住（税务/银行信息不全） | 中 | 提前注册开发者账号走完流程；未签名降级路径 | M4.6/4.8 |
| SBPL 误伤（白名单过紧） | 中 | 最小 profile + 自检（尝试违规操作）；三档网络策略 | M3.6 |
| 沙箱无 rlimit（资源炸弹） | 中 | 监控+告警降级；文档化；对齐 mistral.rs 同款取舍 | M6.9 |
| .app 内更新破坏签名 | 中 | 整包替换策略 + Gatekeeper 重引导 | M3.13/8.3 |
| 双平台行为分歧（等待/提取语义） | 中 | 三后端一致性 fixture；抽象层单一定义 | M1.15 |
| 体量（42-48 人日） | 中 | P2 可砍（DMG 美化/性能第 5.6-5.8 项可顺延） | 里程碑出口评审 |

## ⚠️ 假设

- 工作量按 v1.8 已落地浏览器四件套复用度估算（M0/M2 大量为泛化而非新写）；PyObjC 学习曲线已按 3 人日计入 M1
- macOS 真机在 W7-W8 可用；Apple Developer 账号可由项目方提供
- 「AI 直接驱动」范围 = 6 工具原语 + dual-LLM-lite 提取；不含自主多步网页任务规划（那属浏览器 Agent 化，另立项）
- 竞品基线（<150MB 常驻）延续 v1.8 验收口径

## 免责声明
⚠️ 本方案基于公开调研（pywebview 官方文档/PyInstaller 与 Apple 公证实践/Keychain C API 实践/Seatbelt 沙箱先例）与代码库实测编制；Apple 平台政策（公证/签名/TCC）以官方最新文档为准；重要架构决策请由技术负责人审定。
