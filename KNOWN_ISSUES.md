# 已知 Bug 与遗留问题清单

**版本**：v1.5.0 | **更新日期**：2026-10-17 | **测试基线**：480 passed / 契约 PASS / 构建幂等

> 状态图例：🔴 未处理 | 🟡 部分处理/有条件规避 | 🟢 已处理（仅记录）

---

## 一、环境限制类（本机无法闭环，需目标机验证）

### 1. 起窗冒烟未做（GUI 真机验证受阻）
- **描述**：v1.3-v1.5 全部功能仅在自动化测试层验证（pytest + node vm 沙箱 + 本地回环服务器），未在真实 WebView2 窗口做端到端冒烟。2026-10-17 尝试三种 GUI 自动化方案均受阻：CDP 端口被本机安全软件拦截 Python 出站连接；开发模式直接跑页面白屏；坐标点击受窗口 z-order 干扰。
- **影响范围**：全部交互功能（理论风险低——测试层已全覆盖，但未经真实窗口确认）
- **处理状态**：🔴 未处理。已在 `main.py` 增加 `GLM_CDP_PORT` 环境变量开关（默认关，生产零影响）为后续验证铺路。

### 2. 本地模型 `/api/tags` 元数据优化未经 UI 真机验证
- **描述**：v1.5 新增的第四级元数据来源（Ollama `/api/tags` 权威声明优先于前缀猜测）在代码层验证通过（含真实 Ollama 实测：qwen3.5-9b → 256k + tools），但未经设置面板 UI 确认展示效果。
- **影响范围**：本地模型元数据徽标显示（窗口值/tool 能力标注）
- **处理状态**：🔴 未处理（代码就绪，重启后在「设置 → 本地模型 → 探测本机」可人工验证）

### 3. 性能基准未实测
- **描述**：MCP 连接池改造目标为「本地回环 P95 -40%」（roadmap §6），WebDAV 上传下载、本地模型冷/温启耗时均无真实基准数据。
- **影响范围**：性能宣称（功能正确性不受影响）
- **处理状态**：🔴 未处理。基准脚本方法已就绪（127.0.0.1 自建回环服务器）。

### 4. WebDAV 未与真实服务器联调
- **描述**：WebDAV 执行器（PROPFIND/PUT/MKCOL/GET + 冲突四策略）仅在本地回环测试服务器验证，未对接真实 WebDAV 服务（坚果云/Nextcloud 等）。
- **影响范围**：WebDAV 备份/恢复的真实服务器兼容性
- **处理状态**：🔴 未处理。已留 `test_connection`（OPTIONS+PROPFIND）供用户一键自检。

---

## 二、平台与兼容性

### 5. 仅支持 Windows
- **描述**：依赖 pywebview（EdgeChromium）、ctypes DPAPI、PIL.ImageGrab、send2trash 等 Windows 专有路径；macOS/Linux 未适配（v1.3 PRD Non-goal）。
- **影响范围**：非 Windows 用户完全不可用
- **处理状态**：🟢 已明确为设计边界（roadmap 未排期）

### 6. 杀软误报风险
- **描述**：PyInstaller onefile 打包的 exe 可能被杀毒软件误报（尤其是含 ctypes/进程操作代码的自更新替换逻辑）。
- **影响范围**：首次运行被拦截 / 自动更新失败
- **处理状态**：🟡 部分处理。发布说明中需提示用户加信任；代码签名未做（成本未排期）。

### 7. WebView2 Runtime 依赖
- **描述**：未安装 WebView2 Runtime 的 Windows 10 旧版系统无法启动（已有友好提示框）。
- **影响范围**：Windows 10 老旧系统
- **处理状态**：🟢 已处理（启动失败弹原生 MessageBox 引导安装）

---

## 三、功能边界（roadmap 已规划未排期）

### 8. MCP resources / prompts 能力未实现
- **描述**：MCP 客户端仅实现 tools 能力；resources/prompts（如 Context7 的 instructions 展示）未接入（roadmap：建议 v1.5 发布后硬化审查再排期）。
- **影响范围**：MCP 服务器的高级能力利用率
- **处理状态**：🔴 未处理（roadmap v1.6+ 候选）

### 9. MCP OAuth 认证未实现
- **描述**：仅支持无认证 / Basic / 自定义 header；需要 OAuth 流的 MCP 服务器不可用。
- **影响范围**：企业级 MCP 服务器接入
- **处理状态**：🔴 未处理（roadmap v1.6+ 候选）

### 10. 多模态输入未实现
- **描述**：截图工具可采集屏幕，但对话输入不支持图片/文件拖拽（v1.3 PRD Non-goal）。
- **影响范围**：视觉对话场景
- **处理状态**：🔴 未处理（roadmap 未排期）

