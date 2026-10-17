# GLM-Chat「连接与模型」区块合并重设计 · 开发设计书

**日期**：2026-10-17 · **版本**：v1.1（D1 改判完全单端点）
**配套原型**：`deliverables/design/v4/connect-merge.html`（可交互，含演示控制台）
**基线**：v1.5 代码库（v4 UI 已落地，451 测试全绿）

---

## 1. 背景与目标

设置面板现有**三块**功能重叠：「连接与模型」（GLM）、「模型服务商（OpenAI 兼容端点）」（自定义）、「本地模型」（v1.5）。用户诉求：**合并为一块——先填 API Key，下面选模型，自动识别这个 API 对应的热门模型给选择**。

本设计书的合并范围 = 上述三块 → 一个「连接与模型」区块。角色/联网搜索、省 Token、生成参数等其他区块不动。

## 2. 已裁决设计决策（Grill 会话，2026-10-17）

| # | 分支 | 裁决 |
|---|------|------|
| D1 | 信息架构 | **完全单端点（用户 22:30 改判定稿）**：取消端点分段控件。全 App 只有一个「当前端点」概念，由**预设下拉**第一行选择（智谱 GLM / DeepSeek / Moonshot / 通义千问 / Ollama / LM Studio / vLLM / llama.cpp / LocalAI / 自定义）。GLM 官方只是 name='glm' 的预设（Base URL 预填官方地址），不是独立模式。原「启用自定义端点」「启用本地模式」两个勾选开关从 UI 移除——端点状态由「当前预设」单一决定 |
| D2 | 自动识别 | **防抖 800ms 自动触发 + 手动按钮兜底**；数据源 = 实时 `GET {base}/models`（带 Key）+ 内置热门模型表（按 host 匹配）；失败回落手动输入，**永不阻塞** |
| D3 | GLM 专属控件 | 智能档 = 模型下拉**首项**（仅智谱 GLM 预设）；推理力度/三价/工具调用/窗口覆盖全部移入「高级 ▾」折叠，按预设**条件显隐**；联网搜索留在「角色与联网」区块不动 |
| D4 | 价格字段 | 仅非 GLM 非本地的云端自定义预设时显示（高级折叠内），预设切换自动填默认价（DeepSeek 2/8/0.4）；留 0 不计费 |
| D5 | 存储兼容 | **UI 合并 ≠ 多套存储合并**：单一事实源 = `provider_*` 键组（provider_name/base_url/key/model/prices），GLM 与本地服务器都是预设而非独立键系；本地专属项（ctx 覆盖/工具调用）继续写 `local_*`（与 provider 并列，不互斥）；启动一次性迁移：老 config 只有 `api_key` 无 `provider_base_url` → 自动 seed 为 glm 预设 |
| D6 | 交付物 | 可交互原型 + 本设计书；不含前端代码（开发按此书实施） |

## 3. 信息架构（完全单端点）

```
┌─ 连接与模型 ─────────────────────────────────────────┐
│ 一个 Key，连所有端点                                    │
│ ┌──────────────────────────────────────────────┐   │
│ │ 预设  [智谱 GLM        ▾]  ← 第一行，选预设即填 URL │   │
│ │ Base URL  [https://open.bigmodel.cn/paas/v4 ] │   │
│ │ API Key  [••••••（仅保存在本机）]               │   │
│ │   （本地系预设时本行替换为免 Key 提示条）          │   │
│ │ 模型  [智能档（自动调节，最省）    ▾] [↻ 识别模型] │   │
│ │   （识别出热门模型；末项固定「✎ 手动输入模型名…」）  │   │
│ │ [测试连接]  ✓ 连接成功                           │   │
│ │ ▸ 高级 ▾（收起）                                │   │
│ │   ├ 推理力度（仅智谱 GLM 预设显示）               │   │
│ │   ├ 计费三价（仅云端自定义预设显示）               │   │
│ │   └ 工具调用/窗口覆盖（仅本地系预设显示）           │   │
│ └──────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────┘
```

**单一端点状态机**（`71-provider.js` 的 `resolveApiEndpoint/isGlmEndpoint/effectiveApiKey` 保留，判据改预设）：

| 预设 | provider_name | 生效 Base URL | Key | GLM 专属能力 |
|---|---|---|---|---|
| 智谱 GLM | glm | open.bigmodel.cn/api/paas/v4 | 必填 | 全开（智能档/推理力度/思考/联网/内置价格表） |
| DeepSeek/Moonshot/通义/自定义 | 各自 host | 用户填 | 必填 | 关（三价计费） |
| Ollama/LM Studio/vLLM/llama.cpp/LocalAI | 各自 localhost | localhost 端口 | 免 | 关（零费 + ctx/工具本地项） |

