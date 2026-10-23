# Harbor v1.9.0 前端组件结构与移植规范（交接报告组件章节底稿）

> 主理人画统筹汇编，2026-10-23。上游：许明需需求摘要 + 彩格调令牌方案（token-upgrade-plan.md）+ 筑原型 6 文件（prototypes/）。本节为 Phase 5 交接报告的组件结构事实底稿。

## 一、模块地图（v1.9 前端增量）

| 新/改模块 | 职责 | 依赖后端接口 |
|---|---|---|
| `66-plan.js`（改） | Intent Preview 计划卡：ETA/风险条/边界声明/累计上下文/批准链动效/自动批准态 | plan_propose（已交付） |
| `67-plan-card.js`（改） | 检查点入口：回滚链接+清单对话框+校验提示 | checkpoint_create/list/rollback（后端已备） |
| `26-guard.js`（改） | 审批预算指示器+授权条增强（常驻一键收回+超限升级任务授权邀请） | guard_approval_budget（M2.4 后端） |
| `39-search-panel.js`（改） | 浏览器驱动面板：可见/隐藏模式+六原语状态+反爬接管 | browser_* 六工具（M3-M5 后端） |
| `34-local-model.js`（改） | dual-LLM-lite 状态灯（读取器可用性/降级计数） | search_reader_stats（M2.1 后端） |
| `25-tool-exec.js`（改） | browser_* 六工具分发+isError 回传+校验反馈 | 同上 |
| `69-platform.js`（新） | 平台探测展示+macOS 分支根类+权限引导入口 | get_platform_info（M6.10 后端） |
| `60-agent-loop.js`（改） | 计划审查主关卡分支（批准才执行） | plan_propose/approve（已交付） |
| `74-audit-view.js`（新） | 审计五维哈希链可见性（head 8 位+len+断链 err） | sessions.audit_chain（M2.6 后端） |
| `index.template.html`（改） | 纯新增：计划卡/检查点/浏览器面板/预算指示器/mac 根类样式 | — |

## 二、新组件清单（纯增命名，前缀即域）

| 前缀 | 组件 | 状态枚举 | 原型 |
|---|---|---|---|
| `plan-` | eta（ETA 徽标）/riskbar（左 3px 风险条）/scope（边界声明区）/ctx（累计上下文）/auto（自动批准态） | pending/doing/done/blocked/skipped（既有五态） | plan-intent-preview.html |
| `ckpt-` | list（清单态）/verify（校验态）/row（文件行 mod/add/del 徽标） | 清单→确认→校验三态 | checkpoint-dialog.html |
| `brw-` | mode（可见/隐藏切换）/row（六原语状态行）/takeover（反爬接管卡） | ok 待命/warn 运行/err 失败 | browser-driver-panel.html |
| `grant-` | budget（预算指示器）/budget.over（超限态）/revoke（一键收回） | used/limit/escalated | grant-budget.html |
| `mac-` | kbd（键位提示）/badge（平台徽标）/switch（圆钮） | body[data-platform="mac"] 驱动 | macos-adaptation.html |
| `audit-` | chain（哈希链首 8 位）/break（断链 err 态） | head/len | （随 74-audit-view.js 移植） |
| `untrusted` | UNTRUSTED 内容标记（琥珀 45° 斜纹边+mono 来源） | — | plan-intent-preview.html 内演示 |

## 三、动效分配矩阵（彩格调方案 §3，移植时直接引用）

| 场景 | 曲线 | 时长 | 说明 |
|---|---|---|---|
| 模式切换（brw-mode/平台注入） | spring | 200ms | 形变生命感 |
| 计划卡批准 | anticipate | 两段式 60ms 回缩+comp 弹出 | 批准链：press 90 → 三钮 comp-out 140 → badge 交叠 micro 130 → steps stagger 60 → eta micro 出场 |
| 计划卡拒绝 | anticipate 收缩+comp 淡出 | 200ms | — |
| 检查点回滚 | in-soft | 200ms | 「后退用收缩到位感」 |
| 回滚后校验提示 | out-soft（narr 220） | 220ms | 「前进用入场缓动」 |
| 清单 stagger | — | 40ms 阶梯 | 封顶 160ms（既有令牌） |
| 任务态挂载 | aurora-op-focus | — | 极光加深一档，fx-off 停列 |
| 高风险档禁快捷确认 | 仅 press 90 | — | 不抢跑 |

## 四、移植纪律（铁律）

1. **UI 契约只增不改**：新 DOM id/class 纯增；既有 40 id/13 onclick/43 callApi/39 类/21 变量零改动
2. **令牌单一事实源**：新令牌两段式 `--{域}-{语义}`；JS 禁硬编码 ms（走 MOTION）
3. **降级三件套**：每个新动效注册 fx-off 停列 + prefers-reduced-motion + prefers-reduced-transparency；body.theming 白名单同步追加
4. **双主题**：所有新组件亮/暗双值（body.dark 镜像）
5. **平台差异化注入**：`body[data-platform="mac"]` 驱动（--font-ui/--scrollbar-w/--radius-ctrl/focus ring 宽度），Win 缺省即现行为——零 if 分支成本
6. **安全三重编码**：UNTRUSTED/哈希链/预算超限一律「色+形+字」三重编码，不靠单色传达语义
7. **移植顺序建议**：plan-card（M2.3-2.5）→ grant-budget（M2.4）→ ckpt（M2.7-2.8）→ audit-view（M2.6）→ brw-panel（M3.8/M5.7）→ mac 层（M6.10）——按后端里程碑就绪顺序

## 五、风险与注意（移交前后端）

1. **backdrop-filter 双端差异**：WebView2（Chromium）与 WKWebView 表现不一致——mac 端玻璃需实测（彩格调风险项），备选：mac 下 --glass-bg 不透明度提升补偿
2. **mac 字体注入时序**：SF 栈须早于首屏渲染（boot 前由 69-platform.js 设 data-platform）
3. **哈希链显示**：只显示首 8 位+省略号，禁长串全文（信息密度纪律）
4. **演示 dwell 常量**（stepDwell 900/autoDwell 3000/restoreDwell 1200/primDwell 650）为原型演示专用，移植不进产品代码；3s 自动批准徽标淡出是方案规格值需保留
