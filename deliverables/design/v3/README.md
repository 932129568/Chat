# GLM-Chat UI 重构 v3 — 交付索引

> 交付日期：2025-10-15 · 交付人：导出交付专家（交付达）
> 状态：**PASS**（契约校验 + pytest 全通过，exe 打包成功）

## 一、交付产物

| 产物 | 路径 | 说明 |
|------|------|------|
| 主程序（Windows exe） | `dist/GLM-Chat.exe`（桌面副本：`C:/Users/陈/Desktop/GLM-Chat.exe`） | PyInstaller onefile 打包，内嵌 glm-chat.html + libs |
| 前端单文件产物 | 根目录 `glm-chat.html`（约 182 KB / 3300 行） | 由 `frontend/build.js` 从 26 个源码模块构建，**勿手改** |
| 前端源码 | `frontend/index.template.html` + `frontend/src/*.js`（26 模块） | 修改后必须 `node frontend/build.js` 重新构建 |
| 后端源码 | `main.py`（薄入口）+ `backend/`（api 门面 + 8 个 service） | |
| 依赖库 | `libs/`（marked / purify / flate / highlight） | 全部本地化，无 CDN |

## 二、预览页清单（`deliverables/design/v3/`）

| 预览页 | 主题 | 变体 |
|--------|------|------|
| `preview-v3-light.html` | 浅色 | 基准 |
| `preview-v3-dark.html` | 深色 | 基准 |
| `preview-v3-light-analytics.html` | 浅色 | 数据分析面板 |
| `preview-v3-light-settings.html` | 浅色 | 设置面板 |
| `preview-v3-dark-analytics.html` | 深色 | 数据分析面板 |
| `preview-v3-dark-fxoff.html` | 深色 | 关闭特效 |

浏览器直接双击打开即可，无需任何服务。

## 三、截图清单（`deliverables/design/v3/shots/`）

| 文件 | 内容 |
|------|------|
| `light-chat.png` / `dark-chat.png` | 主聊天界面（浅 / 深） |
| `light-workspace.png` | 工作台视图 |
| `light-sessions.png` | 会话列表 |
| `light-settings.png` | 设置面板 |
| `light-analytics.png` / `dark-analytics.png` | 数据分析面板（浅 / 深） |
| `light-fxoff.png` | 关闭特效状态 |
| `dark-reducedmotion.png` | 减少动效状态 |
| `light-tooltip.png` | Tooltip 组件 |

## 四、过程文档

- `deliverables/design/v3/01-requirements.md` — Phase 1 需求发现
- `deliverables/design/v3/02-design-system.md` — Phase 2 设计系统
- `deliverables/design/v3/04-critique.md` — Phase 4 质量审查报告
- （Phase 3 构建记录见团队会话；修复记录 `05-fixes.md` 在上级目录）

## 五、最终校验数字（Phase 5 复验）

| 校验项 | 结果 |
|--------|------|
| `node frontend/build.js` | ✅ 26 模块 → glm-chat.html（3300 行） |
| `check_contract.py` DOM id | ✅ 40/40 |
| onclick 处理函数 | ✅ 13/13 |
| callApi 后端方法 | ✅ 43/43 |
| CSS 类 | ✅ 39/39 |
| CSS 变量 | ✅ 21/21 |
| 本地依赖库 | ✅ 4 引用 / 0 缺失 |
| `pytest tests/ -q` | ✅ 31 passed |
| PyInstaller 打包 | ✅ 成功 |

## 六、如何运行 / 打包 / 校验

```bash
# 运行（开发态）
python main.py

# 修改前端后重新构建
node frontend/build.js          # 或使用 node 可执行文件全路径

# 打包 exe
python -m PyInstaller --onefile --windowed --clean --name "GLM-Chat" \
  --icon "glm-chat.ico" --add-data "glm-chat.html;." --add-data "libs;libs" \
  main.py --noconfirm

# 校验契约
python deliverables/design/check_contract.py

# 运行测试
pytest tests/ -q
```

## 七、注意事项

1. 根目录 `glm-chat.html` 为构建产物，任何手改都会在下次构建时被覆盖。
2. exe 用户配置目录：`%USERPROFILE%\.glm-chat\`。
3. v2 旧版 exe 已被桌面新副本覆盖（`C:/Users/陈/Desktop/GLM-Chat.exe`）。
4. 若 exe 启动异常，可用开发说明中的"调试版"命令打包控制台版本排查。
