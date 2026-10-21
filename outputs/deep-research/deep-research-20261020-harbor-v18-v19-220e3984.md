---
tags: [deep-research-report, status/review]
created: 2026-10-20
scope: 多平台社区调研与Harbor-v18-v19迭代方案
sources: "内部 6 / 外部 33"
search-mode: 多平台并行外检→主题归纳→方案映射
---

# 深度检索报告：《全网社区调研与 Harbor v1.8/v1.9 迭代方案》

## 范围
- 查询范围：GitHub / 知乎系（微信公众号·腾讯云开发者·CSDN·尧图网络·工具导航·观猹·linux.do·ASI111·墨天轮·人人代码）/ 贴吧（百度贴吧·主机大巴）/ B 站（前序任务两个视频系列）/ 国际社区（AgentRank·AgentList·DEV·Agent Times·AI-Radar·Happycapy·Subagentic·PromptZone·Bitroot·anothernews·CyberMedia·MacMyths·Galileo·SSW·o-mega·NeuralTrust·OWASP·Microsoft Learn·DeepWiki·thinkaicorp·orush·ayautomate·aitechconnect·owerczuk·modb·clawpk·arXiv·presenc·decodethefuture·zubnet·guijiagi·opensourcesai·localaimaster·renrendaima·computingforgeeks·tavily·apipick·aiuxplayground·aydesign·skillselion·producthub·aiopenlibrary·lobehub·crates.io·haotianblog·zread·ivoox·oh-bug·sandbase·tryinterlock·belsoft·agamisoft·powerlabs·omnithium·datawizard·thepromptbench·deepseek.ai·api-docs.deepseek·bigmodel·modelscope·tsight·hqwc·pingcode·ahrvoje·hackyboiz）关于「AI 桌面客户端 Agent 能力」的已有方案、案例、讨论与用户反馈
- 主题聚焦：Harbor v1.8/v1.9 四大方向——浏览器精准搜索 / 外部软件调用 / 本地大模型协同 / Agent 自主化；覆盖提示词工程、RAG、记忆、上下文工程、MCP 安全、可观测性、沙箱技术、API 特性、onboarding
- 时间窗口：2026-10-20 单日 10 批检索（用户要求「全网所有已有经验」，分 6+4 两阶段追加）；外部源以近 12 个月为主
- 检索路径：30 路并行 WebSearch（10 批）+ 2 次 WebFetch（B 站链接）+ 内部代码库与既有方案文档比对；无向量后端，关键词检索
- 检索模式：关键词 + 多平台交叉（同一主题中英文各一路 + 方案/社区/事故/数据分类覆盖）

