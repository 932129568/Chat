# Harbor v1.8.0「Agent 能力版」· 整体设计方案包

**日期**：2026-10-20 · **状态**：v1.1（原型经 5 维审查 REVISE→修复后 PASS；§7 待裁决项待产品负责人审定）
**基线**：v1.7.0（701 passed / 契约 PASS）+ v1.8.0 迭代方案 + Agent 自主调研
**消费方**：前后端开发（可并行）· 产品审定 · 后续版本规划

---

## 交付物清单

| # | 文件 | 内容 | 对应需求 |
|---|------|------|----------|
| 1 | `deliverables/dev-plan/v18-architecture-and-interfaces-2026-10-20.md` | **系统架构 + 模块划分 + 核心接口定义与数据契约 + 前后端联调计划 + 平滑演进方案**：四层正交架构图；后端 8 模块/前端 5 新模块+2 改；**17 个新 js_api 完整契约**（请求/响应 JSON schema/错误码/护栏映射/扩展点，v1.9.0 预留位单列）；T0 契约冻结 + 三层 Mock（fixture 即契约）+ 里程碑 W1-W5 对齐；零破坏性变更 8 条红线 | 用户要求 ①②⑤ |
| 2 | `deliverables/design/v18/ux-flows.md`（890 行） | **10 个关键交互流程状态机**（v1.8.0×6 / v1.8.5×1 / v1.9.0×3）：触发条件/分步四列表/ASCII 状态机/状态反馈表/中断取消语义/前后端触点；铁律「≥3s 动作必须可见等待，禁止静默黑箱」；10 个 Gap 与 4 个优先裁决项 | 用户要求 ③ |
| 3 | `deliverables/design/v18/motion-spec.md`（252 行） | **15 组件动效规范表**（入场/出场/悬停/按压/状态切换/降级六列，全部具体值+四律标签）+ 长任务可见等待四件套（阶段 pill/骨架/进度/心跳 + pacing 五律）+ 六态视觉字典 + fx-off/reduced-motion/reduced-transparency 完整降级矩阵 + 九域 class 命名 + 新 keyframes 清单 | 用户要求 ④ |
| 4 | `deliverables/design/v18/prototype.html`（1162 行） | **可交互单文件原型**：仿真「查 Qwen3 + git 提交」全链；8 大模块全部可演示（演示控制台：完整链播放/8 单步/主题/fx-off/reduced-motion，键盘 1-8）；零外部依赖、深浅双主题、动效值全部取自 motion-spec | 用户要求 ③④ |
| 5 | `deliverables/design/v18/check_proto.js` | 原型独立验证脚本（JS 语法/禁项/九域类名/令牌/降级/双主题 24 项） | 质量保障 |
| 6 | `deliverables/design/v18/critique-report-v18.md` | 质量审查报告（5 维评分 16/25 REVISE + Anti-Slop 门控 + 12 项问题清单 + 修复复核记录：修复后 PASS） | 质量保障 |

## 版本编排（设计包覆盖范围）

| 版本 | 能力 | 设计覆盖 |
|---|---|---|
| **v1.8.0** | B 浏览器搜索 / S 软件调用 / H 本地协同 / V1 校验 / C1 缓存 / U1 接管 / S3 软件面板 | 架构契约 + UX 流程 1-6 + 动效 + 原型 |
| **v1.8.5** | A1/A2 权限地基（L2 任务授权 + L4 白名单） | UX 流程 7 + gr-* 动效 + 原型演示 |
| **v1.9.0**（接口预留） | Plan-Act / 批量澄清 / 检查点回滚 / A3 L3 | UX 流程 8-10 + plan-/clr-/ckpt- 动效 + 原型演示 + 接口预留位 |

## 核心设计决策（TL;DR）

1. **四层正交不变**：路由层（hybrid_router）→ 工具层（search/software）→ 护栏层（guard_service）→ 沙箱层（sandbox_service）；任一层失效不架空其余层。
2. **契约零变更**：17 个新 js_api 全进 `_V12_EXTRA`；`build_tools` 加 `include_agent=False` 可选参数（默认路径逐字节不变）；config.json 零污染（software.json/hybrid.json 独立）。
3. **UX 铁律**：Agent 每个 ≥3s 动作必须有可见等待/进度态——长任务四件套（阶段 pill + 骨架 + 进度 + 心跳）是原型的核心演示点。
4. **动效延续 v4**：零新增动效令牌、零新色值；新组件先找同源参照物（settle flash 一律 v4ToolSettle 200ms、spinner 一律 --dur-stream 1.4s）再定值；倒计时环 stroke-dashoffset 1s/跳为登记例外（时钟语义）。
5. **并行开发边界**：T0 契约冻结后前后端按契约并行；纯函数（引擎适配器/提取器/validator）本环境全绿；Mock 三层（fixture 单测 / vm harness + Mock js_api / CDP 真机冒烟）。

## 待产品负责人裁决（源文档 §13 + §11 共 7 问 + UX Gap 4 项）

1. 搜索默认引擎 Bing；U1 人工接管面板随首批（+2 人日）还是 v1.8.1
2. software_call 默认档位（mutate→session）；dangerous→always 是否过严
3. 混合路由默认 auto；saver 质量下降提示
4. 版本合发 v1.8.0 或拆两批
5. A1/A2 是否提前插 v1.8.5（+3 人日）
6. L2 授权 TTL：2h 固定 vs 任务生命周期+空闲 30min 收回（UX Gap：进行中调用竞态未定义）
7. 检查点保留策略：到下一任务 vs 完成即清
8. （UX Gap）browser_search 进度回报通道：事件推送 or search_status 轮询——接口清单需明确
9. （UX Gap）saver 下降级必提示 vs 省钱意图的张力
10. （UX Gap）GLM 端点双通道工具选择歧义（建议 include_agent 下 GLM 场景只下发 browser_search）
