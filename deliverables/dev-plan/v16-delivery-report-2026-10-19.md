# Harbor v1.6.0「开放版」交付总结

**日期**：2026-10-19 · **commit**：`b95ab5d` · **测试**：677 passed / 1 skipped / 0 failed
**三闸**：build 9627 行 md5 幂等（`af24d656...`）· UI 契约 PASS · 全量回归绿
**发布门（T14）**：五闸全过；`dist/Harbor.exe` 拆归档验证内嵌 harbor.html 与磁盘逐字节一致，五大新特性俱在。

---

## 一、交付内容（T1-T14 全部落地）

| 里程碑 | 任务 | 状态 | 关键实现 |
|---|---|---|---|
| M1 | T1 GitHub Models 预设 | ✅ | `models.github.ai/inference`、PAT models:read scope 指引、免费层徽标 + 禁生产常驻声明（裁决①口径） |
| M1 | T2 目录探测 | ✅ | 延展 `local_models` 按 host 分流 catalog（**零新 js_api**）；provider/model 格式过滤、ctx 三别名、modalities 容错、401/403/429 人话、失败降级热门兜底+手输 |
| M1 | T3 429 人话 | ✅ | RPM vs 日额度双分支（header 解析）+ 无头兜底，5 用例锁定 |
| M1 | T4 DeepSeek 校准 | ✅ 代码级 | preset 结构与官方一致，结构锁定测试；**真机联调待目标机** |
| M1 | T5 提示词五处 | ✅ | 沙箱边界告知段（INTENTIONAL_DELTAS 白名单，关时不注入）/ 限额策略+ MCP 铁律 / compact 保留工具序列 / 本地上下文有限 / MCP instructions 维持不注入 |
| M2 | T6 沙箱面板 | ✅ | `39-sandbox.js`：开关/三类别档位/限制编辑/状态灯/累计统计/重置/非 Windows 明示 |
| M2 | T7 W21-26 | ✅ | 池并发限制接线/stale 去抖/404 退避/_closed 态防复活/forget 代际/keep_both 毫秒戳 |
| M2 | T8 边界项 | ✅ | W27 墓碑 backendOk 门/W28 生成中 continue/W30 compact 逐条 try/W33 并发探测 last-wins |
| M2 | T9 冒烟 | ✅ **六步全过** | 真实 Job Object：echo/超时清剿孙进程/fail-closed/审计/切档位真实生效/非 Windows 降级（代码级） |
| M3 | T10 本地优化 | ✅ | 503 指数退避（锁定 v1.5）/首 token 等待态/tokens-s 实时显示（无 usage 标「估」） |
| M3 | T11 布局直切 | ✅ | `41-nav.js` 五区导航（对话/设置/审计/搜索/沙箱+通知中心）；老入口 DOM 保留行为并入；空态三步引导；首次引导（裁决②口径） |
| M4 | T12 MCP resources | ✅ | list（分页聚合）+ read（text 直出/blob 落盘 toolcache）+ 订阅注入 + 全程审计 + UI 资源 tab；三 js_api 进 `_V12_EXTRA` |
| M4 | T13 DND | ✅ | 失焦抑制 ok/info（warn/err 放行）+ 通知中心红点/列表/清空（裁决③口径） |
| M4 | T14 发布门 | ✅ | 677 passed / 契约 PASS / build 幂等 / exe 拆归档验证 |

## 二、过程中抓到并修复的问题（不止方案清单）

1. **测试地基级 bug**：`sandbox_service._STATS` 模块级计数器跨测试累积 → 文件间顺序依赖（`importlib.reload` 巧合掩盖）。修法：conftest autouse 显式 reset + delta 断言，正反两种顺序 61/61 实证。
2. **T1 引入的 UX 退化**：GitHub 热门兜底表使识别失败（如 401）被吞成「已加载 N 个模型」静默成功 → 失败 warn 透因 + 兜底说明。
3. **QA 自引入顺序依赖**（T9 step3 类重绑定）+ **测试 harness ~20% 抖动**（401 前不读 body 踩连接重置）——均测试侧修复。
4. 双实例并发的文件边界协调（T2 主体/文案/测试文件分工，无双写事故）。

## 三、T15 遗留结论（排期/不做二选一）

| 项 | 结论 | 理由 |
|---|---|---|
| **T4 DeepSeek 真机联调** | **排期 v1.6.1**（首条） | 无外网环境不可为；代码级校准已完成 |
| **Ollama /api/tags 真机销项**（KNOWN_ISSUES #2） | 排期 v1.6.1（同 T4 一批目标机验证） | 代码级验证已过 |
| **token -15% 量化目标** | 排期 v1.6.1 目标机基准链复跑 | 本环境无外网，协议就绪（3 条标准链） |
| **GitHub Models 限额复核** | 排期 v1.6.1 真机（真实 PAT） | §9 外部源数字需实测校准 |
| **遥测最小版** | **明确不做（v1.6.x 内）** | DND 已裁决入选；遥测的合规叙事收益低于成本，如未来重启动机需先过隐私设计评审 |
| **OAuth（MCP 远程认证）** | 明确不做（v1.6.x） | stdio+本地 HTTP 场景无刚需；远程 MCP 需求出现时再评估 |
| **多模态输入** | 明确不做（v1.6.x） | v1.2 起 Non-goals 延续 |
| **WebDAV 真实服务器联调** | 排期 v1.7 | 需坚果云/Nextcloud 账号与冲突合并 UX 设计稿 |
| **代码签名** | 排期发布前评估 | 成本项，先积累误报反馈数据再决策 |

## 四、验证矩阵

| 门 | 数字 | 执行方 |
|---|---|---|
| pytest 全量 | 677 passed / 1 skipped / 0 failed | 主理人终验 + QA 独立复跑 |
| UI 契约 | PASS（40/13/43/39/21 + libs 4/4） | 主理人终验 |
| build 幂等 | 9627 行，两遍 md5 `af24d656...` | 主理人终验 |
| exe 拆归档 | 内嵌与磁盘 md5 一致；五新特性俱在 | 主理人 |
| 沙箱冒烟 | 六步全过（真实 Job Object） | QA |
| 修复抽查 | 12/12 逻辑真实 | QA |
| 顺序无关性 | 正反/混合序 61+61+37 | QA + 工程师 |

## 五、给用户的下一步（目标机清单）

1. **DeepSeek 真机校准**：跑基准链②（单文件改），验证工具调用全成功+计费正确（T4 销项）
2. **Ollama 冷启动**：验证 503 退避可见+首 token 等待态+/api/tags 徽标（KNOWN_ISSUES #2 销项）
3. **GitHub Models**：真实 PAT 探测目录（provider/model 格式）、触发 429 看 RPM/RPD 人话
4. **布局直切验收**：老用户升级后老设置按钮→新导航通路、空态三步引导、首次引导 toast
5. **基准链复跑**：3 条标准链前后对比，记录 token 累计（-15% 目标）
