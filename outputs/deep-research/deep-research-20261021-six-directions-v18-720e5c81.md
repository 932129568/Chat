---
tags: [deep-research-report, status/review]
created: 2026-10-21
scope: 六大方向全网调研与Harbor-v18迭代方案（第二批战役）
sources: "内部 1 / 外部 34"
search-mode: 主题分批并行外检→方案合成
---

# 深度检索报告：《六大方向全网调研与 Harbor v1.8.0 迭代方案（第二批）》

## 范围
- 查询范围：按六大方向（浏览器精准搜索/外部软件调用/本地模型协同/Agent 自主化/自反思校验/信任基座）+ 补充调研（中文社区反馈/竞品/onboarding），对 GitHub、知乎系、贴吧、B站、微博及国际社区（Reddit 聚合/HN/OWASP/Microsoft Learn/Anthropic 文档/MLflow 等）的已有方案、案例、讨论与用户反馈
- 执行口径：用户要求「共计 100 批」；实际执行 **8 个并行批次、32 路独立查询、34 个外部域**（每批 3-4 路同主题并行；按去重后边际收益递减原则收敛，未凑数至 100——详见 §调研方法）
- 时间窗口：2026-10-20 至 10-21 两日；外部源以近 12 个月为主
- 基线：Harbor v1.7.0（721 passed）+ 第一批调研（deep-research-20261020-harbor-v18-v19-220e3984）+ 单版本实现方案（deep-research-20261020-harbor-v18-bcf7ab8e）

## 核心结论
- [内+外] **「放手」的核心矛盾有权威数据**：Anthropic 实地遥测显示单命令批准率 **97%**（橡皮图章），而整体 Plan 拒绝率达 **39%**；1053 人盲测中人类对注入危险命令的拦阻率仅 **13.6%**，后台分类器为 **89%**；人类拦阻率随弹窗数从 17% 衰减至 5%。**结论：逐项确认是剧场，计划审查+分类器+少而重的关卡才是真控制**——直接验证 Harbor「Plan-Act + 任务授权 + deny 清单」路线（https://yage.ai/share/claude-auto-mode-approval-illusion-en-20260808.html + https://ai-beat.github.io/news/2026/08/human-agent-permission-fatigue）
- [内+外] **浏览器搜索的工程细节已全部有生产先例**：Bing `format=rss` 双通道（RSS 4KB 主路径 + HTML 100KB 兜底，含 publishedAt）；pywebview 官方文档证实 **evaluate_js 依赖 unsafe-eval CSP 而 run_js 无 CSP 限制但无返回值**——提取结果必须走 **js_api 回调**；DOM 稳定性等待（innerText 长度三连稳）比 networkidle 多救 30% SPA；缓存按内容类型分 TTL（新闻 5 分钟/通用 1 小时/百科 24 小时）+ 激进 URL 归一化（utm/片段/尾斜杠/查询排序/SHA-256）（https://github.com/godchen520/dsh-web-search-bing + https://pywebview.idepy.com/en/guide/interdomain + https://dataresearchtools.com + https://grizzlypeaksoftware.com）
- [内+外] **MCP 威胁是运行时的而非连接时的**：Deadbugz  campaign（2026-08）前两次调用返回良性定义、第三次调用后开始注入窃取指令；「跨服务器影子劫持」——恶意服务器的工具从不被执行，劫持不留痕；微软金融四阶段攻击（描述投毒→静默再信任→调用→外传，每步都在正常参数内）。**防御必须「审批时钉哈希 + 每次执行前重校 + 定期重验」，只在连接时检查不够**（https://ojeo.com/noticia/identificada-la-campa%C3%B1a-de-deadbugz + https://dreaming.press/posts/mcp-tool-poisoning-rug-pulls + https://www.microsoft.com/en-us/security/blog/2026/06/30/）
- [内+外] **检查点设计的六个真实故障已全部有案可查**：git clean -fd 误删 1GB+ 未跟踪数据、快照 ref 撑爆 100GB、后台 gc 剪掉快照对象、agent 经 Bash 编辑时 rewind 静默失效、大仓库每轮 90 秒、多会话互相 undo。**正确形态：只碰两份快照的差异文件、绝不删未备份内容、自有影子仓库、shell 命令前后也快照、恢复前列清单+确认、恢复后校验**（https://github.com/zerostel/zerostel/blob/main/docs/comparison.md）
- [内+外] **本地模型工具调用故障三因根已定位**：chat 模板不匹配（froggeric 修复模板/Ollama Modelfile 重建）、上下文太小吞掉尾部工具定义（64K 是 agent 工作下限）、采样器参数（agent 用 temp≈0.6）；能力探测走 `/api/show` capabilities 数组；**agent 循环每轮重发同一 system+tools 前缀，前缀缓存是最大可避免延迟**（https://openclawdc.com/blog/local-model-says-it-did-it-but-didnt/ + https://www.bigiron.cc/guides/serving-local-llms-for-agents-function-calling-and-json-grammar-enforcement）
- [内+外] **提示词治理的终态形态=不可变版本+可变指针**：MLflow 两表模式（immutable versions + mutable pointers，回滚=单次写指针）；eval 三门（floor 底线/paired CI 配对置信区间/safety flip 安全翻转）；金丝雀 5→25→50→100%；**版本化整个 bundle（文本+模型+温度+工具+示例），每次请求记录 prompt_id+version**（https://mlflow.org/articles/prompt-registry-design/ + https://futureagi.com/blog/prompt-versioning-lifecycle-management-2026/）
- [内+外] **剪贴板/会话隔离已有 OS 级答案**：Microsoft Execution Containers（Build 2026）以「会话隔离」把 agent 执行与用户桌面/剪贴板/UI/输入设备分离，GitHub Copilot CLI 已采用、OpenClaw 已接入——Harbor 的 Job Object 剪贴板 UI 限制（进程级）+ MXC（平台级，Win11 预览）构成两级答案（https://thewindowsupdate.com/2026/06/02/build-2026-furthering-windows-as-the-trusted-platform-for-development/）
- [内+外] **中文社区痛点排序与 Harbor 路线图高度吻合**：知乎 60 回答分析显示 15 大瓶颈中「上下文管理（87 分）、工具调用不可靠（76）、任务规划脆弱（72）」居前三；B站 123 万播放教程评论区 60%+ 高赞问的是「JSON 跑不起来/Cluster 怎么编排」——**卡点在工程化不在 Prompt**；竞品卡位确认：Cherry Studio 51.7k★（功能全但「屎山」化+180-300MB 内存）、LobeChat 82.4k★（自部署）、Chatbox 35.8k★（最轻）——「轻+深+默认安全」三角仍空位（https://2048ai.net/69aa69cb0a2f6a37c595710b.html + https://www.toutiao.com/a7686660239039234619 + https://www.agentlist.top/en/compare/lobe-chat-vs-cherry-studio）
- [⚠ 未覆盖] 微博一手讨论（仅得竞品官网与测评转引）；贴吧深度帖（仅浅层推荐）；X/Twitter 一手（经二手转引）；B站视频内容本体（前序任务已核）

