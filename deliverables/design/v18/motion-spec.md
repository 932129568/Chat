# Harbor v1.8.0「Agent 能力版」· 新增界面动效规格（v18）

**日期**：2026-10-20 · **基线**：v4 设计令牌（`deliverables/design/v4/port-spec.md`）+ v1.8.0 迭代方案 + Agent 自主能力调研
**定位**：本文档只规定**新增界面**的动效。视觉主题（精致静谧 · 玻璃 + 极光）、色彩令牌、排版、间距、阴影**全部沿用 v4，零新增令牌、零新色值**。
**消费方**：前端原型（ui-prototyper）与落地（ui-porter）。CSS 值一律引用 v4 变量；JS 一律走 `MOTION` 读变量，禁止硬编码时长。

---

## 0. 范围、基线 recap 与四律标注法

### 0.1 本文档覆盖的新增面

| 来源 | 新增面 |
|---|---|
| v1.8.0 迭代方案 | 搜索面板（结果列表 / 原文预览 / 人工接管）、软件设置面板（探测列表 / 状态灯 / 测试调用）、混合路由配置与会话头部分账、搜索缓存统计 |
| Agent 自主调研 | L2 任务授权指示灯 / 收回按钮、计划卡（步骤 checklist）、偏差暂停条、批量澄清表单、检查点 / 回滚入口 |

### 0.2 v4 四层动效模型（本规格的取层依据）

| 层 | 时长带 | 令牌 | 用途 |
|---|---|---|---|
| L0 微交互 | 90–130ms | `--dur-press:90ms` `--dur-micro:130ms` | hover / press / focus / 行内反馈 / 小圆点变色 |
| L1 组件 | 140–200ms | `--dur-comp-out:140ms` `--dur-comp:200ms` | 浮层 / 菜单 / chip / 表单 / 列表项 / 状态切换 |
| L2 页面 | 200–280ms | `--dur-narr:220ms` `--dur-panel:240ms` `--dur-panel-out:200ms` | 面板 / 模态 / 对话流内容 / 流级中断 |
| L3 氛围 | 1.4s–52s | `--dur-stream:1.4s` `--dur-breathe:2.6s` `--dur-sheen:6s` `--dur-ambient:34s/52s` | 循环呼吸 / 扫光 / 极光 |

### 0.3 v4 动效四律（每个规范点用标签注明依据）

- **【同】同源同速**——同一语义的动效全站同一组令牌（如"完成收敛"一律 `v4ToolSettle` 200ms；"进行中呼吸"一律 `--dur-breathe` 2.6s；spinner 一律 `--dur-stream` 1.4s）。
- **【层】一次只动一层**——同一时空只有一个运动层：容器动时内容不动，内容逐项动时容器已落定；状态切换 = 变色（200ms）不叠加位移。
- **【向】方向即信息**——自下方升起 = 内容取阅；自上切入 = 系统级打断；向左上撤 = 前进离场；列表项微沉 = 逐项落位。方向不允许随意。
- **【顶】stagger 封顶 240ms**——逐项入场总延迟 ≤240ms：`--stagger-xs:40ms` 最多连用 6 项（6×40=240），第 7 项起零延迟；`--stagger-sm:60ms` 用作层间基础延迟。

### 0.4 新组件通用家族规则（先于个体规范生效）

1. 所有可点击新元素挂静态标记 `.v4-h .v4-press`：hover 130ms `--ease-out-soft`（背景/文字/边/影/透明度），press 90ms scale（icon 档 `.94`，pill/ghost 档 `.97`）。【同】
2. 主 CTA（计划「批准」、回滚「确认」、接管「继续」）允许 focus/hover 发光——v4 发光白名单已登记"焦点 / 主 CTA hover / 流式条 / 品牌 logo"，新 CTA 不扩大范围。【同】
3. 一切退场走**显隐模式**：加 `.hiding` / `.out` → `MOTION.onAnimEnd(el,'animationend',MOTION.compOut())` 双兜底后移除类/DOM；禁止 `display:none` 瞬切。【同】
4. 新 DOM id/class **纯新增**，v4 既有 39 个契约 CSS 类、既有令牌零改动（迭代方案契约红线）。

---

## 1. 新组件动效规范表（15 行）

> 取层说明：表格中的时长全部是上表令牌；位移全部是 `--shift-*` 令牌（tip 4px / comp 6px / toast·msg 8px / panel 12px）。列表项微沉统一复用 v4 `v4CtxItemIn` 先例的 2px。

