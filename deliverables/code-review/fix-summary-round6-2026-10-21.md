# Harbor 第六轮·对抗复审与遗留清剿汇总（2026-10-21 晚）

> 前置：第五轮 85 项修复（077e8e1）后，用户又推进两个 UI 提交（869f0d4/2289a9e）。本轮任务：① 对第五轮修复逐项对抗证伪（构造反例验证修复本身是否成立/引入新缺陷）；② 清剿前五轮审查遗留的未修项。
> 验证终态：**pytest 1133 passed / 1 skipped / 0 failed；check_contract PASS；前端重建 55 模块 15624 行**。

## 对抗证伪结论：第五轮修复 3 处不成立（已修），其余成立

| 轮5 修复 | 证伪结果 | 处置 |
|---|---|---|
| 计划收尾以 `finished` 为条件 | **不成立**：熔断/预算硬停/length 截断续跑路径同样置 finished=true → 计划被谎报「✓ N 步全部完成」并落库 done、回滚入口失效 | 分离 `naturalDone` 判据（仅「AI 回复无工具调用」正常终结置位），抽 `planFinishIfNatural()` 模块级函数可单测 |
| 会话信任 fire-and-forget 登记后端 | **不成立**：桥异常/旧后端时前端 Set 已加、后端未登记 → 前端短路不弹窗、后端武装态拒 → AI 重试再被拒的**无 UI 死循环**（唯一解法重启） | 25-tool-exec 与 26-guard 两处改 `await` 登记，成功才进前端 Set；失败降级为多弹一次窗 |
| onboarding 测试连接传空 key | **不成立**（轮5 自引入）：queueSaveConfig 有 400ms 防抖，测试时 config 未落盘，后端以入参为准 → 云端预设恒「缺少 API Key」；本地预设走云端分支 | 与 connectTestNow 逐字段对齐（key/local/超时三参） |
| 64-software-panel 测试调用共用 softwareReqSeq | **不成立**（轮5 自引入）：探测完成即使在途测试（已真实执行、有副作用）的返回被判陈旧静默丢弃 → 无输出渲染、用户重复点击即重复执行 | 测试流独立 `swTestSeq` |
| 65-hybrid NaN 校验整表 hybridRefresh 回弹 | **不成立**（轮5 自引入）：异步刷新重渲染所有输入框，把用户正在其他字段输入的内容清掉 | 字段级 `hyRevertField`（仅复位犯规字段） |
| 63-search-panel CAPTCHA_REQUIRED 保持按钮禁用 | **不成立**（轮5 自引入）：后端复检后已回 prompting 态允许再次 continue，前端却禁用+toast「请重试」→ 用户既不能继续也不能放弃、面板因 captcha 态关不掉 → **死局** | 该分支刷新接管区（「继续（重试 n/3）」）并解禁 |
| 其余 ~80 项 | 成立（含 SSRF、task_id 白名单、installer 各修、plan.task_id 落库、记忆面板挂载等） | — |

## 新发现并修复（对抗复审产出）