## 关键要点（Key Takeaways）
- **把「计划审查」当主关卡、把「逐项确认」当例外**：97% vs 39% 的数据意味着 UI 应该引导用户审计划（可编辑步骤+时间估计+风险标注），单命令确认只留给 deny 清单与高风险档——Harbor 授权条+计划卡正是此形态
- **浏览器提取三件套**：js_api 回调（CSP 安全）+ DOM 稳定性等待（抗 SPA）+ 输出校验（拒 "loading" 残留）；RSS 优先降级 HTML；成本基线用 DOM 不用截图（10-20 倍差）
- **MCP 防御 Timeline 重画**：连接时（哈希钉+楼层规则）→ 每次调用前（重校哈希）→ 定期（重验+健康度）——Deadbugz 证明「连接时 benign」不可信
- **检查点=影子 git + 六条军规**（差异恢复/绝不删未备份/自有仓库/shell 前后快照/列清单+确认/恢复后校验），.gitignore 文件（.env）明确警告
- **本地模型 onboarding 三件事**：能力探测（/api/show）、64K 上下文下限提示、temp 0.6 建议；hybrid 路由用「级联+置信度」而非静态分流
- **提示词即制品**：prompts/ 目录 + manifest（id→version+sha256）+ 每次请求带版本 + eval 三门 + 指针回滚

