# GLM-Chat UI 重设计 · 交付索引

> 任务：**对软件 UI 进行设计，联通前后端**
> 交付日期：2026-10-15 ｜ 设计原型专家团（design-engine-glmchat）

---

## 1. 最终产物

| 产物 | 路径 | 说明 |
|------|------|------|
| **可运行程序** | `dist/GLM-Chat.exe`（18.6 MB）<br>副本：`C:/Users/陈/Desktop/GLM-Chat.exe` | PyInstaller onefile，内嵌新版 `glm-chat.html` + `libs/`，MD5 一致 |
| **前端构建产物** | `glm-chat.html`（2668 行） | pywebview 实际加载的文件（由 `frontend/` 构建，**勿手改**） |
| **前端源码** | `frontend/index.template.html` + `frontend/src/*.js` | 重设计后的骨架 + CSS + 逻辑模块 |
| **设计预览（可交互）** | `deliverables/design/preview-{dark,light,dark-settings,light-empty}.html` | 注入 mock 后端桥的独立预览，双击即可看 |
| **视觉走查截图** | `deliverables/design/shots/*.png` | 双主题 / 设置面板 / 空状态 / 工具卡三态 |

## 2. 过程文档（按 SOP 阶段）

| 文件 | 阶段 | 产出人 |
|------|------|--------|
| `00-contract-brief.md` | 基线 | 主理人 |
| `01-requirements.md` | Phase 1 需求发现 | 许明需（需求发现分析师） |
| `02-design-system.md` | Phase 2 设计系统 | **主理人代行**（彩格调 连续 2 次基础设施 500 故障） |
| `04-critique.md` | Phase 4 质量审查 | 严过审（质量审查官） |
| `05-fixes.md` | Phase 4 修订轮 | 主理人 |

## 3. 工具脚本（可复用）

| 脚本 | 用途 |
|------|------|
| `check_contract.py` | 一键校验 40 DOM id / 43 callApi / 13 onclick / 39 CSS 类 / 21 主题变量 / 本地依赖库 |
| `make_preview.py <light\|dark> [settings\|empty]` | 生成注入 mock 后端的预览页 |

```bash
# 常用命令
node frontend/build.js                                  # 构建前端（必须，产物为根目录 glm-chat.html）
python deliverables/design/check_contract.py            # 契约校验
python deliverables/design/make_preview.py dark         # 生成深色预览
pytest tests/ -q                                        # 后端回归
```

## 4. 本轮修复的关键联通缺口

`frontend/index.template.html` 此前引用 `libs/marked.min.js`、`libs/purify.min.js`、`libs/highlight.min.js`，但 `libs/` 下实际只有 `marked.js`、`purify.js`、`flate.js` —— **三个库全部 404**，导致：

- `window.marked` / `DOMPurify` 未定义 → `renderMd()` 退化为纯文本转义，**Markdown 完全不渲染**；
- `window.hljs` 缺失 → 代码高亮全部失效。

**修复**：`marked.js → marked.min.js`、`purify.js → purify.min.js`（二者本就是压缩版），并补齐 `libs/highlight.min.js`（highlight.js v11.9.0）。模板引用无需改动。

## 5. 验收状态

| 项 | 结果 |
|----|------|
| 契约校验 `check_contract.py` | **PASS**（六大项全数保住） |
| 后端回归 `pytest tests/ -q` | **31 passed** |
| WCAG AA 对比度（12 项实测） | **0 项不合格** |
| exe 内嵌资源一致性 | 与磁盘构建产物**逐字节一致** |
| 双主题渲染 | 已截图确认 |
