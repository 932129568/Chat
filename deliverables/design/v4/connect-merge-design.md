# GLM-Chat「连接与模型」区块合并重设计 · 开发设计书

**日期**：2026-10-17 · **版本**：v1.0（待开发）
**配套原型**：`deliverables/design/v4/connect-merge.html`（可交互，含演示控制台）
**基线**：v1.5 代码库（v4 UI 已落地，451 测试全绿）

---

## 1. 背景与目标

设置面板现有**三块**功能重叠：「连接与模型」（GLM）、「模型服务商（OpenAI 兼容端点）」（自定义）、「本地模型」（v1.5）。用户诉求：**合并为一块——先填 API Key，下面选模型，最好能自动识别这个 API 对应的热门模型给选择**。

本设计书的合并范围 = 上述三块 → 一个「连接与模型」区块。角色/联网搜索、省 Token、生成参数等其他区块不动。

## 2. 已裁决设计决策（Grill 会话，2026-10-17）

| # | 分支 | 裁决 |
|---|------|------|
| D1 | 信息架构 | **端点分段控件（GLM 官方 / 自定义端点 / 本地服务器）+ 统一「凭证 → 模型」流**。不取消分段（GLM 专属能力需要判断依据）；不做纯视觉合并（不解决重复填写） |
| D2 | 自动识别 | **防抖 800ms 自动触发 + 手动按钮兜底**；数据源 = 实时 `GET {base}/models`（带 Key）+ 内置热门模型表（按 host 匹配）；失败回落手动输入，**永不阻塞** |
| D3 | GLM 专属控件 | 智能档 = 模型下拉**首项**（仅 GLM 段）；推理力度**条件显隐**（仅 GLM 段）；联网搜索留在「角色与联网」区块不动 |
| D4 | 价格字段 | 仅自定义段显示，收在「计费设置」折叠内；预设切换自动填默认价（DeepSeek 2/8/0.4）；留 0 不计费 |
| D5 | 存储兼容 | **UI 合并 ≠ 存储合并**：沿用现有 config.json 键（`api_key`/`model`/`reasoning_effort` + `provider_*` + `local_*`），零迁移、零 schema 变更；分段控件是现有三段状态的统一视图 |
| D6 | 交付物 | 可交互原型 + 本设计书；不含前端代码（开发按此书实施） |

## 3. 信息架构

```
┌─ 连接与模型 ─────────────────────────────────────────┐
│ [GLM 官方] [自定义端点] [本地服务器]      ← seg 分段控件 │
│ ┌──────────────────────────────────────────────┐   │
│ │ ① API Key（password；本地段替换为免 Key 提示条）  │   │
│ │ ② Base URL + 预设（仅自定义段；本地段为预设+端口）│   │
│ │ ③ 模型下拉 + 「↻ 识别模型」按钮                   │   │
│ │    - GLM 段：智能档 + glm-5.3-flash/flashx     │   │
│ │    - 自定义/本地段：识别出的热门模型 + 手动输入    │   │
│ │ ④ 推理力度（仅 GLM 段）                          │   │
│ │ ⑤ 计费设置折叠（仅自定义段）/ 工具调用+窗口（仅本地）│   │
│ │ ⑥ 测试连接 + 状态文字                            │   │
│ └──────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────┘
```

**分段 → 状态映射**（复用现有单活端点架构，`71-provider.js` 的 `resolveApiEndpoint/isGlmEndpoint/effectiveApiKey` 优先级不变）：

| 分段 | providerState.enabled | localState.mode | 生效端点 |
|---|---|---|---|
| GLM 官方 | false | false | API_URL（智谱） |
| 自定义端点 | true | false | provider_base_url |
| 本地服务器 | false（或 true 但 local 优先） | true | local_base_url |

## 4. 自动识别模型机制（D2 展开）

### 4.1 触发时机
- 自定义段：Base URL 或 API Key 输入变化 → **防抖 800ms** → 自动识别（两字段都非空才触发）
- 本地段：「探测本机」已有并行探测（`local_probe`），模型清单在探测命中后自动带出（`local_models`）
- GLM 段：不自动（Key 不枚举模型），仅「↻ 获取模型」按钮 → 拉智谱可用模型清单
- 任何段：按钮可手动重触发；识别中按钮 loading（旋转图标 + 禁用）