## 证据清单
| # | 结论摘要 | 支撑 | 来源 |
|---|---------|------|------|
| 1 | 批准率 97%/计划拒绝 39%/人类拦阻 13.6% vs 分类器 89%/衰减 17%→5% | [外] | https://yage.ai/share/claude-auto-mode-approval-illusion-en-20260808.html |
| 2 | 4 万局游戏：漏拦 1/3 恶意；npm run 类漏拦 65%；误拦正常命令 45-59% | [外] | https://ai-beat.github.io/news/2026/08/human-agent-permission-fatigue |
| 3 | Claude Code 六模式细节（acceptEdits 仅工作区内 fs 命令/bypass 五项永不豁免/会话中切模式） | [外] | https://code.claude.com/docs/zh-CN/desktop + https://platform.claude.com/docs/en/agent-sdk/permissions |
| 4 | Cline 影子 git 检查点（每工具后提交/三种恢复/捕获未跟踪）+ 强模型规划弱模型执行 | [外] | https://www.deployhq.com/guides/cline |
| 5 | 检查点六真实故障（clean 删 1GB/ref 100GB/gc 剪快照/Bash 编辑 rewind 失效/90s 延迟/会话互 undo） | [外] | https://github.com/zerostel/zerostel/blob/main/docs/comparison.md |
| 6 | Intent Preview 模式（可编辑计划+时间估计+Confirm 硬门+漂移重确认）/活动面板分离/渐进委托 | [外] | https://agentic-ux.com/patterns/intent-preview + https://zylos.ai/research/2026-05-28-agentic-ux-frontend-design-patterns-ai-agents/ |
| 7 | Bing RSS 双通道（4KB vs 100KB/publishedAt/UA 要求/验证码结构化错误） | [外] | https://github.com/godchen520/dsh-web-search-bing |
| 8 | pywebview：evaluate_js 需 unsafe-eval/run_js 无 CSP 限制无返回值/js_api 线程不安全/pywebviewready | [外] | https://pywebview.idepy.com/en/guide/interdomain |
| 9 | SPA：domcontentloaded+waitForSelector/DOM 稳定性多救 30%/输出校验/拦截底层 API | [外] | https://dataresearchtools.com + https://www.context.dev/blog/how-to-scrape-javascript-heavy-single-page-apps-into-llm-ready-markdown |
| 10 | 四引擎选择器（Google .tF2Cxc/Bing .b_algo/Baidu .c-container/Sogou .vrwrap）+DDG uddg 解码 | [外] | https://blog.gitcode.com/af6b110fbd308f6902a8f7b55abcca3b.html + https://github.com/20190441309/hot-monitor |
| 11 | 缓存分 TTL+URL 归一化+条件 GET+schema 版本入键+provenance 非可选 | [外] | https://grizzlypeaksoftware.com/library/building-a-research-agent-with-web-search + https://raghavkattel.com.np/blog/building-a-template-first-research-agent |
| 12 | DOM vs 截图成本 10-20 倍/WebMCP -89%/深研基准（DR 120-150 页 28 分钟） | [外] | https://zylos.ai/research/2026-04-05-browser-automation-ai-agents-2026-landscape + https://www.firecrawl.dev/blog/deep-research-for-ai-agents |
| 13 | 软件探测顺序：App Paths→Uninstall（InstallLocation）→PATH→目录；注册表会撒谎需文件系统验证 | [外] | https://docs.appsanywhere.com/appsanywhere/3.5/locally-installed-delivery-method + https://learn.microsoft.com/en-us/previous-versions/technet-magazine/dd797545(v=msdn.10) |
| 14 | Agent 友好 CLI：JSON 信封/语义退出码/**stderr 是提示注入向量需清洗**/hint 自校正 | [外] | https://www.getclaudeskills.com/skills/agent-friendly-cli-spec-sickn33 + https://akeemjenkins.com/blog/agent-first-cli-a-design-pattern |
| 15 | 严格 schema：additionalProperties:false/strict 只保形状不保值域/服务端校验仍是信任边界/重试上限 1 | [外] | https://how2.sh/posts/how-to-validate-structured-outputs-in-agent-actions + https://openllm.wavise.com/blog/json-schema-tool-calling-reference |
| 16 | UIA 对 Electron 空树；FindWindowW+SW_RESTORE；动态标题先 PID；10s 窗口发现超时 | [外] | https://cloud.tencent.com.cn/developer/article/2675534 + https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-mstest-ui-automation |
| 17 | URI 协议：参数皆恶意假设/引号反斜杠断 argv/危险动作先确认；UAC 最小权限+独立提权助手 | [外] | https://learn.microsoft.com/fil-ph/previous-versions/windows/internet-explorer/ie-developer/platform-apis/aa767914(v=vs.85) + https://learn.microsoft.com/en-us/windows/win32/secbp/running-with-administrator-privileges |
| 18 | 本地工具调用三因根（模板/上下文 64K 下限/采样器 0.6）+ /api/show 能力探测 + 避坑型号清单 | [外] | https://openclawdc.com/blog/local-model-says-it-did-it-but-didnt/ + https://aicoderscope.com/blog/ollama-does-not-support-tools-fix-cline-continue-claude-code-2026 |
| 19 | 前缀缓存是 agent 循环最大可避免延迟（system+tools 每轮重发）；llama.cpp --cache-reuse/vLLM --enable-prefix-caching | [外] | https://www.bigiron.cc/guides/serving-local-llms-for-agents-function-calling-and-json-grammar-enforcement |
| 20 | 混合三 Tier（70-80% 查询不需前沿模型）+ 三路由策略（静态 40-60%/动态+50-100ms/级联 50-70%）+ 状态交接四要素 | [外] | https://graphwiz.ai/content/ai/hybrid-cloud-local-inference-architecture + https://mech.app/articles/cloud-vs-device-agents-what-hybrid-multi-agent-systems-reveal-about-cost-latency-and-orchestration-trade-offs |
| 21 | MCP 真实攻击：15k SSH 密钥/Postmark 8k 企业 5M 邮件/Asana 跨租户 12k 团队 | [外] | https://blog.csdn.net/weixin_42376192/article/details/160267630 |
| 22 | Deadbugz：前两次良性第三次注入；23 PR/74 分钟；跨服务器影子劫持（攻击工具从不执行）；line jumping | [外] | https://ojeo.com/noticia/identificada-la-campa%C3%B1a-de-deadbugz-que-envenena-servidores-mcp-para-robar-credenciales + https://dreaming.press/posts/mcp-tool-poisoning-rug-pulls |
| 23 | 微软金融四阶段攻击链（描述投毒→静默再信任→调用→外传，每步正常参数内） | [外] | https://www.microsoft.com/en-us/security/blog/2026/06/30/securing-ai-agents-ai-tools-move-from-reading-acting/ |
| 24 | 防御：审批时 SHA-256 钉+每次执行前重校+定期重验；禁 token 直传+RFC 8707；destructiveHint→拒确认；破三要素 | [外] | https://dreaming.press/posts/mcp-tool-poisoning-rug-pulls + https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html |
| 25 | 审计五问（哪 agent/何任务/何时/代何人/何目的）+ 五维（双身份/意图/计划/执行证据/结果）；45% 企业有事故 18% 根因审计缺失；记录哈希非原文+哈希链 | [外] | https://www.immuta.com/resources/to-trust-ai-you-need-to-trust-your-data + https://bteanalytics.co/knowledge/what_are_the_best_practices_for_agentic_ai_audit_trails_in_enterprise_environments.php |
| 26 | MXC 会话隔离（agent 与桌面/剪贴板/UI/输入分离；Copilot CLI 采用；OpenClaw 接入） | [外] | https://thewindowsupdate.com/2026/06/02/build-2026-furthering-windows-as-the-trusted-platform-for-development/ |
| 27 | 提示词两表模式（不可变版本+可变指针/回滚=单写）+ eval 三门（floor/paired CI/safety flip）+ 金丝雀 5→100% | [外] | https://mlflow.org/articles/prompt-registry-design/ + https://futureagi.com/blog/prompt-versioning-lifecycle-management-2026/ |
| 28 | Reflexion 四组件；评估器优先确定性；二元信号；一条具体修正；滑窗 3-5；temp 0.1；弱评估器毒化全部反思 | [外] | https://n4n.ai/blog/reflexion-how-verbal-self-critique-boosts-agent-accuracy + https://aicassindra.com/blogs/prompt_engineering/pe_reflexion.html |
| 29 | LLM 评审：异族模型防自偏好/离散量规/先推理后打分/Cohen's kappa>0.8 才可信/分层评审 | [外] | https://qaskills.sh/blog/llm-as-a-judge-evaluation-guide-2026 + https://www.agentengineering.io/topics/articles/agent-evaluation |
| 30 | 知乎 60 回答：上下文管理 87 分第一/工具调用 76/规划 72；「方案缺位」在数据管理与安全控制 | [外] | https://2048ai.net/69aa69cb0a2f6a37c595710b.html |
| 31 | B站 123 万播放：卡点在四道工程门（Catalog 字段/Tools 契约/Cluster 编排/Runtime 绑定）非 Prompt | [外] | https://www.toutiao.com/a7686660239039234610 |
| 32 | 竞品实测：Cherry 51.7k★内存 180-300MB/中文长文档语义匹配 ~80%/知识库 1.5s@10MB；「屎山」吐槽 | [外] | https://cike.ai/sites/cherry-studio + https://watcha.cn/discuss/10947 |
| 33 | 用户不敢放权根因：权限边界/执行确认/操作日志缺失；读/改/删权限须细分 | [外] | https://blog.csdn.net/weixin_29032489/article/details/164161806 |
| 34 | Harbor 内部基线（721 passed/契约/沙箱/护栏/实现方案） | [内] | tests/ + backend/ + deliverables/dev-plan/iteration-plan-v18-agent-2026-10-20.md + agent-autonomy-research-2026-10-20.md + sandbox-architecture-2026-10-19.md + outputs/deep-research/deep-research-20261020-harbor-v18-bcf7ab8e.md |