| # | 组件（类名） | 入场（时长 + 缓动 + 位移） | 出场 | 悬停 | 按压 | 状态切换 | 降级行为（fx-off / reduced-motion） |
|---|---|---|---|---|---|---|---|
| 1 | **搜索结果项** `.sp-item` | `v4SpItemIn`：opacity 0→1 + translateY(6px→0)，200ms `--dur-comp` `--ease-out-soft`；列表 stagger 40ms `--stagger-xs`，第 7 项起零延迟【同】【顶】 | opacity→0 + translateY(6px)，140ms `--dur-comp-out` `--ease-in-soft`（进出对称）【同】 | background-color→`--hover`，130ms `--dur-micro`（v4-h 家族）【同】 | scale(.98)，90ms `--dur-press` | 骨架 `.sp-item.skel`→内容：停 shimmer（`::after{animation:none}`），内容项按入场规则落位；已 hover 项被点开原文时底色保持不变、不叠加第二层动画【层】 | fx-off：1ms 瞬时 + stagger 归零；骨架 shimmer 进 fx-off 显式停列（§4.3） |
| 2 | **原文预览浮层** `.sp-prev`（+ `.sp-prev-mask`） | 遮罩 opacity 0→1，200ms `--dur-comp` `--ease-out-soft`（复用 `v4MaskIn`）；浮层 opacity 0→1 + translateY(12px→0)，240ms `--dur-panel` `--ease-out-soft`——自下方升起 = 正文从"下面"取阅【同】【向】 | 遮罩 140ms `--dur-comp-out`；浮层 opacity→0 + translateY(12px)，200ms `--dur-panel-out` `--ease-in-soft`（对称撤回）【同】 | 关闭按钮 v4-h 130ms；正文内链 color 130ms | 关闭 scale(.94)，90ms `--dur-press`（icon 档） | 加载中→正文到达：骨架区 opacity 1→0 与正文 opacity 0→1 **同时反向 200ms**（一次交叉淡化，只动 opacity）【层】 | fx-off：瞬时显隐；reduced-transparency：浮层背景→`--glass-fallback` 不透明、遮罩去 blur（v4 既有规则扩展到新浮层） |
| 3 | **人工接管面板** `.sp-take`（+ 引导标注 `.sp-take-guide`） | 面板：opacity 0→1 + translateY(-6px→0)，200ms `--dur-comp` `--ease-out-soft`（复用 `v4SetIn` 同档：设置族浮层同源）【同】；引导：opacity + scale(.9→1)，200ms `--ease-spring`（对齐 modal-card 弹簧档）【同】 | 140ms `--dur-comp-out` `--ease-in-soft`，translateY(-6px) | 「继续」按钮 v4-h 130ms | scale(.97)，90ms `--dur-press`（pill 档） | 引导常驻 attention pulse：opacity .55↔1，2.6s `--dur-breathe` infinite（与 tool-call-item doing 态同代）【同】；点「继续」后 guide opacity→0 + translateY(-4px)，140ms `--dur-comp-out` | fx-off / reduced-motion：pulse 进显式停列（§4.3），引导静止显示；spring 被全局 .01ms 覆盖为直显 |
| 4 | **软件探测状态灯** `.sw-light`（8px 圆点；probing 时带外环 `.sw-ring`） | 行入场：opacity 0→1 + translateY(6px→0)，200ms `--dur-comp` `--ease-out-soft`；探测列表批量刷新时第 7 行起零延迟【同】【顶】 | 140ms `--dur-comp-out`，translateY(6px) | 行 background-color→`--hover` 130ms；灯无独立 hover | 「测试」按钮走家族档 | **五态**：未知 = `--text-3` 静态；探测中 = `--primary` + scale(.8→1) & opacity(.45→1) pulse，1.4s `--dur-stream` infinite（与 tool-spinner 同代：探测是短时活动态，比 breathe 更即时）【同】；已装 = `--ok` 静态 + 一次性 settle（box-shadow 环扩散→0，200ms `--dur-comp`，`v4ToolSettle` 同款）【同】；未装 = `--text-3` 空心（仅 border）静态——**未装不是错误，不用 err**；版本不符 = `--warn` 静态（循环只留给"进行中"）。态间切换 = background-color/border-color/box-shadow 200ms `--dur-comp` `--ease-out-soft`（与 tool-call-item 三态同源同速）【同】 | fx-off / reduced-motion：probing pulse 显式停→静态 `--primary` 点；settle 被 1ms 变量覆盖自然跳过；**五态配色不降级**（语义优先） |
| 5 | **测试调用回显** `.sw-test`（输出区 `.sw-out` / 行 `.sw-line` / 退出码徽标 `.sw-exit`） | 输出区：opacity 0→1 + translateY(4px→0)，200ms `--dur-comp` `--ease-out-soft` | 140ms `--dur-comp-out` | 输出区可复制按钮 v4-h 130ms | 测试按钮 scale(.97) 90ms | 回显行逐行：opacity 0→1 + translateY(4px→0)，130ms `--dur-micro` `--ease-out-soft`——行是输出流的一部分走 L0，**禁 stagger**（节奏由数据驱动不由编排驱动）【层】；退出码徽标 ok/err 变色 200ms `--dur-comp` + 一次性 settle flash 200ms（同 `.sw-light` 已装）【同】 | fx-off：行 1ms 落位、徽标直接终色；reduced-motion 同行 |
| 6 | **会话头部分账 chip** `.hy-chip` | opacity 0→1 + translateY(4px→0)，200ms `--dur-comp` `--ease-out-soft`——头部元素自上而下落入、向头部位置收敛【向】 | opacity→0，140ms `--dur-comp-out` | chip 底色 130ms + tooltip 130ms（`v4TipIn` 同款） | 若可展开分账详情：scale(.97) 90ms | 数字更新：count-up 600ms `--dur-count`，JS 走 `MOTION.count()` + `MOTION.easeOutSoft`（与 analytics 数字滚动同源同速）【同】；本地/云端占比变化时 chip 内 segment 底色 200ms `--dur-comp` | fx-off：数字直显终值；reduced-motion：JS `prefersReduced()` 分支瞬时终值（78-analytics 既有先例） |
| 7 | **本地/云端路由指示点** `.hy-dot` | 随 chip 一同入场（同一 200ms 组，不另起一层）【层】 | 随 chip 140ms | tooltip 130ms（`v4TipIn`） | 无（非按钮） | 路由切换：background-color 200ms `--dur-comp` `--ease-out-soft` + 一次性 ping（`::after` scale(1→1.9) + opacity(.5→0)，200ms `--dur-comp` `--ease-out-soft`；transform+opacity 白名单内）【同】。语义：本地 = `--ok`，云端 = `--primary`，云端接管（降级）= `--warn` + ping | fx-off：ping 被 1ms 覆盖跳过；reduced-motion 同行；配色不降级 |
| 8 | **L2 授权指示灯** `.gr-light`（+ 倒计时环 `.gr-ring`） | 授权获得：opacity 0→1 + scale(.9→1)，200ms `--ease-spring`（获得授权是"确认级"事件，对齐 modal 弹簧档）【同】 | 收回：灯灰化（→`--text-3`）200ms `--dur-comp`；环 scale(.9→0)+opacity→0，140ms `--dur-comp-out` `--ease-in-soft` | tooltip（TTL 剩余）130ms | 无 | **呼吸**：opacity .88↔1，2.6s `--dur-breathe` infinite（授权中 = 任务级"进行中"，与 tool-call-item doing 态同源同速）【同】；**禁止发光**（常驻指示灯不在 v4 发光白名单）。**倒计时环**：SVG circle `stroke-dashoffset`，`transition:stroke-dashoffset 1s linear`——时钟语义每秒一跳，非装饰动画、不占动效令牌；stroke 族 paint-only 属性（与 v4 主题白名单中 fill/stroke 同族）、零 rAF。TTL 剩 5 分钟：stroke 色→`--warn`，200ms `--dur-comp` | fx-off：呼吸显式停→静态 primary 点；reduced-motion：环 transition 被全局 .01ms 覆盖→**每秒离散跳变**（天然降级仍可读剩余时间）；配色不降级 |
| 9 | **收回授权按钮** `.gr-revoke` | 随授权灯同组入场（不另起层）【层】 | — | v4-h 130ms；hover 时 color→`--err`（破坏性 secondary 用 err 文字而非红底，警示但不恐吓）【向】 | scale(.97)，90ms `--dur-press` | 点击：文案「收回授权」→「已收回」+ color→`--text-3`，200ms `--dur-comp`；`gr-light` 同步灰化（§1-8 出场规则） | fx-off：文字/色 1ms 切换 |
| 10 | **计划卡** `.plan-card`（含徽标 `.plan-badge`） | opacity 0→1 + translateY(8px→0)，220ms `--dur-narr` `--ease-out-soft`——对话流内容一律 narr + `--shift-msg`，与 message 同源同速【同】 | 完成后转摘要：opacity→.55，200ms `--dur-comp`（内容沉淀退后让位，不移除 DOM）【向】 | 卡片无整卡 hover（非按钮） | 「批准」主 CTA：scale(.97) 90ms + 允许 hover/focus 发光 | 待批准徽标 = `--warn-bg`/`--warn`；批准后 →`--primary-soft`/`--primary`（执行中），200ms `--dur-comp`【同】；批准动作：操作行 opacity→0，140ms `--dur-comp-out` 淡出后 `display:none`（显隐模式，不挤占卡片），**卡片本身不动**【层】；编辑态开关：增删步骤控件 fade 140ms | fx-off：瞬时；徽标/摘要变色 1ms |
| 11 | **计划步骤 / todo 五态** `.plan-step` | 逐项：opacity 0→1 + translateY(-2px→0)，200ms `--dur-comp` `--ease-out-soft`（复用 `v4CtxItemIn` 位移先例）；基础延迟 60ms `--stagger-sm` 等卡片落定，stagger 40ms `--stagger-xs`，第 7 项起零延迟【层】【顶】 | 步骤被删：opacity→0 + translateY(-2px)，140ms `--dur-comp-out` | 行 background-color→`--hover` 130ms | scale(.99)，90ms `--dur-press`（行可点击展开详情时；纯展示行无按压，步骤内按钮走家族档） | **五态**：pending = `--text-2` 静态；doing = `--primary` + spinner 1.4s `--dur-stream`（复用 `v4Spin`）；done = `--ok` + 打勾 pop；blocked = `--err` 静态 + 图标（不循环）；skipped = `--text-3` + opacity .7 静态。**打勾动画** `.plan-check`：scale(.4→1) + opacity 0→1，200ms `--ease-spring`（modal 同弹簧档）【同】；同步步骤文字 color→`--text-3` 200ms（done 文字降权）。doing→done：停 spinner + 打勾 pop + 行底 settle flash 一次 200ms（`v4ToolSettle` 同款）【同】 | fx-off：打勾直显终态（spring 被 1ms 覆盖）；reduced-motion：spinner 静止为静态弧 + 文案表意（v4 既有"功能优先"规则延续）；五态配色不降级 |
| 12 | **偏差暂停条** `.dev-bar` | `v4DevIn`：opacity 0→1 + translateY(-12px→0)，240ms `--dur-panel` `--ease-out-soft`——L2 流级事件；自上方切入 = 来自系统层的打断【同】【向】 | opacity→0 + translateY(-12px)，200ms `--dur-panel-out` `--ease-in-soft`（向上撤回，对称）【同】 | 条内按钮 v4-h 130ms | scale(.97) 90ms | **高亮闪烁一次** `v4DevFlash`：box-shadow `0 0 0 1px --err, 0 0 14px -4px --err`→0，200ms `--dur-comp` `--ease-out-soft`，播放一次不循环（`v4ToolSettle` 同款；一次即停避免持续干扰）【同】；闪烁后保持 `--err-bg` 静态底 | fx-off：滑入瞬时、闪烁跳过；reduced-motion 同行；**保留 err 静态配色**（拦截语义不降级） |
| 13 | **澄清表单** `.clr-form`（题目 `.clr-q` / 选项 `.clr-opt`） | 表单：opacity 0→1 + translateY(8px→0)，220ms `--dur-narr` `--ease-out-soft`（对话流 narr 档），延迟 60ms `--stagger-sm` 跟在 Agent 提问消息后【同】【层】 | 提交后：已回答题目 opacity→.55，200ms `--dur-comp`；表单整体 opacity→0 + translateY(6px)，140ms `--dur-comp-out` 后移除 | 选项 v4-h 130ms | scale(.97) 90ms | 题目错落：每题 opacity 0→1 + translateY(6px→0)，200ms `--dur-comp`；stagger 40ms——协议上限 5 题，5×40=200ms **整表落在 240ms 封顶内**【顶】；选项选中：background-color→`--primary-soft` + border-color/color→`--primary`，200ms `--dur-comp`【同】 | fx-off：瞬时；表单为 inline 不遮罩对话流（布局不随降级变化） |
| 14 | **检查点快照进度** `.ckpt-prog`（条 `.ckpt-bar` / 填充 `.ckpt-fill` / 计数 `.ckpt-count`） | 随计划批准后落定出现：opacity 0→1 + translateY(6px→0)，200ms `--dur-comp` | 完成：整条 opacity→0，140ms `--dur-comp-out`（600ms `--dur-count` 延迟后，对齐 count-up 收尾节奏）【同】 | 无 | 无 | 不确定进度：扫光 transform translateX(-100%)→100%，1.4s `--dur-stream` linear infinite（与 stream-bar 同源同速）【同】；确定进度：`.ckpt-fill` transform:scaleX(p)（origin left），每次更新 200ms `--dur-comp`——**transform 实现进度条，零布局动画**【同】；文件计数每次更新：数字 opacity .5→1 一次，130ms `--dur-micro`【同】；完成：条→`--ok` 实心 200ms + settle flash 一次 200ms；超限降级（仅记录 diff 清单）：条→`--warn` 200ms + 文案 cross-fade 200ms（opacity） | fx-off：扫光显式停→静态 primary 条；进度直显终值；reduced-motion 同行 |
| 15 | **回滚确认清单** `.ckpt-list`（模态内，行 `.ckpt-row`） | 模态：遮罩 `v4MaskIn` 200ms + 卡片 `v4ModalIn` 200ms `--ease-spring`（v4 既有模态编排原样复用）【同】 | 模态：遮罩 140ms + 卡片 `v4ModalOut` 140ms `--dur-comp-out` `--ease-in-soft`；完成时同步 toast ok 200ms 右侧入场（`--shift-toast`） | 行 v4-h 130ms（可展开 diff 预览） | 「确认回滚」scale(.97) 90ms | 清单项错落：opacity 0→1 + translateY(-2px→0)，200ms `--dur-comp`；stagger 40ms，第 7 项起零延迟【顶】；**inline 二次确认**（禁模态叠模态）【层】：确认钮首击 = 文案→「再次点击确认」+ color→`--err`，200ms `--dur-comp`；3s 内二击执行，超时复原 200ms；执行中：行内 spinner 1.4s，逐行 restored = `--ok` + settle flash 200ms / failed = `--err` + `--err-bg` 200ms `--dur-comp`【同】 | fx-off：模态瞬时显隐、行状态直显；**二次确认的 3s 超时计时保留**（功能不降级）；reduced-motion 同行 |

