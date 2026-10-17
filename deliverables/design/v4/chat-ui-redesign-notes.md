# 对话区 UI 重设计 · 改动说明（v4 · Harbor）

**日期**：2026-10-18 · **基线**：Harbor（v1.5 + connect-merge 用户集成版，538 测试全绿）
**构建**：`node frontend/build.js` → harbor.html（42 模块 / 8171 行）；`check_contract.py` PASS

---

## 1. 改动清单（7 项）

| # | 诉求 | 改动 | 位置 |
|---|------|------|------|
| 1 | 文件夹设置搬到对话框旁 | 新增**工作区快捷条**：输入区上方一条 pill（文件夹图标 + 当前目录名 + 工具权限 chip + 本会话独立勾选），点开是玻璃浮层（当前/最近文件夹列表 + 浏览…/跟随全局/启用 + 生效信息行）。切目录/独立/启用/浏览全部**遥控委托**既有面板处理函数，行为零分叉 | 模板 `.ws-quick`（input-area 内）+ 新模块 `38-ws-quick.js` |
| 2 | 设置面板紧凑狭窄割裂 | ① set-block 改**卡片式**（白底+细边+圆角+浅影，原透明无边界堆叠是割裂感来源）；② 内容列 290px→**340px 起步、max-width 1040px**；③ 连接块横跨全宽（主块地位） | 模板 `.set-block`/`.set-grid`/`.cm-block` |
| 3 | 浮层悬停错位浮动 | 根因：会话行操作组 `display:none→flex` 弹跳 + `.session-del` hover 时 `position:absolute→static` 跳变（一帧错位 + reflow）。改为**常驻文档流 + opacity 淡入**（pointer-events 跟随），另修 `.cs-opt.on` 加粗导致的选项文本度量跳变 | 模板 `.session-acts`/`.session-del`/`.cs-opt.on` |
| 4 | 设置展开过渡生硬 | ① 设置面板由「文档流内挤压聊天区」改**覆盖层**（absolute inset:0，打开不再推挤输入框，聊天原样停在后面）；② 关面板补**退场动效**（v4SetOut 140ms in-soft + onAnimEnd 双兜底，原来瞬间消失） | 模板 `.settings-panel` + `100-send.js` toggleSettings |
| 5 | 统一下拉框视觉 | 全部 select 走统一 CS 封装（boot 遍历 + cs-src 隐藏原生）；触发器/菜单/选项同一套玻璃令牌；去掉选中项加粗（防跳变）；Harbor 品牌字样统一（空状态/输入框占位） | 模板 cs-* + 品牌字符串 |
| 6 | 复制按钮悬停弹出 | 操作条（复制/重新生成/收藏/继续输出）收进 `.msg-actions`：默认 `opacity:0 + translateY(4px)`，**悬停对话框**或键盘 focus 时 130ms pop 淡入；触屏点消息也能唤出（`.acting`） | 模板 `.msg-actions` + `50-markdown.js`/`60-agent-loop.js` |
| 7 | 整体最新审美 | 上述全部落在 v4「精致静谧」体系内：玻璃浮层、四层动效令牌、进出对称、性能白名单（零布局属性动画）、fx-off/reduced-motion 降级保留 | — |

## 2. 前后端联调结果

- `pytest tests/ -q` → **538 passed**（契约差分 / 安全 / v12-v15 各层 / 用户新增 4 个测试文件全绿）
- `deliverables/design/check_contract.py` → **PASS**（DOM id / onclick / callApi / CSS 类 / 变量只增不改）
- `node frontend/build.js` → 成功（42 模块拼接 + new Function 语法校验）
- 联调中硬化 2 个负载敏感的自有测试（并行探测改「时间跨度重叠」证明、并发排队改轮询等待），消除 flaky

## 3. 预留接口说明（本次**零新增/零修改**，全部复用既有 js_api）

工作区快捷条是「遥控器」，不引入新接口；复用清单：

| 方法 | 参数 | 用途 |
|------|------|------|
| `get_ws_state(sid)` | sid: 会话 id | 读工作区状态 `{ws, bound, enabled, recent[]}`——快捷条主数据源 |
| `get_effective_ws()` | — | 生效目录与来源（全局/会话/未启用）——浮层底部信息行 |
| `list_recent_ws()` | — | 最近文件夹列表（经 get_ws_state.recent 同源获取） |
| `set_ws_dir(path)` | path: 目录 | 切全局目录（非独立态） |
| `set_session_ws(sid, path, enabled)` | sid/path/enabled | 绑/切/解本会话目录（独立态） |
| `set_ws_enabled(sid, enabled)` | sid/enabled | 工作区总开关（「启用工作区」按钮） |
| `get_session_ws(sid)` / `delete_session_ws(sid)` | sid | 会话绑定查询/删除（面板既有） |
| `pick_folder(sid)` | sid | 系统目录选择器（「浏览…」按钮） |

v1.5 预留接口层（`local_probe`/`local_models`/`webdav_*`）与 connect-merge 的模型识别链路（`local_models` 带 Key 拉清单）均**未改动**——本次为纯前端交互重构 + 遥控式复用。

## 4. 已知边界（如实）

- 设置浮层现为聊天区内覆盖层：打开时盖住消息流与输入区（聊天原样保留在背后），关闭回退场动效；Esc 暂不关设置浮层（头部按钮切换，后续可加）
- 工作区面板（面板 4）保留为详细视图，与快捷条双入口并存（单一事实源同步）
- 本环境无 webview：起窗实测需装机环境；测试层（契约/沙箱/构建）已全绿