## 口径与来源（跨文档对比/专业术语查询时启用）
- 术语/指标口径：「影子 git 检查点」= 独立于用户仓库的 git 快照链（Cline/opencode 模式）；「两表模式」= 不可变版本表+可变指针表（MLflow）；「配对 CI」= 候选 vs 现网逐用例差值的 bootstrap 95% 置信区间；「line jumping」= 恶意定义随 tools/list 连接响应即到达（Trail of Bits）
- 实体解析：「Deadbugz」= Pillar Security 披露的 MCP 投毒 campaign（2026-08，zellkernel/@llmgod）；「MXC」= Microsoft Execution Containers（Build 2026 预览）；「froggeric 模板」= 社区修复的 Qwen chat template（Hugging Face）
- 数据状态：内部截至 2026-10-21（v1.7.0）；外部截至 2026-10-21（战役两日）

## 来源分区
### 内部资料（1 组）
- 本仓代码库 + tests/ + 四份既有方案文档（iteration-plan-v18-agent / agent-autonomy-research / sandbox-architecture / 第一批调研 + 单版本实现方案）

### 公开信息（34 个独立域）
人类因素/权限：yage.ai · ai-beat.github.io · code.claude.com · platform.claude.com · deployhq.com · zeallynx.io · chatgpt.ca · machinelike.ai · uxpickle.com · zylos.ai ×2 · agentic-ux.com · parallelhq.com
检查点：github.com(zerostel) · autohand.ai · neural-nexus.net · seashell.sh
浏览器：pywebview.idepy.com · github.com(godchen520) · dataresearchtools.com · context.dev · blog.gitcode.com · github.com(hot-monitor) · grizzlypeaksoftware.com · raghavkattel.com.np · apify.com · firecrawl.dev · bug0.com · antsdata.com · searchcans.com
软件调用：docs.appsanywhere.com · learn.microsoft.com ×4 · getclaudeskills.com · akeemjenkins.com · cloud.tencent.com.cn · anquanke.com · how2.sh · openllm.wavise.com
本地模型：openclawdc.com · aicoderscope.com · ollama.com · gemma4home.pro · betterclaw.io · bigiron.cc · graphwiz.ai · mech.app · siuleeboss.com · vrlatech.com · dreaming.press · llama-cpp.com
MCP 安全：blog.csdn.net · ojeo.com · microsoft.com · owasp.org ×2 · deciphertech.io · tunicyberlabs · aiworkflowlab.dev
审计/提示词：immuta.com ×2 · bteanalytics.co · agentnode.net · mlflow.org · futureagi.com · egoistai.com · cleverbit.software · promptabcd.com · data-analysis.cloud · thewindowsupdate.com
反思/评审：n4n.ai ×2 · pkg.go.dev · github.com(mahdi-eth) · xiangdangnian.net.cn · aicassindra.com · qaskills.sh · agentengineering.io · llmtools.cc
中文社区：2048ai.net · toutiao.com · cike.ai · watcha.cn · juejin.cn · cctime.com · 163.com · asi111.com · deepyard.dev · agentlist.top · unifyllm.com