---

## 2. 关键交互的动画编排

### 2.1 Agent 长任务等待态——「可见的等待」（核心机制）

**设计命题**：源文档要求禁止静默黑箱。机制 = **阶段文案 + 骨架屏 + 确定/不确定进度 + 心跳提醒**四件套，全部落在既有令牌上，零新增长循环。

**舞台道具**（新类名见 §5）：

- `.wait-stage` 阶段 pill：spinner（复用 `v4Spin` 1.4s）+ 阶段文案 + 进行中省略号。
- `.wait-skel` / `.wait-line` 骨架：3 行静态宽度（92% / 78% / 64%），`::after` 渐变扫光复用 `toolSheen`（transform translateX，6s `--dur-sheen`）。
- `.wait-prog` 确定进度条：`.wait-prog-fill` scaleX(p)（§1-14 同款）。
- `.wait-note` 次级行：长阶段心跳提醒。

**反馈节奏五律（pacing，非动效令牌）**：

| # | 规则 | 值 | 理由 |
|---|---|---|---|
| P1 | 首反馈时限 | 任务开始后 1 个 micro（130ms）内 pill 入场（200ms 动画播完） | 禁止 >130ms 白屏启动；130ms 是人感知"即时"的上限【同】 |
| P2 | 阶段最短展示 | 400ms | 快阶段合并展示，防文案闪烁（pacing 常量，与 `STREAM_PACE` 同类） |
| P3 | 阶段切换 | 旧文案 opacity→0 140ms `--dur-comp-out`，新文案 opacity 0→1 + translateY(2px→0) 200ms `--dur-comp`；**spinner 不重启** | 循环动画重置会造成闪动；一次只换一层（文案）【层】【同】 |
| P4 | 心跳 | 任一阶段 ≥5s 无事件 → `.wait-note`「仍在进行，可随时查看日志」+ 省略号 opacity 呼吸 2.6s `--dur-breathe`；≥15s → 追提示（不弹窗） | 最慢阶段也有活体反馈；呼吸与 doing 态同代【同】 |
| P5 | 取消即停 | 点「停止」→ 等待态 140ms 淡出，spinner/呼吸/扫光全停（§4.3 显式列表） | 停止必须干净，禁残留循环 |