**后端**
- **checkpoint_rollback 回落 os.getcwd()**：前端只传 taskId 不传 ws_dir → git reset --hard 打到应用自身仓库（源码运行时一次回滚 reset 掉项目仓库）。改回落 manifest 创建时记录的 ws_dir（api.py:1147 同步透传 A4 失败形状，防 err() 拍平后被前端误判假成功）。
- **installer 延迟自删三坑**：Remove-Item 通配符（`C:\app\a[1]` 误删 a1）→ `-LiteralPath`；Wait-Process 无超时（卸载器异常不退出则 ps 无限滞留）→ `-Timeout 30` + 进程仍在则退出不删（避免半删状态）；PowerShell 被企业禁用 → cmd 短路径 rmdir 兜底（GetShortPathNameW 免转义）。
- **卸载定位链 manifest 优先反了**：安装目录被移动后 manifest 的 install_dir 是旧位置 → 删旧位置、真实目录残留、延迟自删挂错目录。改 exe 所在目录为准（含 Harbor.exe 校验），manifest 仅兜底。
- **_dir_arg 三坑**：`/d=` 小写不认（NSIS 惯例，静默装错地方）；`--dir --silent` 把 flag 当值；空值回落。
- **read_install_manifest 非 dict 崩定位链**（install.json 为 `[1,2,3]` 时卸载入口 AttributeError）→ 归一 None。
- **installer_gui XSS**：state.dir/warnings/error 进 innerHTML 未转义（已实证 value 注入 `<img>`）→ esc()；check_dir 桥异常不再放行未校验目录；刷新页面后 finish 页以 result.install_dir 为准（原 state.dir 张冠李戴）；boot 幂等 + 10s 未就绪可操作提示（含静默安装指引）。
- **agentTrusted 跨会话残留**：newSession/switchSession 补清（后端 set_current_sid 亦清，两侧对齐）。
- **deleteSession 双定义**：文件尾 monkey-patch 覆盖模式删除（旧无守卫声明成潜伏死代码），合并单一函数声明 + typeof 守卫。
- **36-connect 识别按钮陈旧文案**：切预设后旧请求返回用旧 dataset.html 还原 → 按当前预设重刷（cmIdentifyBtn 分支）。
- **34-local-model stale 复位按钮**：finally 加 seq 判定（按钮所有权归最新请求）。
- **105-context-menu Esc 半契约**：浮层守卫只兑现「不误 abort」，补「Esc 关菜单」另一半。

**遗留清剿（前几轮标注未修项，本轮全清）**
- file_service read_file 半读即标记「已完整读」→ 仅整文件 served 时 mark_read（4 场景实证）。
- run_admin_command 超时不 unmark：**确认保持现状**——语义不对称正确（admin 超时=输出读取超时，提权进程已启动，unmark 会让 Agent 盲目重试特权命令造成真正二次执行），且 test_security_fixes.py:199 已钉死该行为。
- 66-guard-grant 定时器空转：ggActive=false 停校准+倒计时（用户在 2289a9e 已落地，本轮验证路径正确）。
- 18-toast 溢出淘汰误删 pinned：队首向后找第一个非 pinned；全 pinned 允许临时超 5 条。
- 硬编码毫秒令牌化残余：85-session-mgmt 800/600、18-toast 30、72-shortcuts 60、60-agent-loop 350 续跑窗口（comp()*2）全部收口。
- fx-off 应用时机：initFx 提到 loadAll 首个 await 之前。
- 110-boot 5s 回退假告警：回退分支置中性「等待后端就绪」；pywebviewready 晚到时 bridgeLateReady 补偿执行桥依赖三件套（提取 bridgeDependentInit 共用）。
- MCP read_resource 无档位：KNOWN_ISSUES §24 文档化设计决策（面板显式触发+全程审计，未来开放给 Agent 需补 resolve_tier）。
- round4 三个前端疑似项全部闭环：36-connect 按钮文案（修）、34-local-model stale 复位（修）、29-mcp mcpResBusyUri（§21 文档化接受——按钮级禁用已覆盖真实路径）。

## 验收

- `pytest tests/ -q`：**1133 passed, 1 skipped, 0 failed**（新增 test_round6_adversarial.py 27 例 + test_round7_adversarial.py 20 例，全部为修复的固化回归）
- `check_contract.py`：PASS
- `node frontend/build.js`：55 模块 → 15624 行
- 一次全量运行中 test_v13_mcp 的 MemoryTransport close 用例时序抖动失败（隔离 5/5 通过、该文件自 v1.5.0 未动）——判定为既有 flake，非本轮回归，记入 KNOWN_ISSUES 待办
- KNOWN_ISSUES §八/§九/§十 记录全部设计决策与接受项

## 提交

- 本轮修复 + main.py（第五轮提交漏掉的根目录文件，fio 清理接线在内）+ 两个新测试文件，一个提交推送
- 未并入：deliverables/dev-plan/macos-browser-plan（并行规划会话在途编辑）、master-plan-v19（并行会话交付物，保持未跟踪）