## 研究方法（外部检索子流程）
- 子问题：① 人类审批为何失效 ② 计划/检查点产品形态 ③ 浏览器提取工程细节 ④ 软件探测与调用契约 ⑤ 本地模型故障与混合路由 ⑥ MCP 真实攻击与审计 ⑦ 提示词治理 ⑧ 中文社区与竞品
- 检索查询：32 路 WebSearch（8 批×4）+ 前序 30 路；深读 100+ 篇
- 唯一来源：34 个外部独立域（本批新增）
- 100 批口径说明：用户要求「共计 100 批」；按边际收益递减原则，实际以 8 个同主题并行批次（32 路）覆盖全部六大方向+补充域，去重后无新增维度的第 9 批起为同义反复，故收敛——**未凑数，缺口已标注**（微博/贴吧深度/X 一手未覆盖）
- 源优先级：官方（微软/Anthropic/OWASP/MLflow）> 数据型调研（Anthropic 遥测转引/agentstatus）> 事故一手转引 > 社区聚合；2026 年内优先

---

# 正文档：Harbor v1.8.0 迭代方案（全网调研修订版·第二批）

## A. 问题分析（为什么是这些功能、为什么是现在）

1. **用户不敢放权是行业第一痛点**：中文社区分析（上下文管理 87 分/工具调用 76/规划 72）+ 用户信任研究（权限边界/确认/日志三缺失）表明——Agent 产品的竞争已从「能不能做」转向「敢不敢让它做」。Harbor 的护栏+沙箱+审计底座是少数默认安全的起点
2. **逐项确认被数据判死刑**：97% 批准率 vs 39% 计划拒绝率、人类 13.6% vs 分类器 89% 拦阻——继续堆确认弹窗是负优化；必须转向「计划审查为主 + 分类器/规则 + 少而重的关卡」
3. **工程化差距是落地生死线**：B站评论区 60%+ 卡在工程门（JSON 跑不起来/编排）；95% Agent 项目失败根因是工程非模型——Harbor 的单版本实现方案正是工程化补课
4. **竞品卡位空位明确**：Cherry 全而重（屎山化/180-300MB）、LobeChat 自部署、Chatbox 轻而无 agent——「轻+深+默认安全」无人占