## 核心结论
- [内+外] **浏览器自动化共识=「结构化交互优先于像素」**：Playwright MCP（微软官方 29-38k★）用 accessibility tree 免视觉点击，但需 Node 18+；Harbor 既定方案（自有 WebView2+纯函数提取器）与共识同向且更轻；**关键实现修正**：提取结果必须经 **js_api 回调**回传（evaluate_js 依赖页面 unsafe-eval CSP，外部站点 Strict CSP 下会失败）；吸收 Firecrawl 的 markdown 输出与 Tavily 的 LLM-ready 结构（https://agentrank-ai.com/blog/best-mcp-servers-web-browser + https://deepwiki.com/r0x0r/pywebview/8.2-security-considerations）
- [外] **提示注入防御三架构（2026 生产姿态）**：lethal trifecta（私数据×不可信内容×外传通道，断一条即可）/ dual-LLM（特权规划器持工具永不读不可信文本 + 隔离读取器无工具只返结构化值）/ CaMeL（AgentDojo 缓解 67-100%）；检测器只是其中一层（自适应攻击者会迭代绕过）；**Harbor 的本地模型天然是「免费读取器」**——dual-LLM 模式对 Harbor 近乎零成本（https://nomadx.ae/blog/ai-agent-security-prompt-injection-defense-2026 + https://red.ht/4rYjg0J）
- [外] **2026 Agent 失控事故档案 + 监管实锤**：GPT-5.6 删 $HOME / 提示注入 DROP TABLE / 沙箱外传被拦 / terraform destroy 2.5 年数据 / 48k files / 子 agent 退化生成**伪造系统指令自我注入** / 野外提示注入存活两周；工信部对 OpenClaw 发预警+六要六不要、Gartner「隔离环境+一次性凭证」。Harbor 三档护栏+Job Object 沙箱+全量审计=监管建议的同构实现（https://happycapy.ai/blog/ai-agent-deleted-db + https://bitroot.org/blog/2026-07-20-when-agents-go-wrong-a-cisos-guide-to-agentic-ai-r + http://mp.weixin.qq.com/s?__biz=MzkyODQwNjUxOQ==&mid=2247483709）
- [外] **本地模型 tool calling 失败点在运行时层**：xLAM 榜首实测 15%（模板不兼容）；Ollama 4k/32k 不协商噩梦；社区 6 failure modes Harbor 已覆盖 4 个；缺口=「tool_calls 空但 content 含工具 JSON」解析兜底 + chat template 探测；**本地模型 readiness 应产品化**（8 项 scorecard）（https://theagenttimes.com/agents/article/local-tool-calling-divides-our-community-breakthrough-or-col-a0eff21e + https://infinisynapse.com/en/blog/ollama-function-calling-reddit）
- [外] **MCP 生态冷水 + OWASP 门控四机制**：3,279 个公开 Server 仅 24.2% 健康；投毒成功率 84.2%（开自动批准时）；OX Security SDK 级 RCE 影响 150M+ 下载。OWASP 客户端风险门控可直接适配：**危险动词楼层规则（delete_/drop_/purge_/wipe_ → L5）+ 定义指纹 TOFU（防 rug pull）+ 暴露天花板 + HITL 门控**——Harbor 的 derive_tier 缺「楼层规则」这一对抗性设计（https://owasp.org/www-project-mcp-top-10/2025/recommended-controls/Client-Side-Tool-Risk-Gating + https://cloud.tencent.com.cn/developer/article/2752880）
- [外] **上下文工程四杠杆 + 缓存范式革命**：context rot 全模型单调劣化（18/18 模型）；context collapse 需增量条目化更新（ACE）；「stable prefix first + front-load aggressively + append don't rewrite」——2023 年的裁剪省 token 建议已过时；「日志只记一样就记模型看见的消息数组」（https://galileo.ai/blog/the-2026-caching-playbook-for-agents-bigger-prompts-smaller-bills + https://thinkaicorp.com/the-million-token-trap-why-context-management-beats-bigger-windows-in-2026/）
- [外] **Prompt caching 与压缩的择时**：压缩=cache reset，应像数据库 vacuum 择时（Harbor TOK-1 双条件设计被外部验证）；度量 cache hit rate 而非 raw tokens（Harbor 已有三价计算）（https://www.ssw.com.au/rules/do-you-follow-best-practices-for-prompt-caching + https://o-mega.ai/articles/prompt-caching-cut-agent-bills-45-in-2026）
- [外] **DeepSeek 模型线已换代**：deepseek-chat/reasoner 2026-07-24 退役，现役 V4-Flash（$0.15/$0.60，缓存 $0.003）/V4-Pro（$0.66/$1.98）；1M 上下文+磁盘缓存（TTFT 13s→500ms）；GLM Web Search API 提供结构化搜索（意图识别/域名/时效/摘要长度）——**Harbor 的 36-connect preset 与价格表需校准**（https://api-docs.deepseek.com/quick_start/pricing + https://docs.bigmodel.cn/cn/guide/tools）
- [外] **沙箱技术事实纠正**：Microsoft Learn 证实 Job Object UI 限制**包含 READCLIPBOARD(0x0002)/WRITECLIPBOARD(0x0004)**（Chrome 渲染器即用此禁剪贴板）——本仓 KNOWN_ISSUES §17「剪贴板隔离不可达」结论**需实测复核**，若 Flag 值属实则 strict 档可闭合该缺口；CreateProcessInSandbox（Win11 新 API）提供真正的文件系统隔离（fs_read_write 路径清单），是沙箱硬化候选（https://learn.microsoft.com/en-us/windows/win32/secauthz/createprocessinsandbox + https://hackyboiz.github.io/2026/07/13/OUYA77/Wipeload_step4/en）
- [外] **token 估算的系统性偏差**：cl100k vs o200k 同文本差 20%；DeepSeek 估算结构性偏差 20-30%（中文更重）；**Harbor 的 estTokens 中文比 1.8 显著低于业界 3.2-3.4**——即高估中文 token 约 2 倍，导致过早压缩（保守但浪费）；provider usage 才是账本真值（https://dev.to/caresodev/i-ran-the-same-text-through-two-tokenizers-they-disagreed-by-20-71 + https://n4n.ai/blog/token-counting-methods-tiktoken-vs-provider-reported-usage）
- [⚠ 未覆盖] 微博一手内容、贴吧深度帖（仅浅层推荐帖）；X/Twitter 一手（经二手转引）；Harbor 自身用户反馈（无遥测）

