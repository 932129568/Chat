# Harbor v1.9.0 设计令牌升级方案（彩格调 · Design System Expert）

**定位**：v4 玻璃拟态 + 编辑部排版体系内增量升级；双端一套令牌、平台差异化注入；UI 契约只增不改；审美基准 WorkBuddy，品牌蓝 #4560e0 不变。

## 1. 色彩与氛围升级

**沉浸感（新令牌，亮/暗双值）**

| 令牌 | 值（亮 / 暗） | 用途 |
|---|---|---|
| `--aurora-5` | rgba(69,96,224,.10) / .18 | 品牌蓝第 5 光斑，与既有 2 可见斑（青/紫）构成 3 斑漂移；品红斑已退役（display:none）；新界面挂载时淡入 |
| `--aurora-op-focus` | .18 / .26 | 计划卡/检查点等任务态挂载期间极光加深一档（fx-off 停列） |
| `--edge-hi-strong` | inset 0 1px 0 rgba(255,255,255,.9) / .10 | 模态玻璃受光边第三档，仅模态白名单可用 |
| `--bg-deep` | #0d0f16 / #07080d | 暗色夜态窗口外圈环境色，强化"悬浮于夜"的沉浸 |
| `--skylight-strength` | .5 / .7 | 聊天天光纱，增强计划卡区域渗透 |

glow 白名单新增两类：计划卡批准钮 hover、授权条收回钮（均品牌蓝，禁扩散）。暗态 `--aurora-bg-opacity` 维持 .62（模板 2026-10-21 夜态沉浸已上调约 25%，方案初稿表述滞后）。

**安全信任色**：`--untrusted:#8f5a0a/#fbbf24`（复用已校准 warn 值）+ `--untrusted-bg`。UNTRUSTED 内容 = 琥珀 45° 斜纹边 + mono caption「来源：…」，语义=内容可信度，区别于 err（操作失败）；`--prov-line` 1px 虚线 + 4px 节点圆点表审计哈希链，断链转 err。铁律：色 + 形 + 字三重编码，不靠单色传达安全语义（对比度 ≥4.5）。

## 2. UI 层级与组件规范

命名延续 v4：`plan-/ckpt-/brw-/grant-/mac-` 前缀；复用 `pill-btn / plan-badge / plan-step` 五态 / `risk l0|l2`。

1. **Intent Preview 计划卡**（`.plan-card` 升级）：头部 badge + 标题 + `.plan-eta` 徽标（mono「≈3 步·2 分钟」）；步骤 checklist 复用五态；`.plan-riskbar` 卡左侧 3px 风险色条（取最高步骤风险）；`.plan-scope` 边界声明区（dashed 边框，「将修改 / 不访问」）；三钮：批准 primary+glow / 编辑 ghost / 拒绝 err-soft；`.plan-ctx` 累计上下文（mono 62% 细进度条）。**L2 全 low 自动批准态** `.plan-auto`：ok 徽标「已自动批准·授权范围内」，3s 淡出。
2. **检查点对话框**（inline 卡，禁模态叠模态）：清单态 `.ckpt-list`（stagger 40 逐项入场）→ 确认态（`.plan-rollback` 回滚链接 + 确认钮）→ 校验态 `.ckpt-verify`（ok/err 行 +「已恢复至检查点 N」）。
3. **浏览器驱动面板**：`.brw-mode` 可见/隐藏切换（spring 滑块形变 200ms）；`.brw-row`×6 六原语状态行（12px 点：ok 待命 / warn 运行 / err 失败）；`.brw-takeover` 反爬接管卡（warn 边 + 1.4s 脉冲点，「需手动完成验证」）。
4. **审批预算指示器**：授权条内 `.grant-budget` mono「审批 3/5」+ 5 格 dot；超限 `.grant-budget.over` 转 err「已达上限，需显式批准」+ 一键收回钮（glow hover）。
5. **macOS 适配层**：`body[data-platform="mac"]` 驱动差异化注入——`--font-ui` 注入 `-apple-system,BlinkMacSystemFont,"SF Pro Text"`；`--scrollbar-w` Win 10px（现行值不变）/ mac 0（hover 显形 8px overlay）；`--radius-ctrl` Win 6px / mac 8px（mac 控件略圆，Win 与既有 `--radius-sm:6px` 对齐）；focus ring mac 双环 3px primary-soft vs Win 2px；`.mac-kbd` 键位提示（⌘K / Ctrl+K 双映射）；`.mac-badge` 平台探测徽标（设置页 caption「macOS 模式·Cmd 已映射」）；switch 用 mac 圆钮 32×18 spring。