**阶段表（搜索任务；软件/本地推理同构替换）**：

| 阶段 | 文案 | 预算 | 反馈形式 | 超时/异常反馈 |
|---|---|---|---|---|
| 1 理解意图 | 正在理解任务意图 | 本地 ≤5s | pill + 骨架 | ≥5s：文案追「本地响应偏慢，即将切换云端」+ 省略号呼吸 |
| 2 构造检索式 | 正在构造检索式 | 含于 5s | 文案 cross-fade | — |
| 3 打开搜索窗口 | 正在打开受控浏览器 | ≤8s | pill + 不确定进度扫光 | ≥8s：自动切 urllib 兜底，文案「已切换轻量抓取」 |
| 4 提取结果 | 正在提取搜索结果 | <1s | 骨架逐项替换为 `.sp-item` | 空结果：校验重试「结果不理想，正在改写检索式重试（1/2）」 |
| 5 深度提取 | 正在读取正文（3/10） | Top N 逐页 | 确定进度 scaleX + 计数微闪 | 单页超时：跳过该项、计数继续、完成时汇总「2 页读取失败」 |
| 6 本地校验 | 正在校验结果 | ≤3s | pill | 置信 <0.7：升级云端复核，文案转 `--warn`（降级字典 §3） |
| 7 完成 | 搜索完成 | — | pill →`--ok` 200ms，600ms 后淡出 | — |