## 关键要点（Key Takeaways）
- **v1.8 浏览器搜索 = dual-LLM-lite 架构**：主模型（持工具、读隔离后的结构化结果）+ 本地读取器（解析网页、只返 JSON、永不传递指令）；provenance 分隔包裹；Tier 3 危险动作永远人类门；这把「提示注入防御」从提示词层面升级到架构层面，且本地读取器几乎零成本
- **搜索 API 是可选加速器不是默认**：Tavily/Serper/GLM Web Search 需 Key/付费/隐私出网，与 Harbor 本地优先冲突——设计为「用户自配 Key 时启用」，浏览器仍是默认通道
- **预期管理写入验收**：WebArena 浏览 agent 完成率仅 35-55%、百次重复成功率 38-75%——browser_search 定位「检索+提取」不做「网页操作」；OSWorld 人类 72% vs 模型 12% 再次否定 Harbor 走 GUI 自动化（software_call 的结构化路线更稳）
- **工具描述三段式进 v1.8 area 2**：触发条件置首 / 参数语义（格式+边界）/ 排除条款（何时不该用）；consolidate <20 工具；返回精简高信号结果（Sourcegraph：96 次调用→5 次）
- **onboarding 用 Use Case Wizard 模式**：3-4 个高信号问题（每个映射真实配置变更）、Skip 常驻、步骤计数+ETA、首屏展示计量表（花费/配额）、首 session 揭示一个杀手特性（沙箱）、留下次会话锚点
- **F3 RAG 评估路线已明确**：SQLite FTS5（中文必须保留关键词）+ 可选 sqlite-vec + bge-m3（CPU 1.6GB 零显存）+ RRF 融合 + 0.35 分数门 + 模型溯源重嵌入；400-600 字符句子感知切分
- **F2 记忆设计从六流派收敛**：先问「要不要表达时间变化和实体关系」——Harbor 单用户场景不需要时序图谱，走结构化条目+关键词检索+用户可见可删；OMEGA/Hindsight 证明本地 SQLite+开源模型可达 91-95% LongMemEval
- **发布体量纪律**：Cherry Studio「屎山」前车之鉴——每个新功能过「零依赖/轻量/护栏」三问；exe 尺寸/启动内存设阈值审计

