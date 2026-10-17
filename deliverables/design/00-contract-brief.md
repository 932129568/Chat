# GLM-Chat UI 重设计 · 共享契约简报（所有成员必读）

> 本文件是本轮"UI 重设计 + 前后端联通"任务的**硬约束基线**。任何视觉/结构改造都不得破坏下列契约，否则前端将无法驱动后端。

## 1. 项目性质

- **产品**：GLM-Chat —— 一个基于 pywebview 的 Windows 桌面 AI Agent 客户端（单窗口，前端 HTML 单文件 + Python 后端）。
- **前端**：`frontend/index.template.html`（骨架 + 全部 CSS）+ `frontend/src/*.js`（25 个模块，按文件名数字前缀拼接成同一个 `<script>`）。
- **构建**：`node frontend/build.js` → 产出根目录 `glm-chat.html`（pywebview 加载/打包的就是它）。
- **铁律**：**永远不要直接改根目录的 `glm-chat.html`**，它是构建产物。只改 `frontend/` 下的源码，然后重新构建。
- **后端**：`backend/api.py` 是 50 个 `js_api` 公开方法的门面，返回 JSON 字符串。前端通过 `window.pywebview.api[name](...args)` 调用。

## 2. 前端 ↔ 后端调用契约（不可改）

统一入口：`callApi(name, argsArray, timeoutMs)`（见 `frontend/src/05-bridge.js`），内部 `window.pywebview.api[name](...args)`。

前端实际调用的后端方法（共 43 个，全部必须保持可用）：

```
set_current_sid set_session_ws append_memory clear_caches set_ws_dir get_memory
append_worklog write_file take_screenshot set_ws_enabled set_clipboard search_replace
save_workspace_file save_sessions save_config run_powershell run_command run_admin_command
read_more read_file pick_folder open_url open_billing open_app move_path make_dir
list_processes list_dir kill_process get_ws_state get_worklog get_sessions get_file_info
get_effective_ws get_config get_clipboard get_api_info delete_session_ws delete_path
copy_path build_tools build_system_prompt append_file
```

**改造时禁止**：改方法名、改参数个数/顺序、改返回值解析方式。

## 3. DOM 契约（`getElementById` 依赖的 40 个 id，一个都不能丢）

```
apiKey attachPreview brandModel chatContainer continueNewBtn ctxMenu effPath effTag
emptyState enableSearch headerTitle liveTokenStat maxTokens modelSelect reasoningEffort
saverLevel searchEngine searchEngineWrap sendBtn sessionBudget sessionList settingsPanel
shotQuality sidebar streamBar systemPrompt tempVal temperature themeBtn tokenStat
toolMode topP topPVal userInput wsBody wsEffPath wsEffTag wsEnabled wsInd wsSel wsUnbindBtn
```

> 注意：`ctxMenu` 由 JS 动态创建并 append 到 body（`105-context-menu.js`），模板里可不含。
> `emptyState` 由 `85-session-mgmt.js` 的 `newSession()`/`switchSession()` 动态重建，**其内部 HTML 结构也要保持一致**（见下）。

## 4. 模板 `onclick` 契约（内联事件处理函数，必须存在且签名不变）

```
newSession() exportChat() openBilling()
onFolderEnabled(this.checked) onIndToggle(this.checked) onWsSelect(this.value)
browseWs() unbindSession() toggleSidebar() toggleTheme() toggleSettings()
sendMessage() continueInNewSession()
document.getElementById('imgInput'|'vidInput'|'fileInput'|'zipInput').click()
```

## 5. CSS 类契约（JS 动态创建/操作的元素，样式类名必须保留）

JS 会 `createElement` 并赋予这些类名，CSS 必须为它们提供样式：

```
.message / .message.user / .message.assistant / .avatar / .content / .content.error
.md-body / .typing-dots / .tool-call-item / .tool-spinner / .toolchip / .tc-head / .tc-label / .tc-meta
.usage-info / .msg-images / .msg-file / .copy-btn / .code-copy / .code-lang
.cs / .cs-trigger / .cs-label / .cs-arrow / .cs-menu / .cs-opt / .cs-opt.on / .cs-src
.ctx-menu / .ctx-menu-item / .sys-tip / .attach-item / .attach-preview
.session-item / .session-item.active / .session-title / .session-time / .session-del / .sidebar-empty
.empty-state / .empty-icon
```

`emptyState` 动态重建用的固定结构（`85-session-mgmt.js` L21-26）：
```html
<div class="empty-state" id="emptyState">
  <div class="empty-icon">✦</div>
  <h2>开始和 GLM 聊天</h2>
  <p>支持文字、图片、视频、文本文件 · 历史记录自动保存</p>
</div>
```

## 6. 主题变量契约

- 主题通过 `body.dark` 类切换（`15-theme.js` / `applyTheme()`），`localStorage['glm_theme']` 存 `light`/`dark`。
- 全部颜色走 CSS 变量（`:root` 与 `body.dark` 两套），**改造后必须两套主题都成立**。
- 现有变量名：`--bg --sidebar-bg --main-bg --header-bg --card-bg --border --text --text-2 --primary --primary-hover --user-bubble --ai-bubble --hover --active --chip-bg --ok --warn --err --shadow-sm/md/lg`。
  新增变量可以，但**已有变量名不得删除**（多处 JS 用 `var(--primary)` / `var(--chip-bg)` / `var(--err)` 内联引用）。

## 7. 已知联通缺口（本轮必须修复）

`frontend/index.template.html` 头部引用了 4 个本地库：

```html
<script src="libs/flate.js"></script>
<script src="libs/marked.min.js"></script>     <!-- 文件不存在！实际文件是 libs/marked.js -->
<script src="libs/purify.min.js"></script>     <!-- 文件不存在！实际文件是 libs/purify.js -->
<script src="libs/highlight.min.js"></script>  <!-- 文件完全不存在！ -->
```

- `libs/` 实际只有 `flate.js`、`marked.js`（marked v12.0.2 压缩版）、`purify.js`（DOMPurify 3.0.9 压缩版）。
- 后果：`window.marked` / `window.DOMPurify` 为 undefined → `renderMd()` 退化为纯文本转义，**Markdown 完全不渲染**；`window.hljs` 不存在 → 代码高亮全失效。
- 修复方向：让 `<script src>` 与实际文件一致，并补齐 highlight 库。

## 8. 现有 UI 结构速览（改造对象）

- **侧栏 `.sidebar`（272px，可折叠 `.collapsed`）**：品牌区 → 新建对话 / 导出 / 余额三个按钮 → 工作区卡片 `.ws-card` → 工具权限下拉 → 生效路径条 `.eff-row` → 会话列表 `.session-list` → 底部 token 统计 `.token-stat`。
- **主区 `.main`**：顶部 `.header`（☰ / 标题 / 徽章 / 主题 / 设置）→ `.settings-panel`（4 个 `.set-block` 网格）→ `.chat-container`（消息流）→ `.input-area`（附件预览 + 工具按钮行 + 输入框 + 提示行）。
- 空状态 `.empty-state`、消息气泡、代码块（深底）、工具卡片 `.tool-call-item`、流式进度条 `.stream-bar`、系统提示 `.sys-tip`。

## 9. 交付要求

- 所有产出放 `deliverables/design/` 下。
- 语言：简体中文。
- 改造必须落到 `frontend/` 源码，并通过 `node frontend/build.js` 重新构建出 `glm-chat.html`。