软件任务：探测中（`.sw-light` probing 态）/ 执行中（沙箱 timeout 5–600s：不确定扫光 + 「已运行 0:42」时钟文本每秒 +1，**时钟不走 count-up 动画**）/ 收尾（`.sw-test` 回显）。

### 2.2 计划卡批准前后的过渡

1. **落定**：计划卡 narr 220ms 入场 → 步骤基础延迟 60ms 后逐项 stagger（§1-10/11）。
2. **批准点击**：按钮 press 90ms → 徽标 待批准(warn)→执行中(primary) 200ms → 操作行 140ms 淡出移除 → **第一个 doing 步骤起 spinner**。全程卡片本身不动，四步串行同一时序链（每步等上一步 end，JS 用 `MOTION.onAnimEnd` 衔接），任何时刻只有一层在动【层】。
3. **拒绝**：卡片 140ms `--dur-comp-out` 淡出上移（--shift-comp），用户消息 narr 220ms 入场（对话流继续）。
4. **编辑**：卡片进编辑态：步骤行内控件 fade 140ms 逐项（stagger 40ms 封顶 240ms），「+ 添加步骤」行同规则入场；保存即回到待批准徽标。

### 2.3 澄清表单与对话流的衔接

1. Agent 提问消息 narr 220ms 入场（对话流既有规则）。
2. 60ms（`--stagger-sm`）后 `.clr-form` 滑入（§1-13），题目 stagger 40ms——**表单是 inline 不是模态**，上方对话保持可滚动可交互【层】。
3. 提交：已回答题目 opacity→.55 沉淀 200ms → 表单 140ms 淡出 → 用户答案以消息 narr 220ms 入场 → 「正在生成计划」等待态（§2.1）→ 计划卡 narr 220ms。五个beat 总时序 ≈ 220+60+200+140+220+220+220 ≈ 1.3s，一步一停、层层交接【层】。