### 4.2 数据源（双路，按序）
1. **实时清单**：`GET {base_url}/models`，带 `Authorization: Bearer {key}`（OpenAI 标准）——**需后端小增强**（见 §6.2）
2. **内置热门表**：实时失败/为空时，按 Base URL host 匹配前端静态表（`PROVIDER_HOT_MODELS`）：

| host 关键词 | 热门模型（初版，可维护） |
|---|---|
| bigmodel.cn | glm-5.3-flash、glm-5.3-flashx、glm-4.6、glm-4.5-air |
| deepseek.com | deepseek-v4.1-256k、deepseek-v4.1 |
| moonshot.cn | kimi-k2、moonshot-v1-128k |
| dashscope.aliyuncs.com | qwen-max、qwen-plus、qwen-turbo |
| （其他） | 不猜——直接进手动输入态 |

### 4.3 结果呈现与兜底
- 成功：模型下拉填充识别结果（本地段每项带 ctx 徽标「32k/8k」+ 工具能力点）；toast「已识别 N 个模型」
- 失败（超时/404/空）：toast 人话错误；下拉固定末项「✎ 手动输入模型名…」始终在位——**选手动即变为文本输入，可随时切回下拉**。识别失败永不阻塞保存与发送
- 安全：清单请求走后端（`urlopen_no_redirect`，禁重定向）；Key 不出前端

### 4.4 状态机（自定义段）
```
idle → (输入变化, 防抖 800ms) → fetching → ok → filled（下拉含识别结果）
                                   ↓ fail
                                manual（手动输入态 + 错误 toast）
filling 中用户改 Base URL → 取消旧请求序号（last-wins），重新 fetching
```

## 5. 条件显隐矩阵

| 元素 | GLM 官方 | 自定义端点 | 本地服务器 |
|---|---|---|---|
| API Key 输入 | ✅ | ✅ | ❌（免 Key 提示条） |
| Base URL | ❌（内置） | ✅（+预设下拉） | ✅（+预设下拉，localhost 端口） |
| 模型下拉 | ✅（智能档+内置系） | ✅（识别+手动） | ✅（探测带出+ctx 徽标） |
| 识别模型按钮 | ✅（获取智谱清单） | ✅ | ❌（探测按钮代替） |
| 推理力度 | ✅ | ❌ | ❌ |
| 计费设置（三价） | ❌（内置价格表） | ✅（折叠） | ❌（零费） |
| 工具调用/窗口覆盖 | ❌ | ❌ | ✅ |
| 测试连接 | ✅ | ✅ | ✅ |
| 会话头部计费 | 三价实价 | 三价实价 | 「本地 · 0 费用」 |

## 6. 数据与契约

### 6.1 config.json 键位（不变，D5）
- GLM：`api_key` / `model` / `reasoning_effort`
- 自定义：`provider_enabled/name/base_url/model/key/prices{in,out,cache}`
- 本地：`local_mode/base_url/model/ctx_window/tool_capable/preset`
- 合并 UI 的 collect/load 按分段写上述对应键组；`save_config` 合并语义不变（契约红线保持）

### 6.2 后端增强（唯一必需，1 处）
`local_models(base_url)` 增加**可选** `api_key` 参数：非空时请求带 `Authorization: Bearer {key}` 头（自定义端点清单需要；本地免 Key 行为不变）。签名向后兼容，js_api 仍隐身 `_V12_EXTRA`。
（备选：新建 `provider_models(base_url, api_key)`——不推荐，local_models 语义已覆盖「拉 OpenAI 兼容清单」。）

GLM 官方清单端点可用性未在本环境验证——**开发首日验证** `GET https://open.bigmodel.cn/api/paas/v4/models`；不可用则 GLM 段保持内置静态表（可接受，已在 §4.2 留好降级）。