### 11. 云端同步/账号体系未实现
- **描述**：数据主权仅本机 + WebDAV 手动备份；无账号、无自动云同步。
- **影响范围**：多设备同步场景
- **处理状态**：🔴 未处理（WebDAV 为既定方案，v1.6 起）

---

## 四、已知小问题（测试钉住的行为）

### 12. 400 双降级链每轮只走一次
- **描述**：请求带 tools 收 400 时，若同时含 thinking 字段错误与 tools 不支持特征，当轮只降 thinking 不降 tools（下轮才生效）。
- **影响范围**：极小概率场景（自定义端点同时拒两种字段）
- **处理状态**：🟢 已记录为设计取舍（防病态端点诱导无限重试）

### 13. 本地模型元数据为估计值时的标注
- **描述**：前缀启发式推导的窗口/工具能力显示「（估）」标注；用户可在设置手设覆盖（手设值持久化到 config.json）。
- **影响范围**：元数据准确性（有 UI 出口）
- **处理状态**：🟢 已处理（估计值明示 + 手设覆盖 + `/api/tags` 权威源优先）

### 14. 压缩备份上限 50 条
- **描述**：就地压缩的单份可恢复备份超过 50 条后旧备份被挤出（v1.4 设计上限，防磁盘膨胀）。
- **影响范围**：深度压缩历史的可回溯深度
- **处理状态**：🟢 已处理（PRD 既定上限）

---

## 五、用户环境备注（非软件缺陷）

### 15. ModelScope MCP 免费期
- **描述**：用户自配的 ModelScope MCP 端点（函数计算 FC / PAI-DSW）仅三个月免费，到期不可用。
- **影响范围**：该 MCP 服务器的可用性
- **处理状态**：⚪ 用户侧事项（与软件无关）

---

## 六、v1.6 命令沙箱模块（2026-10-19 新增）

### 16. 沙箱已实现：Job Object 进程隔离 + 资源限制（后端核心完成）
- **范围**：run_command/run_powershell 默认走沙箱（standard 档：1GB 内存/16 进程/120s CPU/UI 限制 basic）；run_admin_command 显式排除（提权进程无法被中型父进程收编）；配置 `~/.glm-chat/sandbox.json`（不碰 config.json）；js_api：sandbox_get_config/sandbox_save_config/sandbox_status（隐身）
- **架构与风险矩阵**：deliverables/dev-plan/sandbox-architecture-2026-10-19.md
- **测试**：tests/test_sandbox.py 24 项真实 Win32 API 全过；全量 584 passed / 契约 PASS
- **处理状态**：🟡 后端核心完成；设置面板 UI 未接线（默认开箱生效）；真机起窗冒烟待做（同第 1 条）

### 17. 沙箱的已知能力边界（诚实缺口，文档化接受）
- **网络隔离不可达**：零依赖 + 无管理员前提下，Job Object 不含网络控制；沙箱内进程可外联。缓解：guard 审计可见 + 「netsh 封禁助手」脚本（需用户 UAC，opt-in）
- **剪贴板/截屏隔离不可达**：Job 无剪贴板 UI 限制；沙箱内进程可绕过应用层直接调 Win32 API。由 guard 三档确认兜底（应用层）
- **文件系统越界仅为应用层校验**：未做 ACL/AppContainer（与零依赖单文件约束冲突）；沙箱内进程直接调 API 写工作区外路径理论上可行，威胁模型主要为提示注入驱动的外联（R5/R6 同源）
- **处理状态**：🟡 文档化接受（sandbox-architecture §5 R4/R5/R6）；根治需重新评估定位（AppContainer 或独立低权限用户，涉及打包与启动链）

### 18. 【已修复】P0 潜伏 bug：非桩路径命令「执行成功但向 Agent 报错」
- **根因**：`cmd_service._exec` 的 Popen 路径 `return proc`——`proc.stdout` 是 BufferedReader 而非字节，`_dec(result.stdout)` 必抛 AttributeError。自 v1.1 重构起存在，被测试桩（stub subprocess.run）全面掩盖；真机现象=命令实际执行（弹窗/副作用发生）但 Agent 收到错误 → 重试 → 「cmd 反复弹窗」用户报告的部分同源
- **修复**：返回 `subprocess.CompletedProcess(popen_args, proc.returncode, communicate() 捕获的字节)`；回归测试 `test_cmd_service_no_sandbox_path_unchanged`（沙箱集成时实测发现）
- **处理状态**：🟢 已修复（584 passed 含回归）

---

## 发布检查清单（上传前确认）

- [x] 全量测试 480 passed
- [x] UI 契约 check_contract.py PASS
- [x] 前端构建 40 模块幂等
- [x] 敏感信息扫描干净（无 API Key / 无个人 MCP 配置 / 无 DPAPI 密文）
- [x] VERSION = 1.5.0，exe 内嵌版本一致
- [x] 窗口标题显示应用版本（v1.5.0）而非契约版本