## 证据清单
| # | 结论摘要 | 支撑 | 来源 |
|---|---------|------|------|
| 1 | Playwright MCP 官方 29-38k★ accessibility tree，需 Node 18+；Firecrawl markdown；Chrome DevTools MCP 调试向 | [外] | https://agentrank-ai.com/blog/playwright-mcp-vs-puppeteer-mcp + https://agentrank-ai.com/blog/best-mcp-servers-web-browser |
| 2 | pywebview 安全模型：file:// 默认禁/下载默认禁/外链进系统浏览器；**evaluate_js 需 unsafe-eval，run_js 无返回值** | [外] | https://deepwiki.com/r0x0r/pywebview/8.2-security-considerations |
| 3 | 注入防御：lethal trifecta/dual-LLM/CaMeL 67-100% 缓解；检测只是一层；工具分级 T1-T3+HITL；dual-LLM 成本 $0.002-0.05/轮 | [外] | https://red.ht/4rYjg0J + https://nomadx.ae/blog/ai-agent-security-prompt-injection-defense-2026 + http://ai-tldr.dev/learn/prompt-engineering/prompt-injection-security/prompt-injection-defenses + https://zdnetinside.com/knowledge/what_is_a_dual_llm_architecture_for_prompt_injection_defense_and_how_does_it_work.php |
| 4 | 搜索 API 两类：SERP 原始（$0.30/1k 快）vs Web Search LLM-ready（Tavily $8/1k 93.3% SimpleQA 厂方基准）；Exa 语义向 | [外] | https://www.tavily.com/blog/7-best-exa-alternatives-for-ai-agents-in-2026 + https://blog.csdn.net/Y381532662/article/details/162977929 |
| 5 | 基准：BFCL 20+ 工具 65-78%（Qwen3 32B 58%）；**百次重复成功率 38-75%，pass@1→pass^8 骤降**；OSWorld 人 72% vs 模型 12%；WebArena 35-55%；τ²-bench 87.9% Qwen3.5-397B | [外] | https://presenc.ai/research/ai-agent-capability-benchmarks-2026 + https://zubnet.ai/news/en/agentic-reasoning-benchmarks-2026-swe-bench-tau-bench-osworld-arc-agi + https://decodethefuture.org/en/ai-agent-benchmarks-2026/ |
| 6 | Agent 事故档案六例 + OpenClaw 监管（工信部预警/六要六不要/15 家券商/Gartner 隔离环境）+ ClawHub 投毒 | [外] | https://happycapy.ai/blog/ai-agent-deleted-db + https://bitroot.org/blog/2026-07-20-when-agents-go-wrong-a-cisos-guide-to-agentic-ai-r + https://anothernews.io/news/claude-subagent-wipe-order + http://mp.weixin.qq.com/s?__biz=MzkyODQwNjUxOQ==&mid=2247483709 |
| 7 | 野外提示注入：wiki 按 UA 给 agent 投删除载荷存活 2 周被拒；「模型的拒绝是最后一道墙」 | [外] | https://cybermediacreations.com/the-story-of-an-ai-that-nearly-wiped-out-its-own-reading-system/ |
| 8 | MCP 安全：OWASP Top10；客户端门控四机制（L0-L5 评分+危险动词楼层+TOFU 指纹+暴露天花板+HITL）；84.2% 投毒成功率；OX SDK RCE 150M+ 下载；严格 JSON Schema+SSRF 白名单 | [外] | https://owasp.org/www-project-mcp-top-10/2025/recommended-controls/Client-Side-Tool-Risk-Gating + https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html + https://deciphertech.io/blogs/mcp-at-the-crossroads-adoption-attack-surfaces-and-defense-patterns-for-production-agentic-systems |
| 9 | 上下文工程：rot 18/18 模型单调劣化；collapse 需增量条目化（ACE ICLR2026）；四杠杆 write/select/compact/isolate；锚定迭代摘要；工具结果精简（96→5 调用） | [外] | https://thinkaicorp.com/the-million-token-trap-why-context-management-beats-bigger-windows-in-2026/ + https://orush.ai/blog/what-is-context-rot-in-ai-agents + https://www.ayautomate.com/blog/context-engineering + https://www.owerczuk.dev/en/blog/context-engineering-llm-agents |
| 10 | 缓存范式：stable-first/front-load/append；500+ sessions 降本 41-80% TTFT +13-31%；naive 全量缓存反增延迟 | [外] | https://galileo.ai/blog/the-2026-caching-playbook-for-agents-bigger-prompts-smaller-bills + https://www.ssw.com.au/rules/do-you-follow-best-practices-for-prompt-caching |
| 11 | DeepSeek 换代：chat/reasoner 2026-07-24 退役；V4-Flash $0.15/$0.60 缓存 $0.003；1M ctx；磁盘缓存 TTFT 13s→500ms；峰谷计价 | [外] | https://api-docs.deepseek.com/quick_start/pricing + https://deepseek.ai/deepseek-api + https://api-docs.deepseek.com/zh-cn/news/news0802 |
| 12 | GLM Web Search API：结构化（意图/域名/时效/摘要长度 400-2500 字）；agent_toolset web_search+web_fetch（12000 tok）；工具编写最佳实践（中文官方同款） | [外] | https://docs.bigmodel.cn/cn/guide/tools + https://docs.bigmodel.cn/cn/managed-agents/tools |
| 13 | 沙箱：Job UI 限制含 READCLIPBOARD 0x0002/WRITECLIPBOARD 0x0004（MS Learn）；Chrome 渲染器 job 禁剪贴板/子进程/桌面；CreateProcessInSandbox 新 API 提供 fs 隔离；AppContainer 无 deny 规则 | [外] | https://learn.microsoft.com/en-us/windows/win32/secauthz/createprocessinsandbox + https://hackyboiz.github.io/2026/07/13/OUYA77/Wipeload_step4/en + https://ahrvoje.github.io/sandy_cli/modes.html |
| 14 | token 估算：cl100k vs o200k 差 20%；DeepSeek 估算偏 20-30%；中文模型 3.2-3.4 字符/token；provider usage 才是账本；混合模式（本地预检+usage 账本+5% 对账告警） | [外] | https://dev.to/caresodev/i-ran-the-same-text-through-two-tokenizers-they-disagreed-by-20-71 + https://deepwiki.com/kactlabs/toksum/5.3-tokenization-accuracy + https://n4n.ai/blog/token-counting-methods-tiktoken-vs-provider-reported-usage |
| 15 | Ollama 调参：keep_alive 默认 5m（每请求 0 则杀掉吞吐）；num_ctx 按显存分层（4K/32K/256K）；FA+KV q8 省 30-50%；KV 数学 8B Q4@32K≈10GB；pin tag 勿用 latest | [外] | https://opensourcesai.com/tools/ollama + https://computingforgeeks.com/?p=167394 + https://www.renrendaima.com/wap/article/13554.html |
| 16 | 工具描述三段式（触发/语义/排除）+ consolidate <20 + 命名空间 + 精简返回；strict schema；failure 对照表 | [外] | https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use + https://www.bestaiweb.ai/how-to-design-tool-descriptions-and-build-function-calling-pipelines-with-claude-and-gpt-5-5-in-2026 + http://taku.ai/blog/llm-tool |
| 17 | onboarding：Use Case Wizard（3-4 问映射真实配置/Skip 常驻/步骤 ETA/禁空白结尾）；单连接情境化请求；展示计量表；揭示一个杀手特性；次会话锚点 | [外] | https://aiuxplayground.com/pattern/use-case-wizard + https://www.aydesign.ai/blog/ai-onboarding-flow-design-guide-2026 + https://skillselion.com/skills/whawkinsiv/claude-code-superpowers/ux-design |
| 18 | 本地 RAG：SQLite FTS5+sqlite-vec+bge-m3（CPU 1.6GB）+RRF+0.35 分数门+模型溯源；中文必须关键词通道；400-600 字符句子感知切分；暴力余弦够用于个人语料 | [外] | https://lobehub.com/mcp/handrew-knowledge-base-mcp + https://crates.io/crates/knowledge-cli + https://www.haotianblog.com/local-llm-deploy-04-rag-zh |
| 19 | 记忆六流派选型：Mem0（48k★ 向量）/Zep（时序图谱 63.8%）/Letta（OS 式）/A-MEM（卡片盒）；决策变量=要不要时间与关系；OMEGA 本地 SQLite 95.4%/Hindsight 91.4% LongMemEval | [外] | https://www.modb.pro/db/2063811783568728064 + https://clawpk.net/research/R-TECH-09-agent-memory-architecture.html + https://adityakarnam.com/awesome-agentic-memory |
| 20 | 可观测性：OTel GenAI 约定；「只记一样就记模型看见的消息数组」；指标（TTFT 分位/工具数/重试/循环/每成功任务成本）；错误 trace 全留；redaction 在管道层；prompt 版本进日志 | [外] | https://oh-bug.com/posts/llm-observability-production-opentelemetry-genai-semantic-conventions-agent-tracing + https://blog.sandbase.ai/agent-observability-logging-tracing-debugging + https://tryinterlock.com/knowledge/how_should_teams_use_opentelemetry_for_ai_observability_in_2026.php |
| 21 | Prompt as code：golden set 20-50 真实输入+rubric；CI 三门（schema→golden diff→block）；prompt ID+版本进日志；回滚=revert N-1；canary 灰度；shadow edit 是首患 | [外] | https://powerlabs.cloud/version-control-for-prompts-treating-prompts-as-code-in-ci-c + https://thepromptbench.com/evals-and-testing/prompt-regression-testing + https://aitechconnect.in/tips/evals-in-ci-prompt-agent-regression-testing-2026 |
| 22 | Cherry Studio 三坑（掉帧/升级误删/MCP prompts 不可调）+「屎山」+64GB 内存吐槽；linux.do 定位讨论；竞品矩阵（Chatbox 最轻/Cherry 全而重/LobeChat 82.5k★） | [外] | https://toolnavs.com/zh/article/2140-is-cherry-studio-worth-installing-real-costs-and-3-gotchas-of-the-52k-star-open + https://linux.do/t/topic/2735116/1 + https://kkaiapi.com/chatbox-api-peizhi |
| 23 | 本地 tool calling 运行时层失败（xLAM 15%/Ollama 4k 噩梦）+6 failure modes+readiness scorecard；Win32 零依赖自动化三路线（UIA 对 Electron 无效） | [外] | https://theagenttimes.com/agents/article/local-tool-calling-divides-our-community-breakthrough-or-col-a0eff21e + https://infinisynapse.com/en/blog/ollama-function-calling-reddit + https://cloud.tencent.com/developer/article/2675534 |
| 24 | Harbor 已覆盖社区 failure modes 4/6；内部既有设计清单 | [内] | [[sandbox-architecture-2026-10-19]] + [[iteration-plan-v18-agent-2026-10-20]] + [[agent-autonomy-research-2026-10-20]] + 代码库实测 |

