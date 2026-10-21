/* ================= 启动 ================= */
window.onload = function () {
  let called = false;
  const go = () => { if (!called) { called = true; loadAll(); } };
  if (window.pywebview && window.pywebview.api) go();
  else {
    window.addEventListener('pywebviewready', go);
    setTimeout(() => { if (!called) { called = true; loadAll(); } }, 5000);
  }
};
async function loadAll() {
  try { window.__memCache = await callApi('get_memory', []); } catch (e) { window.__memCache = '[]'; }
  setupContextMenu();
  document.querySelectorAll('select').forEach(initCustomSelect);
  initFx();   // v3：特效总开关（.fx-off + localStorage['glm_fx'] 持久化）
  applyTheme((function () { try { return localStorage.getItem('glm_theme') || 'light'; } catch (e) { return 'light'; } })());
  const tempEl = document.getElementById('temperature');
  const topPEl = document.getElementById('topP');
  const updateLabels = () => {
    document.getElementById('tempVal').textContent = parseFloat(tempEl.value).toFixed(1);
    document.getElementById('topPVal').textContent = parseFloat(topPEl.value).toFixed(2);
  };
  tempEl.addEventListener('input', () => { updateLabels(); queueSaveConfig(); });
  topPEl.addEventListener('input', () => { updateLabels(); queueSaveConfig(); });
  document.getElementById('modelSelect').addEventListener('change', () => {
    if (typeof connectOnModelChange === 'function') connectOnModelChange();   // v4：下拉 ⇄ 手动态同步
    queueSaveConfig();
    updateBrandModel();   // v1.2 R6 / v4：品牌位显示当前生效模型
  });
  ['toolMode','maxTokens','reasoningEffort','searchEngine'].forEach(id =>
    document.getElementById(id).addEventListener('change', queueSaveConfig));
  document.getElementById('toolMode').addEventListener('change', () => {
    const v = document.getElementById('toolMode').value;
    addSysTip('工具权限 → ' + (v === 'full' ? '完整' : v === 'readonly' ? '只读' : '纯聊天') + '，下一回合生效');
  });
  document.getElementById('systemPrompt').addEventListener('input', queueSaveConfig);
  document.getElementById('apiKey').addEventListener('input', queueSaveConfig);
  /* v1.2：更新源字段改动即保存 */
  ['updateManifestUrl'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', () => { queueSaveConfig(); });
  });
  /* v4「连接与模型」合并块：预设切换 / 单一 URL·Key·模型流 / 识别与测试按钮 */
  try { connectInit(); } catch (e) { console.warn('连接与模型初始化失败', e); }
  /* v1.8.0 B 域：搜索面板挂载（纯新增 #searchPanel；功能分级开关默认开，
   * 关闭时 searchPanelInit 内部短路——try/catch 防单模块异常拖垮启动） */
  try { searchPanelInit(); } catch (e) { console.warn('搜索面板初始化失败', e); }
  /* v1.8.0：任务历史与回滚管理（设置区块动态注入；plan_list UI 入口） */
  try { checkpointMgrInit(); } catch (e) { console.warn('任务历史面板初始化失败', e); }
  /* v1.8.0：快捷键与命令帮助（? 键 + header 帮助钮） */
  try { shortcutsInit(); } catch (e) { console.warn('快捷键帮助初始化失败', e); }
  /* v1.8.0：长对话导航（输入区把手 → 最近消息浮层） */
  try { chatNavInit(); } catch (e) { console.warn('长对话导航初始化失败', e); }
  /* v1.8.0 S 域·外部软件 + H 域·混合路由 + v1.8.5 A 域·任务授权/白名单
   * （纯新增 #softwareBlock / #hybridBlock / #grantIndicator / #grantRulesBlock；
   * 各自 Init 内部幂等 + typeof 守卫，失败不阻塞启动） */
  try { softwarePanelInit(); } catch (e) { console.warn('外部软件面板初始化失败', e); }
  /* v1.8.0 W10：记忆面板挂载（softwarePanelInit 之后；内部幂等 + typeof 守卫） */
  try { memoryPanelInit(); } catch (e) { console.warn('记忆面板初始化失败', e); }
  try { hybridInit(); } catch (e) { console.warn('混合路由初始化失败', e); }
  try { guardGrantInit(); } catch (e) { console.warn('任务授权面板初始化失败', e); }
  document.getElementById('enableSearch').addEventListener('change', function () {
    document.getElementById('searchEngineWrap').style.display = this.checked ? 'flex' : 'none';
    queueSaveConfig();
  });
  updateLabels();
  window.addEventListener('dragover', e => { e.preventDefault(); });
  window.addEventListener('drop', e => {
    e.preventDefault();
    const files = e.dataTransfer && e.dataTransfer.files;
    if (!files || !files.length) return;
    for (const f of files) {
      const lower = f.name.toLowerCase();
      if (/\.(png|jpe?g|gif|webp|bmp)$/i.test(lower)) handleFiles([f], 'image');
      else if (/\.(mp4|mov|avi|mkv|webm)$/i.test(lower)) handleFiles([f], 'video');
      else if (/\.(zip)$/i.test(lower)) handleFiles([f], 'zip');
      else handleFiles([f], 'text');
    }
    document.getElementById('userInput').focus();
  });
  const ta = document.getElementById('userInput');
  ta.addEventListener('focus', updateCostEstimate);   // v1.2 R5：输入框聚焦时刷新预估花费
  ta.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 160) + 'px';
    updateCostEstimate();
  });
  ta.addEventListener('keydown', function (e) {
    if (e.isComposing || e.keyCode === 229) return;
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  ta.addEventListener('paste', function (e) {
    const items = e.clipboardData && e.clipboardData.items;
    if (!items) return;
    for (const item of items) {
      if (item.kind === 'file') {
        const file = item.getAsFile();
        if (file) {
          const dt = new DataTransfer();
          dt.items.add(file);
          if (file.type.startsWith('image/')) handleFiles(dt.files, 'image');
          else if (file.type.startsWith('video/')) handleFiles(dt.files, 'video');
          else if (file.name.endsWith('.zip')) handleFiles(dt.files, 'zip');
          else if (/\.(rar|7z)$/i.test(file.name))
            toast('仅支持 zip 压包；rar/7z 请先转成 zip，或解压后用「添加文本文件」选取。', 'warn');
          else handleFiles(dt.files, 'text');
        }
      }
    }
  });
  ['imgInput:image','vidInput:video','fileInput:text','zipInput:zip'].forEach(pair => {
    const [id, tp] = pair.split(':');
    document.getElementById(id).addEventListener('change', async e => {
      await handleFiles(e.target.files, tp); e.target.value = '';
    });
  });
  await loadSessions();
  let cfg = {};
  try {
    if (window.pywebview && window.pywebview.api) {
      const raw = await Promise.race([
        callApi('get_config', []),
        new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 3000))
      ]);
      cfg = JSON.parse(raw || '{}');
    }
  } catch (e) {}
  if (!cfg || Object.keys(cfg).length === 0) {
    try { cfg = JSON.parse(localStorage.getItem('glm_config') || '{}'); } catch (e) {}
  }
  if (cfg.api_key) document.getElementById('apiKey').value = cfg.api_key;
  else document.getElementById('settingsPanel').classList.add('show');
  if (cfg.temperature != null) document.getElementById('temperature').value = cfg.temperature;
  if (cfg.top_p != null) document.getElementById('topP').value = cfg.top_p;
  if (cfg.model) document.getElementById('modelSelect').value = cfg.model;
  const bm0 = document.getElementById('brandModel');
  if (bm0) bm0.textContent = document.getElementById('modelSelect').value;
  const ht0 = document.getElementById('headerTitle');
  if (ht0) ht0.textContent = document.getElementById('modelSelect').value;
  if (cfg.tool_mode) document.getElementById('toolMode').value = cfg.tool_mode;
  if (cfg.max_tokens != null) document.getElementById('maxTokens').value = cfg.max_tokens;
  if (cfg.reasoning_effort) document.getElementById('reasoningEffort').value = cfg.reasoning_effort;
  if (cfg.system_prompt != null) document.getElementById('systemPrompt').value = cfg.system_prompt;
  if (cfg.enable_search) document.getElementById('enableSearch').checked = true;
  if (cfg.search_engine) document.getElementById('searchEngine').value = cfg.search_engine;
  if (cfg.shot_quality) document.getElementById('shotQuality').value = cfg.shot_quality;
  if (cfg.saver_level) document.getElementById('saverLevel').value = cfg.saver_level;
  if (cfg.session_budget != null) document.getElementById('sessionBudget').value = cfg.session_budget;
  /* v1.2：回填更新源 + 安全护栏配置 */
  if (cfg.update_manifest_url) document.getElementById('updateManifestUrl').value = cfg.update_manifest_url;
  /* v4「连接与模型」单块：预设 + 单一 URL/Key/模型流回填（含旧配置一次性 seed 迁移，幂等） */
  try { connectLoadFromConfig(cfg); } catch (e) { console.warn('连接与模型回填失败', e); }
  try { loadLocalUI(cfg); } catch (e) {}   // v1.5 本地专属项（ctx 覆盖 / 工具调用；local_* 键回填）
  // 实现 v1.6 HF-P0：本地 CORS 代理基址——后端补齐 ACAO 头，EdgeWebView 才读得到
  // 不输出 CORS 头的本地服务器（FreeToken/裸 llama.cpp/vLLM）响应；取不到静默
  // （resolveApiEndpoint 回落直连，行为不劣化）。须在 loadLocalUI 后（localState 就绪）
  try {
    const pr = JSON.parse(await callApi('get_local_proxy', []) || '{}');
    if (pr && pr.ok && pr.base_url) window.__localProxyBase = pr.base_url;
  } catch (e) {}
  try { await loadGuardConfig(); } catch (e) {}
  // 实现 v1.6 T6：沙箱设置面板 + 状态灯（加载配置/状态；失败不阻塞启动）
  try { await loadSandboxPanel(); } catch (e) {}
  // 实现 v1.6 T11/T13：左侧主导航引导 + 空态引导 + 头部状态区 + 通知中心 + DND 回填
  try { loadDndSetting(); } catch (e) {}
  /* v1.8.0 W10：首次使用引导向导（无 Key+无会话时展示；localStorage 记住）
   * 修复：原在启动最前执行——彼时 sessions 未加载、Key 未回填，obShouldShow
   * 恒判「无会话+无 Key」误弹引导。移到 loadSessions 与 connectLoadFromConfig 之后。 */
  try { onboardingInit(); } catch (e) { console.warn('引导向导初始化失败', e); }
  try { navInit(); } catch (e) {}
  document.getElementById('searchEngineWrap').style.display = cfg.enable_search ? 'flex' : 'none';
  updateLabels();
  CS.syncAll();
  try {
    if (window.pywebview && window.pywebview.api) {
      let info = null;
      for (let attempt = 0; attempt < 3 && !info; attempt++) {
        try { info = JSON.parse(await callApi('get_api_info', [])); }
        catch (e) { if (attempt < 2) await new Promise(r => setTimeout(r, 800)); }
      }
      if (info) {
        const need = ['pick_folder','get_cwd','write_file','run_command','take_screenshot','open_app',
                      'get_memory','append_memory','get_worklog','append_worklog','save_workspace_file',
                      'build_tools','build_system_prompt','read_more','get_ws_state','cache_tool_output',
                      'get_clipboard','set_clipboard','list_processes','kill_process','open_url'];
        const missing = need.filter(m => !((info.methods || []).includes(m)));
        backendWarning = missing.length > 0
          ? '△ 后端缺少方法: ' + missing.join(', ') + '（exe 为旧版，请重新打包）'
          : null;
      } else {
        backendWarning = '△ 后端 get_api_info 调不通，请重新打包';
      }
    }
  } catch (e) {}
  updateTokenStat();
  refreshWsCard();
  renderSessionList();
  renderAnalytics();   // v3：分析面板首次聚合（数据来自运行时 sessions，空态友好显示）
  checkForUpdate(false);   // v1.2 R1：启动后台静默检查更新（有新版本时右上角 pill 轻提示）
  if (sessions.length > 0) {
    const latest = [...sessions].sort((a, b) => b.updatedAt - a.updatedAt)[0];
    switchSession(latest.id, true);   // v4：boot 首载静默重建（不走 swapping 淡出，避免开屏闪空容器）
  }
}
