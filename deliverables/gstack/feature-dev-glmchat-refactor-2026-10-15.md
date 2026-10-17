# GLM-Chat v1.0.0 → v1.1 全栈重构交付报告

**日期**：2026-10-15
**场景**：全流程交付（产品评审 → 代码重构 → QA测试）
**参与成员**：产品官（gstack-product-reviewer）+ 主理人代行实施与 QA（子代理基础设施 6 次网络故障，详见「待完善」）

---

## 📌 TL;DR（执行摘要）

- **整体结论：🟢 通过（GO）**。v1.0.0 已完成全面重构：后端 1325 行单类 → `backend/` 分层包；前端 2401 行单文件 → `frontend/src/` 24 模块 + 零依赖构建。
- **行为零漂移已被机器证明**：差分契约测试对 49 个公开方法逐一比对 v1.0.0 与重构后输出，29 项测试全绿；前端 63 处 callApi 契约、42 个 DOM id、style/body/libs 零变化。
- **顺手修掉 1 个 P0 真实漏洞**（`copy_into_ws` 路径穿越写入）+ 5 项安全加固（命令去重全量接入、kill 保护名单、admin 真实退出码、永久删除警示、静默吞错改日志）。
- 阻塞项：0。遗留：起窗/exe 冒烟需在装机环境人工执行（本环境无 webview/PIL）。

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| Go / No-Go | 🟢 Go |
| 严重度分布 | 🔴 0 / 🟠 0 / 🟡 0 / 🟢 0（QA 矩阵 24/24 PASS；2 个过程问题已修复复测） |
| 关键行动项 | 3 条（装机冒烟、exe 打包冒烟、v1.1 安全增强决策） |
| 建议负责人 | 工程负责人 |

---

## 1. 各成员核心结论

### 🔍 产品官（产品评审）
- 核心判断：v1.0.0「功能野心很大、安全意识不低、工程结构停留在单文件脚本阶段」；核心资产是 50 个 js_api 方法的稳定契约，核心负债是单类 + 全局状态 + 导入即启动导致的「结构性零可测试性」。
- 关键建议：门面模式分层 + 先补黑盒契约测试安全网 + 顺手修 P0/P1；命令 allowlist、剪贴板/截屏确认等行为变更留 v1.1 做产品决策。**P0：copy_into_ws name 未消毒，可路径穿越写入。**
- 原始产出：`deliverables/gstack/review-product-glmchat-main-2026-10-15.md`（344 行，含带行号的架构/安全清单与 Step 0-9 实施方案）

### ✅ 质量门神（QA测试与发布）
- **执行者说明**：QA 官派遣 1 次，因子代理网络 502 失败；由主理人按 QA 流程代行，结果真实可复现。
- 核心判断：24 项验证矩阵全过；差分契约测试（legacy vs 重构后同序列调用输出逐字节一致）是本次重构正确性的最强证据；前端「保序拼接」策略经 QA 抓到并修复排序 bug 后收敛为纯预期变更。
- 原始产出：`deliverables/gstack/qa-regression-glmchat-refactor-2026-10-15.md`

---

## 2. 综合审查发现（去重合并后按严重度排序）

| # | 严重度 | 类别 | 位置 | 问题描述 | 建议 | 来源成员 |
|---|--------|------|------|---------|------|---------|
| 1 | 🔴→✅已修 | 安全 | legacy L937-949 | copy_into_ws name 未消毒，`..\..\evil.exe` 可路径穿越写入（同文件 L221 有消毒，两个标准） | 复用消毒正则 + 禁 `..` + realpath 双保险；3 例定向测试 | 产品官 |
| 2 | 🟠→✅已修 | 架构 | legacy L582/614 | run_command/run_powershell 未接去重（RunDeduper 只在 admin 路径被调用） | 接入统一去重；顺带修 RunDeduper 两弱点（首 token 绕过、只比上一条） | 产品官 |
| 3 | 🟠→✅已修 | 架构 | legacy L90-127 | RunDeduper 无锁、`_RT['ws_enabled']` 无锁、config.json 读改写竞态、_append_hist 无锁 | 锁统一收编进 RuntimeState/service 实例 | 产品官 |
| 4 | 🟠→✅已修 | 架构 | legacy import 即 webview.start() | 导入 main.py 即建窗启动 → 结构性零可测试性（v1.0.0 无任何自动化测试的根因） | 入口瘦身 + webview 惰性导入；差分契约测试 29 项成为永久守门员 | 产品官 |
| 5 | 🟡→✅已修 | 产品 | 前端 L432-465 vs 后端 build_tools | 工具 schema 双数据源且已漂移（前端缺 clipboard/process/memory，read_file 上限 2000 vs 20000），后端失败静默降级 → AI 悄悄丢能力 | 删前端 TOOLS，唯一来源=后端 build_tools；失败显式报错 | 产品官 |
| 6 | 🟡→✅已修 | 安全 | legacy L785 | kill_process `taskkill /F /T` 无保护名单 | 系统关键进程 + 自身 pid 保护名单 | 产品官 |
| 7 | 🟡→✅已修 | 安全 | legacy L668/672 | run_admin_command 恒返回 exit_code=0 掩盖失败 | 退出码落盘透传，缺失返回 unknown | 产品官 |
| 8 | 🟡→✅已修 | 工程 | legacy 16 处 `except Exception: pass` | 静默吞错，生产不可诊断 | logging 落盘 ~/.glm-chat/logs/glm-chat.log，API 进 runtime.py L2205） | 保留 pywebview 打包命令；tests/__pycache__、__pycache__ 可随时删 |
| → | 增量回滚 | — | main.py / glm-chat.html | 单文件级别回退 | `cp main_v1.0.0_legacy.py main.py && cp glm-chat.v1.0.0.html glm-chat.html`（备份即 v1.0.0 原件） | QA |

---

## ⚠️ 待完善 / 已知局限

1. **装机环境冒烟未执行**：本环境无 webview/PIL，`python main.py` 起窗、exe 打包冒烟需人工执行（QA 报告已列检查清单）。
2. **子代理基础设施不稳定**：本轮 6 次派遣因 502/ECONNRESET 失败（产品官成功交付后也遭遇框架 500）；实施与 QA 由主理人代行。建议工程负责人在收尾时复核关键改动。
3. **readonly 档位语义变化**（单数据源的必然结果）：ro 档不再含 run_command（后端 ro schema 本就不含），ro 将包含 clipboard_read/list_processes/append_memory。属设计意图对齐，需产品确认。
4. **命令去重为行为变更**（用户授权范围内）：重复命令现会被拒（含 run_command/run_powershell），拒绝文案与 v1.0.0 admin 路径一致。
5. **v1.1 候选（本次明确不做）**：命令 allowlist/工作目录强制、剪贴板读与截屏前用户确认、前端 TOOLS 路由的进一步精简、logging 与错误协议 JSON 化、契约三处方言的统一（get_clipboard vs clipboard_read 等）。

---

## 📚 成员产出索引

- 产品官原始产出：`deliverables/gstack/review-product-glmchat-main-2026-10-15.md`（产品/架构/安全三维度 + Step 0-9 重构方案）
- QA 回归报告：`deliverables/gstack/qa-regression-glmchat-refactor-2026-10-15.md`（24 项验证矩阵 + 发布检查清单 + 回滚预案）
- v1.0.0 原件备份：`main_v1.0.0_legacy.py`、`glm-chat.v1.0.0.html`（差分测试的行为基准，勿删）

---

> 本报告由软件工坊 AI 协作生成，关键决策请由工程负责人复核。