### 2.4 回滚清单二次确认的模态编排

1. **入口**：计划卡「回滚到此任务前」按钮或完成摘要回滚链接触发 → 遮罩 `v4MaskIn` 200ms + 卡片 `v4ModalIn` 200ms spring（v4 既有模态编排原样复用，遮罩与卡片同属 L2 同时运动是既有登记模式）【同】。
2. **清单**：`.ckpt-row` 逐项 200ms + stagger 40ms（第 7 项起零延迟）；超 10 项显示「等 N 个文件」汇总行（不无限拉长模态）【顶】。
3. **inline 二次确认**：确认钮首击 → 文案「再次点击确认」+ color→`--err` 200ms；3s 内二击执行，超时复原。**不叠第二层模态**【层】。
4. **执行**：模态不关（遮罩不动），行内 spinner 1.4s，逐行 restored(ok + settle flash)/failed(err) 200ms；全部完成 → 模态 140ms 退场 + toast ok 200ms。
5. **取消**：Esc / 点遮罩 → 140ms 退场，零副作用。

---

## 3. 状态反馈视觉字典

> 色彩全部取自 v4 既有语义令牌（`--primary` / `--ok` / `--warn` / `--err` 及 `--*-bg`），**零新色**。图标沿用 v4 内联 SVG 风格（stroke=currentColor，1.7 宽，圆帽圆角）。

| 状态 | 色彩令牌 | 图标 | 动效 | 典型载体 |
|---|---|---|---|---|
| **进度**（indeterminate） | `--primary` | 旋转弧 / 扫光条 | 1.4s `--dur-stream` 循环（spinner/stream/sweep 同代）【同】 | `.wait-stage`、`.sw-light.probing`、`.ckpt-bar` 不确定态、既有 `.stream-bar` |
| **成功** | `--ok` / `--ok-bg` | ✓ 勾 | 一次性 settle flash 200ms（`v4ToolSettle` 同款）后静态【同】 | `.plan-step.done` 打勾、`.sw-light.installed`、`.ckpt-prog` 完成、`.sw-exit` ok |
| **失败** | `--err` / `--err-bg` | ! / ✕ | **静态无循环**（失败不是活动态；持续闪动=骚扰） | `.sw-test` 退出码、`.plan-step.blocked`、`.ckpt-row.failed`、既有 `.tool-call-item.fail` |
| **降级**（云端接管） | `--warn` / `--warn-bg` | ↓ 云形箭头 | 一次 pulse 200ms 后静态（注意但继续，不阻断）【同】 | `.hy-dot.degraded`、阶段 6 升级复核文案、`.ckpt-prog` 超限降级 |
| **拦截**（deny） | `--err` / `--err-bg` | 盾 + ! | 一次 flash 200ms 后静态（`v4DevFlash` 同款；比失败多一次"撞击"强调硬边界）【同】 | `.dev-bar`、guard 拦截回传、危险按钮 hover 文字 |
| **等待用户** | `--warn` / `--warn-bg` | 手 / 暂停符 | breathe 2.6s（活体等待：球在用户方，轻呼吸表意不报警）【同】 | `.clr-form` 待答、`.gr-light` 授权中、计划卡待批准徽标 |

**状态切换通则**：任何状态迁移 = 颜色族 200ms `--dur-comp` `--ease-out-soft`；"到达成功/失败终态"额外附加**一次** 200ms settle/flash；循环动画只属于"进行中 / 等待"两类，成功/失败/拦截终态一律静态【同】【层】。

---

## 4. 性能与降级红线

### 4.1 动效白名单（新动效全部落在内）

- **允许**：`transform`（translate/scale/rotate）、`opacity`、颜色族（`background-color` / `color` / `border-color` / `box-shadow` / `fill` / `stroke`）。
- **登记扩展**：`stroke-dashoffset`——仅限 `.gr-ring` 倒计时环，`transition` 1s linear 每秒一跳（时钟语义），paint-only、无 rAF；与 v4 主题白名单中的 fill/stroke 同族。
- **既有登记例外**（v4 保留，新代码不得扩大）：`.sidebar` 折叠的 `margin-left`。
- **禁止**：`transition:all`；`width` / `height` / `top` / `left` / `right` / `bottom` / `margin`（登记例外外）/ `padding` / `font-size` 的过渡与 keyframes；JS 逐帧写样式（确定进度一律 scaleX，环一律 CSS transition）；`@keyframes` 内出现白名单外属性。