## 4. 自动识别模型机制（D2 展开）

### 4.1 触发时机
- Base URL 或 API Key 变化 → **防抖 800ms** → 自动识别（云端预设需两字段非空；本地系只需 URL 非空）
- 「↻ 识别模型」按钮随时手动重触发；本地系预设时按钮文字变「**探测本机**」并改走并行端口探测（复用 `local_probe`，命中后自动带出清单）
- GLM 预设：不自动枚举，按钮 = 「获取模型」拉智谱可用清单（端点可用性开发首日验证，不可用则回落内置静态表）

### 4.2 数据源（双路，按序）
1. **实时清单**：`GET {base_url}/models`，带 `Authorization: Bearer {key}`——**需后端小增强**（§6.2）
2. **内置热门表**：实时失败/为空时按 Base URL host 匹配前端静态表 `PROVIDER_HOT_MODELS`：

| host 关键词 | 热门模型（初版，可维护） |
|---|---|
| bigmodel.cn | glm-5.3-flash、glm-5.3-flashx、glm-4.6、glm-4.5-air |
| deepseek.com | deepseek-v4.1-256k、deepseek-v4.1 |
| moonshot.cn | kimi-k2、moonshot-v1-128k |
| dashscope.aliyuncs.com | qwen-max、qwen-plus、qwen-turbo |
| localhost | gpt-oss-20b、qwen3.8-27b、llama3.1:8b（本地系兜底建议） |
| （其他） | 不猜——直接进手动输入态 |

### 4.3 结果呈现与兜底
- 成功：模型下拉填充识别结果（本地系每项带 ctx 徽标「32k/8k」）；toast「已识别 N 个模型」
- 失败（超时/404/空）：toast 人话错误；下拉末项「✎ 手动输入模型名…」**始终在位**——选手动即原位变文本输入，可切回。识别失败永不阻塞保存与发送
- 安全：清单请求走后端（`urlopen_no_redirect` 禁重定向）；Key 不出前端
- 防抖竞态：last-wins（新触发使旧请求序号失效）

## 5. 条件显隐矩阵（按预设，D3/D4）

| 元素 | 智谱 GLM | 云端自定义 | 本地系 |
|---|---|---|---|
| API Key 输入 | ✅ | ✅ | ❌（免 Key 提示条） |
| Base URL | ✅（预填官方） | ✅（预设自动填） | ✅（预设自动填 localhost） |
| 模型下拉 | ✅（智能档+内置系） | ✅（识别+手动） | ✅（探测带出+ctx 徽标） |
| 识别/探测按钮 | ✅ 获取模型 | ✅ 识别模型 | ✅ 探测本机 |
| 推理力度（高级） | ✅ | ❌ | ❌ |
| 计费三价（高级） | ❌（内置价格表） | ✅ | ❌（零费） |
| 工具调用/窗口覆盖（高级） | ❌ | ❌ | ✅ |
| 会话头部计费 | 三价实价 | 三价实价 | 「本地 · 0 费用」 |

## 6. 数据与契约

### 6.1 config.json 键位（单一事实源，D5）
- **主键组 `provider_*`**：`provider_name`（预设 id）/ `provider_base_url` / `provider_key` / `provider_model` / `provider_prices{in,out,cache}`——一切端点共用；GLM = `provider_name:'glm'` 的预设，不再有「开关」概念
- **本地专属 `local_*`**：`local_ctx_window` / `local_tool_capable`（预设为本地系时才写才读）
- **GLM 遗留键**：`api_key` / `model` / `reasoning_effort` 保留只读迁移——boot 时若无 `provider_base_url` 且有 `api_key`，一次性 seed：`provider_name='glm'` + `provider_base_url`=官方地址 + `provider_key=api_key` + `provider_model=model`；之后全部走 provider_*
- **判据调整**：`isGlmEndpoint()` 从「provider 未启用」改为 `provider_name==='glm'`（或 base_url 含 bigmodel.cn）——决定 thinking/web_search/智能档/推理力度/内置价格表可用性（涉及 60-agent-loop.js、97-compact.js、75-token-stat.js 的判据调用点，语义不变）

### 6.2 后端增强（唯一必需，1 处）
`local_models(base_url)` 增加**可选** `api_key` 参数：非空时请求带 `Authorization: Bearer {key}` 头（云端自定义端点清单需要；本地免 Key 行为不变）。签名向后兼容，js_api 仍隐身 `_V12_EXTRA`。