### 6.3 UI 契约影响
- `check_contract.py` 钉住的 `apiKey`/`modelSelect`/`reasoningEffort` 三个 id **必须保留**（合并后分别为 Key 输入/模型下拉/推理力度下拉）
- `provider_*`/`local_*` 全部 id **不在钉住清单**，可自由重组；但 `71-provider.js`/`34-local-model.js`/`70-config.js`/`110-boot.js` 对这些 id 的引用要同步改（见任务拆解）
- 43 个 callApi 方法清单不含 provider/local 相关——调用点可自由调整；`test_provider_endpoint` 增加 `local` 参数已就绪，自定义段测试连接直接复用

## 7. 组件规格（视觉以原型为准）

- **分段控件**：`.seg` + `.seg-btn` 家族，选中态 = `--active` 底 + `--primary` 字 + 左 3px 竖条（scaleY 动画）；切换时内容区 200ms 交叉淡入
- **模型下拉**：自定义 select（cs-*）封装；识别结果分组（`<optgroup>` 或分组标题项）；本地段每项右侧 ctx 徽标（`.local-badge` 复用）；「✎ 手动输入模型名…」末项固定；手动态 = 下拉原位变文本输入 + 左侧「⌕」图标
- **识别按钮**：`.modal-btn` + 旋转图标（loading 750ms 模拟）；防抖期间显示「识别中…」文字态
- **计费设置折叠**：`<details>` 原生 + set-hint 样式，summary「计费设置（可选）」；三价 input 横排
- **测试连接**：`.modal-btn primary` + 右侧状态文字（`--ok`/`--err`，130ms 过渡）
- **免 Key 提示条**：`.local-badge on` 样式 chip 行
- 全部按钮/下拉走 v4 按钮家族（hover 130ms / press 90ms）；toast 四态；破坏性操作（删除端点配置）走 uiConfirm

## 8. 验收标准

1. **单 Key 流**：任何分段下，Key（或免 Key 提示）+ 模型两个必填项始终在视觉主轴，无需滚动可见（设置浮层 900px 高度内）
2. **自动识别**：自定义段粘贴 URL+Key 后 ≤1s 下拉出现识别结果；断网/错 URL 时 3s 内回落手动态且 toast 人话错误；全程不阻塞保存
3. **GLM 体验不回退**：智能档 + 推理力度 + 内置价格表行为与合并前一致；切到 GLM 段时 reasoningEffort 显示、其他段隐藏
4. **兼容**：旧 config.json（含 provider_*/local_* 键）打开后正确回填三段状态；`pytest tests/ -q` 451 不回归；`check_contract.py` PASS；`node frontend/build.js` 幂等
5. **降级**：fx-off / prefers-reduced-motion 下识别 loading 用瞬时态、无动画依赖

## 9. 开发任务拆解（预估 2.5 人日）

| # | 任务 | 依赖 | 工时 |
|---|------|------|------|
| T1 | 模板：三块合并为一个 set-block（分段控件 + 统一流 + 条件容器），保留 apiKey/modelSelect/reasoningEffort | — | 0.5 |
| T2 | 后端：`local_models` 加可选 `api_key` 参数（带头）；验证智谱清单端点 | — | 0.25 |
| T3 | 前端：新模块 `36-connect.js`——分段状态机 + 防抖识别编排 + PROVIDER_HOT_MODELS 表 + 手动/下拉态切换 | T1 | 0.75 |
| T4 | 前端：71-provider.js / 34-local-model.js / 70-config.js / 110-boot.js 适配新 id 与分段 collect/load | T1,T3 | 0.5 |
| T5 | 测试：契约差分 + vm 沙箱（分段切换/防抖 last-wins/识别失败兜底/手动态）+ 旧配置回填用例 | T4 | 0.5 |
| T6 | 回归 + 构建 + 冒烟（三分段各走一遍：填写→识别→测试连接→发问） | T5 | 0.25 |

## 10. 风险与对冲

| 风险 | 对冲 |
|------|------|
| 智谱清单端点不可用 | §4.2 降级为内置静态表；GLM 段本就有内置系 |
| 自定义端点清单也要 Key 但行为不一（有的免 Key） | 带 Key 请求；401 时自动无 Key 重试一次（dev 自选，默认不做） |
| 防抖自动识别造成意外请求 | 仅自定义段 + 两字段非空才触发；可设置里关自动（留开关位，默认开） |
| 三块合并引发 JS 引用大面积改动 | id 重组集中在 T1/T4；契约测试 + vm 沙箱兜底 |