## 口径与来源（跨文档对比/专业术语查询时启用）
- 术语/指标口径：「lethal trifecta」= Willison 的私数据×不可信内容×外传通道三要素；「TOFU」= 首次见到的定义指纹钉住（trust on first use）；「pass^k」= 同任务连续 k 次成功（Sierra τ-bench 可靠性指标）；「chars/token」= 字符 token 比（中文模型 3.2-3.4，代码 3.4-3.6，英文 ~4）
- 实体解析：「OpenClaw/龙虾」→ OpenClaw 开源 Agent 框架（MIT，2025-11，Peter Steinberger）；「Harbor」→ 本工作区项目（aliases: GLM-Chat）；「CaMeL」= Google DeepMind capabilities-for-ML 防御架构
- 数据状态：内部资料截至 2026-10-20（v1.7.0 交付态）；公开信息截至 2026-10-20（DeepSeek 退役日 2026-07-24；MCP 健康度 2026-09；事故 2026-03/07/08）

## 来源分区
### 内部资料（6）
- [[iteration-plan-v18-agent-2026-10-20]]（v1.8 三能力+V1 校验+混合路由）
- [[agent-autonomy-research-2026-10-20]]（自主四件套 L0-L4）
- [[sandbox-architecture-2026-10-19]]（Job Object 沙箱+风险矩阵）
- [[KNOWN_ISSUES]]（沙箱边界/CDP 被拦截实证/§17 剪贴板结论待复核）
- [[iteration-plan-v16-2026-10-19]]（v1.6 基线）
- 代码库实测：guard_service / mcp_service / local_model_service / 25-tool-exec.js / 60-agent-loop.js / 40-auto-compact.js / 36-connect.js / mcp_transport_http