### 6.3 UI 契约影响
- `check_contract.py` 钉住的 `apiKey`/`modelSelect`/`reasoningEffort` 三个 id **必须保留**（合并后 = Key 输入 / 模型选择 / 推理力度——后者移入高级折叠但 id 在）
- `provider_*`/`local_*` 全部 id **不在钉住清单**，可自由重组；`71-provider.js`/`34-local-model.js`/`70-config.js`/`110-boot.js` 对这些 id 的引用同步改
- 43 个 callApi 方法清单不含 provider/local 相关——调用点可自由调整；`test_provider_endpoint` 的 `local` 参数已就绪

## 7. 组件规格（视觉以原型为准）

- **预设下拉**：第一行、宽 170px，选后 200ms 交叉淡入更新下方（Base URL/Key 行/占位符/模型建议联动）
- **模型下拉**：自定义 select 封装；识别结果分组；本地系每项右侧 ctx 徽标（`.local-badge` 复用）；「✎ 手动输入模型名…」末项固定；手动态 = 原位变文本输入
- **识别/探测按钮**：`.modal-btn` + 旋转图标（750ms）；防抖期间文字态「识别中…」
- **高级折叠**：`<details>` 原生 + set-hint 样式，summary「高级 ▾」；每条显隐规则一行小字说明
- **免 Key 提示条**：`.local-badge on` chip 行
- **测试连接**：`.modal-btn primary` + 状态文字（`--ok`/`--err`，130ms 过渡）
- 全部按钮走 v4 家族（hover 130ms / press 90ms）；toast 四态；破坏性操作走 uiConfirm

## 8. 验收标准

1. **单 Key 流**：Key + 模型两个必填项始终在视觉主轴，设置浮层内无滚动可见
2. **自动识别**：填 URL+Key 后 ≤1s 下拉出现识别结果；错 URL 3s 内回落手动态 + 人话 toast；全程不阻塞
3. **GLM 体验不回退**：智能档/推理力度/内置价格表行为与合并前一致
4. **兼容**：旧 config.json（含 api_key/provider_*/local_*）打开后正确回填为对应预设；`pytest tests/ -q` 451 不回归；`check_contract.py` PASS；`node frontend/build.js` 幂等
5. **降级**：fx-off / prefers-reduced-motion 下识别 loading 瞬时态、无动画依赖

## 9. 开发任务拆解（预估 3 人日）

| # | 任务 | 依赖 | 工时 |
|---|------|------|------|
| T1 | 模板：三块合并为单块（预设下拉 + 单一 URL/Key/模型流 + 高级 details），保留 apiKey/modelSelect/reasoningEffort | — | 0.75 |
| T2 | 后端：`local_models` 加可选 `api_key`（带头）；验证智谱清单端点 | — | 0.25 |
| T3 | 前端：`36-connect.js`——预设状态机 + 防抖识别 + PROVIDER_HOT_MODELS + 手动/下拉态切换 + 条件显隐 | T1 | 1.0 |
| T4 | 前端：71-provider.js（isGlmEndpoint 判据改预设）/ 34-local-model.js / 70-config.js / 110-boot.js（seed 迁移 + collect/load 适配新 id） | T1,T3 | 0.5 |
| T5 | 测试：契约差分 + vm 沙箱（预设切换/防抖 last-wins/识别失败兜底/手动态）+ 旧配置 seed 用例 | T4 | 0.5 |
| T6 | 回归 + 构建 + 冒烟（GLM/DeepSeek/Ollama 三预设各走一遍） | T5 | 0.25 |

## 10. 风险与对冲

| 风险 | 对冲 |
|------|------|
| 智谱清单端点不可用 | §4.2 降级内置静态表；GLM 预设本就有内置系 |
| 自定义端点清单也要 Key 但行为不一 | 带 Key 请求；401 自动无 Key 重试一次（dev 自选） |
| 防抖自动识别造成意外请求 | 仅字段非空才触发；设置留「自动识别」开关位（默认开） |
| 单端点化牵连 isGlmEndpoint 判据（thinking/web_search 剥离） | 判据改 provider_name；语义不变；契约测试 + 沙箱兜底 |
| 旧配置迁移出错 | seed 一次性且幂等；老键只读不改写；测试钉住回填结果 |

---

## 附：Grill 会话总结（决策树全分支已闭合）

用户述求「两块合一、填 Key 选模型、自动识别热门模型」经六分支拷问后定稿：**信息架构取完全单端点**（用户改判，取消分段，GLM 降级为预设——最贴合「一个 Key 连所有端点」的单一流畅感）；**识别机制取防抖自动+手动兜底双路数据源**（实时清单优先、内置热门表兜底、失败永不阻塞）；**GLM 专属能力全部条件化**（智能档留模型下拉首项，推理力度/三价/本地项进高级折叠按预设显隐）；**存储单源化**（provider_* 为主键组 + 一次性 seed 迁移，零 schema 变更）；**交付为原型+设计书**。无未决分支。