## 3. 动效体系升级

- **分配**：模式切换（brw-mode / 平台注入）用 spring（形变生命感）；计划卡批准用 anticipate（60ms 回缩再弹出的两段式）；高风险档禁快捷确认，仅 press 90 反馈、不抢跑。
- **批准链**：press 90 → 三钮 comp-out 140 淡出 → badge pending→running 交叠（micro 130）→ steps stagger 60 入场 → eta micro 出场。拒绝：anticipate 收缩 + comp 淡出。
- **回滚语义**：ckpt 回滚用 in-soft（收缩到位感），校验提示 narr 220 淡入——「后退用入场缓动，前进用 out-soft」。
- **节奏原则**：模态入场 stagger 封顶 40 + panel 240；环境层（极光/呼吸）禁与新界面同帧竞争；新动效全部注册 fx-off 停列与 prefers-reduced-motion/transparency 降级表。

## 4. 实现要点与风险

- **命名**：延续 v4 前缀（`dur-/ease-/stagger-/aurora-/glow-/edge-/ok|warn|err-`），新令牌两段式 `--{域}-{语义}`；JS 禁硬编码 ms，走 MOTION 单一事实源（67-plan-card.js 既有纪律）。
- **纯增策略**：新增 class 仅追加（plan-eta/riskbar/scope/auto、ckpt-list/verify、brw-mode/row/takeover、grant-budget、mac-kbd/badge），不改既有选择器与权重；`body.theming` / fx-off 白名单同步追加。
- **风险**：WebView2 与 WKWebView 的 backdrop-filter / overlay 滚动条差异 → 双端实测矩阵；mac 字体注入须早于首屏渲染（boot 前）；哈希链只显示首 8 位 + 省略号，禁长串全文。

## 5. 不做什么（防过度设计）

不做第三主题；不改字阶/间距/圆角既有值（新徽标复用 caption 12 / micro 11）；不引字体文件（mac 用系统 SF，Win 保持现有栈）；不加新缓动/时长令牌（五缓动七时长够用）；UNTRUSTED 不做全局重着色（仅内容标记场景）；回滚不加庆祝动效；不破坏 rail 60 + sidebar 264 + 四面板结构。

## 6. v1.9 新令牌渲染状态表

| 令牌 | 状态 | 说明 |
|---|---|---|
| `--aurora-5` | 已渲染 | 品牌蓝光斑入极光层，与青/紫 2 可见斑构成 3 斑漂移 |
| `--aurora-op-focus` | 已渲染 | 任务态挂载期间极光加深一档 |
| `--prov-line` | 已渲染 | 哈希链节点虚线 + 圆点（建议 prov-strip 内芯启用） |
| `--untrusted` / `--untrusted-bg` | 已渲染 | UNTRUSTED 斜纹边 + 来源 caption 标记 |
| `--skylight-strength` | 留待挂载 | 聊天天光纱计划卡区域渗透，随对话区移植启用 |
| `--bg-deep` | 留待挂载 | 原生窗口外圈环境色，Web 原型无法呈现，需双端实测 |
| `--edge-hi-strong` | 留待挂载 | 模态玻璃受光边；检查点禁模态叠模态，暂无挂载点 |

## 勘误记录

1. §1 `--aurora-5`：「与既有 4 斑漂移闭环」→「与既有 2 可见斑（青/紫）构成 3 斑漂移；品红斑已退役（display:none）」。
2. §1 暗态 `--aurora-bg-opacity`：「.50→.56」→「维持 .62（模板 2026-10-21 夜态沉浸已上调约 25%，初稿表述滞后）」。
3. §2.5 `--scrollbar-w`：「12px / 0」→「Win 10px（现行值不变）/ mac 0（hover 显形 8px overlay）」。
4. §2.5 `--radius-ctrl`：「8 / 6」→「Win 6px / mac 8px（mac 控件略圆，Win 与既有 `--radius-sm:6px` 对齐）」。