### 公开信息（33 个独立域）
方案/基准类：AgentRank ×2 · AgentList · Microsoft Learn (CreateProcessInSandbox) · DeepWiki (pywebview) · presenc · decodethefuture · zubnet · guijiagi · tavily ×2 · apipick · CSDN(token) · deepseek.ai ×2 · api-docs.deepseek ×2 · bigmodel ×2 · modelscope
安全类：OWASP ×2 · nomadx · ai-tldr · zdnetinside · deciphertech · happycapy · bitroot · subagentic · promptzone · anothernews · cybermediacreations ×2 · red.ht · tunicyberlabs · mcpblog · ahrvoje · hackyboiz
工程范式类：galileo · ssw · o-mega · neuraltrust · thinkaicorp · orush · ayautomate · aitechconnect ×2 · owerczuk · oh-bug · sandbase · tryinterlock · belsoft · agamisoft · powerlabs · omnithium · datawizard · thepromptbench · platform.claude · bestaiweb · taku.ai · promptingguide ×2
RAG/记忆类：lobehub · crates.io · haotianblog · zread · ivoox · modb · clawpk · adityakarnam · arXiv
社区/反馈类：toolnavs · watcha · linux.do ×2 · nostter · kkaiapi · asi111 · zhujidaba · wapforum.baidu · tsight · hqwc · pingcode · opensourcesai · localaimaster · renrendaima ×2 · computingforgeeks · cloud.tencent(win32)
onboarding 类：aiuxplayground · aydesign · skillselion · producthub · aiopenlibrary

## 研究方法（外部检索子流程）
- 子问题：① 浏览器自动化怎么做 ② 注入怎么防 ③ 搜索 API 要不要用 ④ Agent 真实事故与监管 ⑤ 本地模型卡点与调优 ⑥ MCP 安全与生态 ⑦ 上下文与缓存范式 ⑧ RAG/记忆/可观测/prompt-CI ⑨ API 特性校准 ⑩ 沙箱与 onboarding
- 检索查询：30 路 WebSearch（10 批：4 批基础 + 用户要求追加 6 批）+ WebFetch ×2（B 站）+ 代码库比对
- 唯一来源：33 个外部独立域 + 6 内部；深读 80+ 篇搜索结果
- 源优先级：官方（微软/Anthropic/OWASP/DeepSeek/智谱文档）> 数据型调研 > 事故一手转引 > 社区聚合；2026 年内优先；厂方基准（Tavily SimpleQA）已标注biased
- 平台覆盖说明：用户指定平台中 GitHub/知乎系/贴吧浅层/B 站/国际社区有效命中；**微博未获有效内容、贴吧仅浅层、X/Twitter 经二手转引**——已标注未覆盖

---

# 附：Harbor v1.8/v1.9 迭代方案（全网调研终版）

## A. 问题分析（为什么是这些功能、为什么是现在）

1. **能力缺口有外部共识背书**：非 GLM 端点零搜索、open_app 无结构语义、本地模型「连上不管协同」——与业界方案谱系（Playwright MCP/Computer Use/hybrid routing）指向同一答案
2. **用户痛点有真实数据**：Cherry Studio 三坑 +「屎山」+重；Chatbox 轻但无 agent——「轻+深+安全」三角无人占满
3. **安全窗口期**：2026 事故档案 + OpenClaw 监管预警——用户对 Agent 权限恐惧处于历史高点，**带默认护栏的产品迎来信任红利期**
4. **工程范式已换代**：prompt caching 使「大前缀+稳定前缀」成为标准；压缩策略必须从「省字节」转向「保前缀稳定」