### 4.2 `will-change` 纪律

- 只在动画开始前加、`animationend`/`transitionend` 后移除（v4 `.stream-bar.on` 模式）；禁止常驻。
- **列表项一律不加**：`.sp-item` / `.plan-step` / `.ckpt-row` / `.sw-row`（长列表，累计提升开销）。
- 同屏同时挂 `will-change` 的元素 ≤3。

### 4.3 fx-off 显式停列（新增部分，追加进 v4 既有 fx-off 块）

变量级降级（`--dur-*:1ms`、`--stagger-*:0ms`）对 infinite 无效，以下新循环必须显式 `animation:none`：

```css
body.fx-off .sw-light.probing,      /* 探测 pulse */
body.fx-off .gr-light,              /* 授权呼吸 */
body.fx-off .wait-skel::after,      /* 骨架扫光 */
body.fx-off .wait-prog,             /* 不确定进度扫光 */
body.fx-off .wait-dot,              /* spinner（与 v4Spin 同规则） */
body.fx-off .sp-take-guide{animation:none}   /* 引导 pulse */
```

### 4.4 完整降级矩阵

| 组件/机制 | fx-off（用户手动关特效） | prefers-reduced-motion | prefers-reduced-transparency |
|---|---|---|---|
| 全部 transition/animation | 令牌 1ms / stagger 0 → 瞬时 | 全局 .01ms + iteration-count 1 | 不涉及（仅玻璃） |
| spinner / 扫光 / 呼吸 / pulse | 显式停（§4.3） | 静止为静态弧 / 静态条（功能优先，文案表意） | — |
| 倒计时环 `.gr-ring` | stroke-dashoffset 1ms → 直显剩余比例 | transition .01ms → 每秒离散跳变（仍可读） | — |
| count-up 数字 | 1ms → 终值 | JS `prefersReduced()` → 瞬时终值 | — |
| `.sp-prev` / `.sp-take` 玻璃面 | 不涉及 | 不涉及 | 背景→`--glass-fallback` 不透明；遮罩去 blur |
| 二次确认 3s 计时、TTL 计时 | **保留**（功能不降级） | **保留** | — |
| 五态/语义配色 | **保留** | **保留** | **保留** |
| 流式条 | 循环保留仅去微光（v4 既有三不变延续） | 循环保留仅去微光 | — |

### 4.5 其他红线

- 新 DOM id/class 纯新增；v4 既有 39 契约类、既有令牌、既有 keyframes 名零改动。
- 退场一律显隐模式 + `MOTION.onAnimEnd` 双兜底；禁 `display:none` 瞬切。
- 无限循环动画总清单（含既有）：aurora ×2、tool-call breathe/sheen、stream-bar、typing-dots、spinner、sw-light pulse、gr-light breathe、wait-skel sheen、wait-prog sweep、sp-take-guide pulse——fx-off 块必须逐一显式停。
- 长列表（>20 项）：第 7 项起已零延迟；不得加 `content-visibility` 之外的非常规优化（保持零依赖）。

---

## 5. 组件 CSS 类命名建议（与 v4 既有风格一致）

> 既有风格基线：`cs-*`（自定义下拉）/ `set-*`（设置）/ `msg-*`（消息）/ `ws-*`（工作区）/ `tc-*`（工具卡内部）/ `tool-call-item` / `session-item` / `attach-item`。新前缀按面板域划分，两段式小写连字符。

### 5.1 类名清单

| 前缀域 | 类名 |
|---|---|
| `sp-` 搜索面板 | `.sp-panel` `.sp-head` `.sp-item`（+ 态 `.skel`）`.sp-skel-line` `.sp-count` `.sp-prev` `.sp-prev-mask` `.sp-prev-body` `.sp-take` `.sp-take-guide` `.sp-take-arrow` |
| `wait-` 可见等待（跨任务通用） | `.wait-stage` `.wait-dot` `.wait-text` `.wait-note` `.wait-cancel` `.wait-skel` `.wait-line` `.wait-prog` `.wait-prog-fill` |
| `sw-` 软件面板 | `.sw-row` `.sw-light`（态 `.probing` `.installed` `.missing` `.mismatch`）`.sw-ring` `.sw-test` `.sw-out` `.sw-line` `.sw-exit` `.sw-add` |
| `hy-` 混合路由 | `.hy-chip` `.hy-chip-num` `.hy-dot`（态 `.local` `.cloud` `.degraded`）`.hy-cfg` `.hy-stat` |
| `gr-` L2 授权 | `.gr-light` `.gr-ring` `.gr-revoke` `.gr-ttl` |
| `plan-` 计划卡 | `.plan-card` `.plan-head` `.plan-badge`（态 `.pending` `.running`）`.plan-steps` `.plan-step`（态 `.pending` `.doing` `.done` `.blocked` `.skipped`）`.plan-check` `.plan-acts` `.plan-approve` `.plan-edit` `.plan-reject` `.plan-rollback` `.plan-summary` |
| `dev-` 偏差暂停 | `.dev-bar` `.dev-bar-title` `.dev-bar-act` |
| `clr-` 澄清表单 | `.clr-form` `.clr-q` `.clr-opt`（态 `.on`）`.clr-default` `.clr-acts` `.clr-submit` |
| `ckpt-` 检查点/回滚 | `.ckpt-prog` `.ckpt-bar` `.ckpt-fill` `.ckpt-count` `.ckpt-list` `.ckpt-row`（态 `.restoring` `.restored` `.failed`）`.ckpt-more` |

