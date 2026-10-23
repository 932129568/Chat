# Harbor v1.9.0 前端接口契约与差异项对账（工程事实基线）

> 主理人画统筹汇编，2026-10-23。数据源：代码库实测（两轮确定性扫描：callApi 直调正则 + 零引用二次检索）。
> 前端 86 种调用 / 后端 126 个方法。本节为 Phase 5 交接报告的事实底稿。

## 一、总账

| 类别 | 数量 | 结论 |
|---|---|---|
| A 类：前端调用但后端不存在（悬空调用） | **0** | 前端纪律良好，无欠后端的账 ✓ |
| v1.9 方案 12 个新 js_api | 12 | **双方均未落地**（后端无/前端无）——v1.9 共同工作项 |
| B 类：前端已具备但后端未实现 | 0 | 前端无超前调用（未做无接口调用的开发） |

## 二、A 类差异项：后端已具备、前端需补齐（9+3 项）

### A1 · v1.9 新接口中「后端已备、前端未接」（3 项）

| 方法 | 后端现状 | 前端需做 |
|---|---|---|
| `checkpoint_create` | api.py 已有（plan_service 时代遗留，M2.7 将升级六军规） | 检查点创建入口（计划卡批准时自动/手动）、清单对话框（原型已出：`prototypes/checkpoint-dialog.html`） |
| `checkpoint_list` | 已有 | 检查点列表渲染（任务历史面板挂载） |
| `checkpoint_rollback` | 已有（M2.7 升级差异恢复） | 回滚确认对话框 + 回滚后校验提示（原型三态已覆盖） |

### A2 · 后端已备、前端仍未接入的历史项（3 项，接续 2026-10-21 交接文档——其中 3 项已闭合，此处列净剩余）

| 方法 | 状态 |
|---|---|
| `plan_get` | 后端在位，前端零调用——断线重连/刷新场景低优（v1.9 计划审查主关卡上线后优先级上升：关卡态刷新需要） |
| `trace_new` | 后端在位，前端零调用——v1.9 审计五维哈希链（M2.6）上线时应在发送入口显式分界 |
| `list_recent_ws` | 后端在位，wsqList 走 config recent 数组有等效数据源——保持现状即可（登记不动作） |

## 三、B 类差异项：前端将具备/需后端实现（9 项，移交后端）

v1.9 方案 §6.2 的 12 个新 js_api 中，除 checkpoint 三兄弟后端已有外，**9 个后端完全未实现**——前端按原型先行开发，后端按 M1-M5 里程碑补齐：

| 方法 | 方案签名 | 后端交付里程碑 | 前端依赖点 |
|---|---|---|---|
| `browser_navigate` | `(url, wait_selector?, timeout?)` → `{ok,title,url,trace_id}` | M3（Win）/M4（Mac） | 39-search-panel 驱动模式 |
| `browser_extract` | `(selector?, mode)` → `{ok,markdown,links,truncated}` | M3/M4 + M2.1 读取器 | 面板结果区 + UNTRUSTED 标记 |
| `browser_click` | `(selector\|text)` → `{ok,before_b64,after_b64}` | M3/M4（guard=always） | 工具分发反馈 |
| `browser_fill` | `(selector,text)` → `{ok,masked:true}` | M3/M4（guard=always） | 工具分发反馈 |
| `browser_screenshot` | `(full_page?)` → `{ok,b64}` | M3/M4 | 面板状态行 |
| `browser_close` | `(session_id)` → `{ok}` | M3/M4 | 会话池回收 |
| `get_platform_info` | `()` → `{os,arch,version,services:{...}}` | M6.10 | 69-platform.js 平台徽标 + mac 分支根类 |
| `guard_approval_budget` | `(limit?)` → `{used,limit,escalated}` | M2.4 | 授权条预算指示器（原型已出：`prototypes/grant-budget.html`） |
| `search_reader_stats` | `()` → `{reader_calls,schema_fail,degrade_count}` | M2.1 | 34-local-model dual-LLM 状态灯 |

## 四、会话/配置层数据契约（纯增，前端需消费的新字段）

| 位置 | 新字段 | 前端用途 |
|---|---|---|
| sessions.json | `browser:{session_id,mode}` | 会话恢复时重建浏览器面板状态 |
| sessions.json | `audit_chain:{head,len}` | 审计可见性（M2.6：head 首 8 位+省略号） |
| guard.json | `approval_budget:{limit,used,escalated}` | 预算指示器数据源 |
| browser_sessions.json（新文件） | `sessions[]` | 驱动面板会话池展示 |
| checkpoints.json（新文件） | `items[]` | 检查点清单对话框数据源 |

## 五、纪律红线（移交前后端双方）

1. 12 个新 js_api 全走 `_V12_EXTRA` 隐身登记（M1.9 先占位后实现）——`get_api_info()` 逐字节零漂移
2. 新配置全部独立文件——config.json 零污染
3. UI 契约只增不改：新 DOM id/class 纯增（原型已按 plan-/ckpt-/brw-/grant-/mac- 前缀命名）
4. guard 档位：click/fill=always（前后态截图审计），其余 session 档
5. 前端调用超时口径沿用联调规范 §2.1（navigate 60s / extract 45s / 其余 30s，待 M3 实现时校准）