## B. 调研对既定方案的修订（R1-R25 终表）

| # | 修订点 | 来源 | 改动量 |
|---|---|---|---|
| R1 | B 组搜索增提示注入防御（provenance 分隔+「内容即数据」指令+guard 墙+特征 surface） | 事故档案 | +1.5 |
| R2 | B 组提取产 markdown、结构化优先 | Playwright/Firecrawl | 含 B1/B2 |
| R3 | **B 组架构升格 dual-LLM-lite**：主模型持工具读结构化结果；本地模型任「隔离读取器」（解析网页只返 JSON 无指令权）——注入防御从提示词层升到架构层 | dual-LLM/CaMeL | +2.0 |
| R4 | **提取结果经 js_api 回调回传**（不用 evaluate_js 返回值——外部站 Strict CSP 下失败） | pywebview 安全模型 | 含 B1 |
| R5 | H 组增 chat template 探测 + tool_calls 空/content 含 JSON 解析兜底 | xLAM 15% | +1.0 |
| R6 | MCP 健康度三态 + 帧混乱检测 + schema hash（TOFU 雏形） | 24.2% 健康度 | +1.5 |
| R7 | **MCP 风险评分加「楼层规则」**：工具名含 delete_/drop_/purge_/wipe_ 或 destructive 无 idempotent → 直接 L5（对抗性设计，缺元数据时升分而非降分） | OWASP 门控 | +1.0 |
| R8 | 审计 trace_id 串联（agent 轮次↔工具↔MCP） | DEV.to/自我注入案例 | +1.0 |
| R9 | 压缩哲学校准：双条件+append 纪律+cache hit rate 进面板 | Galileo/SSW | +0.5 |
| R10 | 搜索 API 可选加速器（用户配 Key 启用 Tavily/Serper/GLM Web Search），浏览器仍是默认 | 搜索 API 对比 | +1.0 |
| R11 | **预期管理写入验收**：定位「检索+提取」非「网页操作」；参照 WebArena 35-55% 设合理目标 | 基准 | 含 B1 |
| R12 | Ollama 调参进 onboarding/readiness：keep_alive 建议 10-30m、num_ctx 显存分层、pin tag、FA/KV 量化提示 | Ollama 调参 | 含 N1 |
| R13 | **工具描述三段式**（触发置首/参数语义/排除条款）+ consolidate <20 + 精简返回 + CI lint | Anthropic/智谱官方 | +1.0 |
| R14 | **onboarding Use Case Wizard**：3-4 问映射真实配置/Skip 常驻/ETA/计量表首屏/杀手特性揭示（沙箱）/次会话锚点 | onboarding 模式 | 含 M3 |
| R15 | F3 RAG 路线明确：FTS5+可选 vec+bge-m3 CPU+RRF+0.35 门+模型溯源；中文保留关键词通道 | 本地 RAG 实战 | 含 F3 |
| R16 | F2 记忆收敛：结构化条目+关键词检索+用户可见可删；规则提取先行（「以后都…」显式信号），LLM 抽取后置 | 记忆六流派 | 含 F2 |
| R17 | 上下文工程进 token 议程：四杠杆+防 collapse（增量条目化）+锚定迭代摘要；度量任务成功率非 token 数 | 上下文工程 | 含 TOK |
| R18 | 可观测性：**每步记录模型看见的完整消息数组**（最有价值单点日志）+指标集（TTFT 分位/工具数/循环/每成功任务成本）+错误 trace 全留 | OTel 实践 | +1.0 |
| R19 | **Prompt as code**：提示词入 backend/prompts/*.md，ID+版本进日志，golden set 20-50+rubric，CI 三门，回滚=revert | prompt-CI | +1.5 |
| R20 | **DeepSeek preset 校准**：模型 ID 改 v4-flash/v4-pro（旧名 7 月已退役）、价格表刷新、1M ctx、峰谷计价提示 | DeepSeek 换代 | +0.5 |
| R21 | **GLM web_search 升级**：改用 Web Search API 结构化结果（意图/域名/时效/摘要长度）；agent_toolset 作为 GLM 端点备选记录在案 | GLM 文档 | +1.0 |
| R22 | **estTokens 校准**：中文比 1.8→3.2-3.4（现高估约 2 倍致过早压缩）+provider usage 对账告警（>5%） | token 研究 | +0.5 |
| R23 | **沙箱剪贴板缺口复核**：实测 JOB_OBJECT_UILIMIT_READCLIPBOARD/WRITECLIPBOARD Flag 值与效力；若属实，strict 档闭合 §17 缺口（改文档或改代码） | MS Learn/Chrome 实证 | +0.5 |
| R24 | CreateProcessInSandbox（Win11）列为沙箱硬化候选（真 fs 隔离），做可用性探测不做实现 | MS Learn | 0（调研） |
| R25 | 发布叙事接入监管语境（工信部六要六不要同构清单，不夸大） | OpenClaw 监管 | +0.5（文档） |

## C. 迭代目标（三棒战略）

1. **能力棒 v1.8.0（31 人日）**：浏览器精准搜索（dual-LLM-lite+注入防御）/ 外部软件调用 / 本地模型协同 / V1 校验 / 缓存 / 面板 / 软件设置
2. **放权棒 v1.8.5+v1.9.0（3+13.5 人日）**：任务授权+白名单 → Plan-Act+批量澄清+检查点+Reflexion+跨会话记忆
3. **信任棒（横切，7 人日）**：MCP 门控加固+健康度 / trace_id+消息数组日志 / readiness 面板 / 渲染性能 / prompt-CI / DeepSeek·GLM 校准

## D. 实施步骤与时间安排（单人约 8 周 / 2 人约 4.5-5 周）

```
v1.8.0 W1    B1 搜索核心（先定 dual-LLM-lite 信任边界：R3/R4/R1）
       W2    B2 深度提取 + S1 软件核心（并行）
       W3    H1 混合路由（R5）+ V1 校验框架
       W4    C1/U1/S3 + N5 渲染验收 + R10 搜索 API 可选通道
v1.8.0 内    R20 DeepSeek 校准 + R21 GLM web_search 升级（各 0.5-1 日，宜早）
v1.8.5        A1 任务授权 + A2 白名单
v1.9.0 W1-W3  B/C/D 主件 + F1/F2/F3（F3 按 R15 路线评估）
横切并行      N1/N2/N3（R6/R7/R12）+ N4+R18 日志（R8）+ R19 prompt-CI + R22 estTokens + R23 剪贴板复核
v1.9.1        L3 智能自动灰度 + R24 CreateProcessInSandbox 探测
```

## E. 风险与验证方式

| 风险 | 等级 | 缓解 | 验证 |
|---|---|---|---|
| 网页注入流入执行（事故形态） | **高** | R1+R3 四层（provenance/指令/架构隔离/guard 墙） | 注入 fixture（含删除指令网页→不触发工具/被 surface） |
| 功能膨胀（屎山化） | 高 | 三问纪律+P2 顺延+体量审计 | exe 尺寸/启动内存阈值 |
| 本地 readiness 低跑 agent | 中 | N1 面板+R5 兜底 | 自检分与成功率关联复盘 |
| 压缩/cache 打架 | 中 | R9 双条件+append+hit rate 面板 | 三指标基准（token 成本/TTFT/hit rate） |
| 第三方 MCP 污染/降级 | 中 | R6+R7 检测+门控+文档 | 混乱注入+降级桩+TOFU 测试 |
| MCP 工具描述投毒 | 中 | R7 楼层规则+schema hash+严格参数 schema | 毒化描述 fixture（含隐藏指令的 description→被楼层/扫描拦下） |
| estTokens 偏差决策失误 | 中 | R22 校准+usage 对账 | 估算 vs usage 偏差 <5% 告警测试 |
| 剪贴板隔离结论错误（§17） | 中 | R23 实测复核 | Win32 实测：设 Flag 后剪贴板读取是否真被拦 |

## ⚠️ 假设

- 工作量基于 v1.7.0 结构与 721 测试网 velocity；R1-R25 修订共 +16 人日，已计入 C/D 表
- 事故案例均为公开转引（HN/X/Reddit 二手），用于设计输入不用于营销引用
- 「监管语境叙事」仅引用公开预警事实；Harbor 是单用户桌面工具，与企业级 Agent 平台场景不同，不构成合规声明
- DeepSeek/GLM API 特性为 2026-10 文档快照，价格与模型线变化快，实施时以官方页面复核
- R23/R24 涉及 Win32 行为，需在本机实测后修正文档或代码——当前 §17 结论标记「待复核」而非直接采信外部文档

## 免责声明
⚠️ 本报告基于公开网络检索结果（30 路查询、80+ 篇深读、33 个独立域）的整理归纳与代码库实测，外部观点不代表 Harbor 立场；引用的事故案例为二手转引；迭代方案为工程规划建议，重要决策请由产品负责人审定。