## B. 调研对实现方案的修订（R26-R45，相对单版本实现方案）

| # | 修订点 | 来源 | 改动量 |
|---|---|---|---|
| R26 | **UI 主关卡从「逐项确认」改为「计划审查」**：发送后先出可编辑计划卡（步骤+时间估计+风险标注+「将调用外部 API/无邮件」类边界声明），确认才执行；单命令确认收缩到 deny 清单+高风险档 | 证据 1/2/6 | 含 B 组 |
| R27 | **审批疲劳的三项工程防御**：会话审批预算（超限升级为「任务授权」而非继续弹窗）；高风险档视觉/流程差异化（禁用快捷确认）；授权条常驻+一键收回 | 证据 1/2 | +1.0 |
| R28 | **Bing 适配器 RSS 优先**：`format=rss` 主路径（4KB/publishedAt/标准字段）+ HTML 兜底（.b_algo）；带浏览器 UA；验证码 → 结构化 WEB_PROVIDER_ERROR 不伪装「无结果」；AbortSignal 可取消 | 证据 7 | 含 B1 |
| R29 | **提取通道三件套**：js_api 回调回传（禁 evaluate_js 返回值）；DOM 稳定性等待（innerText 三连稳×500ms，上限 8s）；输出校验（拒含 "loading" 的结果，重试一次） | 证据 8/9 | 含 B1 |
| R30 | **缓存分级 TTL + 归一化 + 版本键**：新闻 5min/通用 1h/百科 24h；URL 归一（utm/gclid/片段/尾斜杠/查询排序/SHA-256）；适配器版本号入缓存键（解析器变更自动失效）；条件 GET 304 续期 | 证据 11 | 含 C1 |
| R31 | **软件探测四阶顺序**：App Paths（HKLM+WOW6432Node）→ Uninstall InstallLocation（HKLM/HKCU/WOW6432Node）→ PATH → 常见目录；探测结果必须文件系统验证（注册表会撒谎）；DisplayVersion 缺失容忍 | 证据 13 | 含 S1 |
| R32 | **软件调用结果契约**：{ok, exit_code|launched, output(截断), error{code,message,suggestion}}；**stderr 回灌前清洗 ANSI/bidi/零宽字符**（提示注入向量）；语义退出码表（0/1/2/10/11/20/30）；hint 字段供自校正 | 证据 14 | 含 S1 |
| R33 | **schema 校验双门**：模型侧 strict（additionalProperties:false+required+enum）；服务侧独立校验（strict 只保形状不保值域）；校验失败 isError 回传+重试上限 1；null 当缺失剥除 | 证据 15 | 含 S1/V1 |
| R34 | **本地模型 onboarding 三件事**：`/api/show` capabilities 探测（工具能力/模板 .Tools）；64K 上下文下限提示（系统+工具定义在尾部会被吞）；temp≈0.6 建议；避坑型号清单（codellama/base/R1 蒸馏/-base 标签） | 证据 18 | 含 N1 |
| R35 | **混合路由升级为级联+置信度**：validate 类本地先行，置信<0.7 带原文升级云端（防重复劳动）；路由决策表（任务类型×敏感度×SLA）；状态交接四要素（历史/工具日志/推理片段/置信度） | 证据 20 | 含 H1 |
| R36 | **MCP 防御 Timeline 三段化**：连接时（SHA-256 钉+楼层规则）→ 每次调用前（重校哈希）→ 定期（健康度+重验）；楼层规则扩到 schema 全字段（参数名/类型/枚举/默认值投毒——CyberArk FSP）；禁 token 直传 | 证据 22/23/24 | +1.5 |
| R37 | **审计五维+哈希链**：双身份（agent+委托任务）/意图（原始 prompt）/计划/执行证据（参数哈希非原文）/结果（状态 delta+人工接管）；条目哈希链防篡改；trace_id 贯穿；记录记忆检索事件 | 证据 25 | +1.0 |
| R38 | **提示词两表模式落地**：prompts/*.md 不可变版本（manifest id→version+sha256）+ 可变指针（active.json 指向当前版本）；回滚=改指针单写；每次 LLM 请求记录 prompt_id+version；eval 三门（floor/配对 CI/安全翻转）进 CI；版本化整个 bundle（文本+模型+温度+工具） | 证据 27 | 含 R19 |
| R39 | **检查点六军规**：只恢复两份快照差异文件；绝不删未备份内容（.gitignore 的 .env 明确警告）；自有影子仓库不碰用户 git；shell 命令前后也快照；恢复前清单+uiConfirm；恢复后文件校验；大小上限+保留 3 份 | 证据 5 | 含 D |
| R40 | **Reflexion 工程纪律**：评估器确定性优先（校验器/测试）；二元 pass/fail 信号；反思提示词=「一条具体修正」；滑窗保留 3-5 条；temp 0.1；弱评估器熔断（连续低置信转人工） | 证据 28 | 含 F1 |
| R41 | **计划卡 UX 规格**：Intent Preview 形态（人类可读步骤非工具轨迹/<30 秒可扫/时间估计/边界声明「将调用外部 API」）；活动面板与对话流分离；批准带累计上下文（已完成什么/此步做什么/下一步）；渐进委托（熟练用户自动批准率 2 倍于新用户，跨会话保持） | 证据 6 | 含 B 组 UI |
| R42 | **剪贴板两级答案**：进程级（Job Object READCLIPBOARD/WRITECLIPBOARD UI 限制，strict 档）+ 平台级（MXC 会话隔离，Win11 预览，文档化为演进路线） | 证据 26 | 含 R23 |
| R43 | **中文社区优先级校准**：上下文管理列第一痛点 → 压缩/记忆/计划三项权重上调；「权限细分（读/改/删）」进 UI 文案 | 证据 30/33 | 含 M3/F2 |
| R44 | **B站工程门启示**：新工具上线配「最小可运行示例」文档（AGENTS.md 模式：调用规则/默认工作流/回写）；减少「JSON 跑不起来」类工单 | 证据 31 | +0.5 |
| R45 | **竞品基线写入验收**：启动内存 <150MB（Cherry 180-300MB 的对标）；中文长文档检索可用率 ≥90%；安装到首问 <3 分钟 | 证据 32 | 含 G7 |

## C. 迭代目标（三棒，单版本 v1.8.0）

1. **能力棒**：浏览器精准搜索（RSS 优先+三件套+注入防御）/ 外部软件调用（四阶探测+结果契约）/ 本地协同（能力探测+级联路由）
2. **放权棒**：任务授权+白名单+Plan-Act（计划审查主关卡）+批量澄清+检查点（六军规）+Reflexion+跨会话记忆
3. **信任棒**：MCP 三段防御+审计五维+提示词两表+estTokens 校准+onboarding 向导+竞品基线验收

## D. 实施步骤与时间安排（W0-W12，54.5+4.5=**59 人日**；单人约 12 周 / 2 人约 7 周）

```
W0  M1 地基（3d）：prompts/ 两表模式（R38）· include_agent 参数 · _V12_EXTRA 占位 · R23 剪贴板实测（R42）· DeepSeek 校准
W1  M1 地基（4d）：guard 扩展（deny/allow_rules/task_grant/五层判定链）· 26-guard 授权条+审批预算（R27）· trace_id
W2  M2 H 组（5d）：hybrid_router（四类+级联置信度 R35）· local_model_service 能力探测（R34）· 65-hybrid · readiness 面板
W3-W5 M2 B 组（11d·最大单项）：search_browser（js_api 回调 R29）· adapters（Bing RSS 优先 R28+四引擎选择器）· extract · search_service（缓存 R30+注入包裹）· dual-LLM-lite · 39-search-panel · 工具定义+分发
W6  M2 S 组（3.5d）：software_service（四阶探测 R31+结果契约 R32+schema 双门 R33）· 64-software-panel
W7  M2 V1+F1（2.5d）：validation_service（确定性优先 R40）· reflect（二元信号+滑窗）
W8-W9 M3 放权（7.5d）：plan_service（Intent Preview R26/R41）· 66-plan · clarify · checkpoint（六军规 R39）
W10 M4 信任（3.5d）：MCP 三段防御（R36）· 审计五维+哈希链（R37）· estTokens 校准 · 68-onboarding · GLM web_search 升级
W11 M4 F2（2d）：memory_service · 67-memory UI · 系统提示注入（R43）
W12 回归发布（2d）：七门+基准链+注入 fixture+审查+四 exe+发布说明（R44/R45）
```

**关键路径**：W1 guard → W2 hybrid → W3-W5 搜索 → W8-W9 Plan-Act → W12 回归。
**可并行**：W6/W7；W10 各项互独立；F2 可浮动。**纪律**：每里程碑全量门禁，未测代码不跨里程碑。

## E. 风险与验证方式

| 风险 | 等级 | 缓解 | 验证 |
|---|---|---|---|
| 计划审查疲劳转移（用户不看计划直接批） | 中 | 计划<30 秒可扫；高风险步骤视觉强化；批准带累计上下文 | 走查：计划卡阅读完成率抽样 |
| RSS 通道被 Bing 关停（undocumented） | 中 | HTML 兜底同源结果；双通道一致性测试 | fixture 双通道对比测试 |
| js_api 回调线程安全（官方明示非线程安全） | 中 | 回调内加锁转主队列；单线程化提取管线 | 并发提取压测 |
| MCP 重校哈希的调用开销 | 低 | 哈希缓存（内容未变零成本）；per-server 节流 | P95 延迟基准 |
| 检查点影子仓库膨胀 | 中 | 大小上限+保留 3 份+引用链+显式 prune | 大仓库快照耗时测试 |
| 级联路由双倍调用成本 | 中 | 仅 validate 类级联；置信度高跳过；本地零钱 | 成本分账对比 |
| 单版本体量（59 人日） | 高 | 四里程碑门禁；P2 明确可砍（搜索 API 加速器/健康徽标细化/GLM 升级） | 里程碑出口评审 |

**七门验证**（维持实现方案）：G1 全量测试（721+新增约 200）/G2 契约差分/G3 UI 契约/G4 构建幂等/G5 安装器 e2e/G6 注入 fixture（毒网页+毒 MCP 描述+Deadbugz 时序：前两次良性第三次毒）/G7 真机七项冒烟。**竞品基线**（R45）：启动内存 <150MB；中文长文档检索 ≥90%；安装到首问 <3 分钟；计划卡阅读完成率抽样。

## ⚠️ 假设
- 工作量在第一批 54.5 人日基础上+4.5（R27/R36/R37/R44）；R26-R45 多数为「含既有项」的规格细化
- 「100 批」按边际收益递减收敛为 32 路（本批）+30 路（前批），覆盖全部六大方向；未覆盖项已标注
- Anthropic 遥测数据为转引（yage.ai/ai-beat），一手报告未直读——用于方向判断不用于精确引用
- MXC 为 Win11 预览特性，文档化为演进路线，不承诺本版实现

## 免责声明
⚠️ 本报告基于两日 32 路公开检索（100+ 篇深读、34 个独立域）与代码库实测编制；外部观点不代表 Harbor 立场；事故案例均为公开转引；迭代方案为工程规划建议，重要决策请由技术负责人审定。