### 5.2 新增 keyframes 清单（命名延续 v4XxxIn/Out 惯例）

| keyframes | 属性 | 复用/参照 |
|---|---|---|
| `v4SpItemIn` / `v4SpItemOut` | opacity + translateY | 新建（对齐 v4MsgIn 家族） |
| `v4PrevIn` / `v4PrevOut` | opacity + translateY(±12px) | 遮罩复用 `v4MaskIn` |
| `v4TakeIn` / `v4TakeOut` / `v4GuideIn` | opacity + translateY/scale | 对齐 `v4SetIn` / `v4ModalIn` |
| `v4LightPulse` | scale + opacity | 新建（probing 1.4s） |
| `v4TestAreaIn` / `v4TestLineIn` | opacity + translateY | 对齐 `v4AttachItemIn` |
| `v4ChipIn` | opacity + translateY(4px) | 新建 |
| `v4DotPing` | ::after scale + opacity | 新建 |
| `v4GrIn` / `v4GrRingOut` | opacity + scale | 对齐 `v4ModalIn` |
| `v4PlanStepIn` | opacity + translateY(-2px) | 参照 `v4CtxItemIn` |
| `v4CheckPop` | scale(.4→1) + opacity | 新建（spring 200ms） |
| `v4DevIn` / `v4DevOut` / `v4DevFlash` | opacity + translateY / box-shadow | flash 参照 `v4ToolSettle` |
| `v4ClrIn` / `v4ClrQIn` / `v4ClrOut` | opacity + translateY | 对齐 `v4MsgIn` |
| `v4WaitTextIn` / `v4WaitTextOut` | opacity + translateY(2px) | 新建 |
| 复用不改名 | `v4MaskIn` `v4ModalIn` `v4ModalOut` `v4ToastIn` `v4TipIn` `v4Spin` `v4Stream` `v4ToolSettle` `v4ToolBreathe` `toolSheen` | v4 既有 |

### 5.3 落地集成点（ui-porter  checklist）

1. 所有可点击新元素挂 `.v4-h .v4-press`（§0.4）。
2. `body.theming` 主题白名单（port-spec §2.16）追加新表面类：`.sp-item,.sw-row,.plan-card,.plan-step,.dev-bar,.clr-form,.clr-opt,.ckpt-row,.hy-chip,.wait-stage,.sp-prev,.sp-take,.gr-light,.gr-ring,.wait-skel`。
3. fx-off 块追加 §4.3 显式停列；reduced-motion / reduced-transparency 块按 §4.4 扩展。
4. JS 零硬编码时长：新模块一律 `MOTION.comp()/compOut()/panel()/panelOut()/narr()/count()/staggerXs()/staggerSm()/onAnimEnd()/instant()/prefersReduced()`——**零新 MOTION API**。
5. `check_contract.py` 预期 PASS（新类纯新增）；`grep -rn "transition:all" frontend/` 预期无输出。

---

## 6. 自检记录（彩格调 · 2026-10-20）

| 检查项 | 方法 | 结果 |
|---|---|---|
| 禁 `transition:all` | 全文 grep | 通过（0 处） |
| 禁布局属性动画 | 全文 grep `transition:.*(width\|height\|margin\|padding\|top\|left)` 及 keyframes 属性扫描 | 通过（0 处；margin-left 仅以文字提及 v4 既有登记例外，无新声明） |
| 零新色值 | 全文 grep HEX `#` | 通过（0 处；色彩全部 `var(--ok/--warn/--err/--primary/--text-*)`） |
| stagger ≤240ms | 逐条核对 stagger 用法 | 通过（最多 6×40ms；澄清表单 5×40=200ms） |
| 动效全落白名单 | 逐条核对 keyframes/transition 属性 | 通过（transform/opacity/颜色族 + 登记的 stroke-dashoffset 时钟） |
| fx-off 对 infinite 显式停 | §4.3 停列对照 §4.5 循环总清单 | 通过（10/10 覆盖，含既有 5 项点名） |
| 零新增动效令牌 | 对照 v4 令牌表 | 通过（仅引用既有 `--dur-*`/`--ease-*`/`--shift-*`/`--stagger-*`） |
| 四律标注完整 | §1 表格 + §2 编排逐条核对 | 通过（每条规范带【同】【层】【向】【顶】标签） |
