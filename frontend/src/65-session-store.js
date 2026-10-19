/* ================= 会话存储 ================= */
/**
 * 修复 S26：会话列表统一归一化校验。
 * 原实现直接 `JSON.parse(raw)` 赋给 sessions：`{}` 能通过 parse 但后续 `sessions.find` /
 * `s.messages.forEach` 级联 TypeError；坏条目（非对象/缺 messages）也无任何防护。
 */
function normalizeSessions(raw) {
  let arr = null;
  try {
    const p = (typeof raw === 'string') ? JSON.parse(raw || '[]') : raw;
    if (Array.isArray(p)) arr = p;
  } catch (e) { arr = null; }
  if (!arr) return [];
  const now = Date.now();
  return arr.filter(x => x && typeof x === 'object').map(x => {
    const s = {
      id: (x.id != null && String(x.id)) || ('s_recover_' + now + '_' + Math.random().toString(36).slice(2, 7)),
      title: (x.title != null) ? String(x.title) : '',
      createdAt: Number(x.createdAt) || now,
      updatedAt: Number(x.updatedAt) || now,
      messages: Array.isArray(x.messages) ? x.messages : []   // 修复 S26：75-token-stat 等消费方级联 TypeError 的源头
    };
    // 保留已知附加字段（压缩态/已读键/预算标记等）
    if (x.apiFrozen && typeof x.apiFrozen === 'object') s.apiFrozen = x.apiFrozen;
    if (Array.isArray(x._readKeys)) s._readKeys = x._readKeys;
    if (typeof x.worklogInjected === 'boolean') s.worklogInjected = x.worklogInjected;
    if (typeof x.autoResume === 'number') s.autoResume = x.autoResume;
    if (typeof x.__budgetWarned === 'boolean') s.__budgetWarned = x.__budgetWarned;
    // 修复 S8（二轮）遗漏 + UX-1（v1.4）：单调花费计数器与压缩备份必须跨重启保留——
    // 原 normalizeSessions 白名单会静默丢弃这两个顶层键（计数器丢→预算硬停被压缩
    // 洗白的防护重启即失效；备份丢→「恢复原文」跨重启失效）
    if (typeof x._spentCost === 'number') s._spentCost = x._spentCost;
    if (typeof x._spentTokens === 'number') s._spentTokens = x._spentTokens;
    if (x._compactBackup && typeof x._compactBackup === 'object' && Array.isArray(x._compactBackup.msgs)) {
      s._compactBackup = x._compactBackup;
    }
    return s;
  });
}
async function loadSessions() {
  // 修复 W30：双源按 updatedAt 合并——原「后端优先、失败回退本地」在后端写失败时会静默丢新会话
  let backend = [];
  let local = [];
  let backendOk = false;   // 实现 v1.6 W27：后端读取成败标志——墓碑清理只在读成功后进行
  try {
    if (window.pywebview && window.pywebview.api) {
      backend = normalizeSessions(await callApi('get_sessions', []));
      backendOk = true;
    }
  } catch (e) {}
  try { local = normalizeSessions(localStorage.getItem('glm_sessions')); } catch (e) {}
  // 修复 W24（二轮）：删除墓碑——后端写失败时下次启动合并会把已删会话复活；
  // 墓碑记录在 localStorage（本地删除即生效，不依赖后端成功），合并时过滤；
  // 后端列表已不含的 id 出棺（防墓碑无限膨胀）
  // 修复 W27（v1.6）：原无脑按 backendIds 过滤墓碑——后端读取失败（异常/无
  // pywebview）时 backendIds 恒空 → 墓碑被清空 → 已删对话在下次成功读取时
  // 复活。仅在 backendOk 时执行出棺。
  let tomb = [];
  try { tomb = JSON.parse(localStorage.getItem('glm_deleted_ids') || '[]'); } catch (e) { tomb = []; }
  const tombSet = new Set(tomb.filter(x => x && typeof x === 'string'));
  if (backendOk) {
    const backendIds = new Set(backend.map(s => s.id));
    const keptTomb = tomb.filter(id => backendIds.has(id));
    try { localStorage.setItem('glm_deleted_ids', JSON.stringify(keptTomb)); } catch (e) {}
  }
  const byId = new Map();
  const put = (list) => list.forEach(s => {
    if (tombSet.has(s.id)) return;   // 修复 W24：墓碑中的 id 不参与合并
    const prev = byId.get(s.id);
    if (!prev || (s.updatedAt || 0) > (prev.updatedAt || 0)) byId.set(s.id, s);
  });
  put(local); put(backend);   // 同 id 时取 updatedAt 较新的一侧
  sessions = [...byId.values()].sort((a, b) => b.updatedAt - a.updatedAt).slice(0, 60);
}
// 修复 建议㉜（三轮）：saveSessions 串行化——原并发调用可让旧快照后落盘覆盖新快照
let _saveChain = Promise.resolve();
// 修复 ㉚（三轮）：全量序列化节流——流式/连续保存（每消息、每工具调用）原每次都对
// 全量 sessions 做 JSON 双序列化 + 双端写（localStorage + 后端）。现 300ms 合并窗口：
// 首次立即执行，窗口内后续调用合并为一次 trailing 落盘；await 语义不变（返回的
// promise 仍在其实际写入完成后 resolve），末态必达，丢的只是中间快照。
const SAVE_THROTTLE_MS = 300;
let _saveLastRun = 0;
let _saveTrailer = null;
function _enqueueSave(run) {
  _saveChain = _saveChain.then(run).catch(() => {});
  return _saveChain;
}
async function saveSessions() {
  const run = async () => {
  if (sessions.length > 60) {
    sessions.sort((a, b) => b.updatedAt - a.updatedAt);
    sessions = sessions.slice(0, 60);
  }
  const slim = JSON.parse(JSON.stringify(sessions, (k, v) => {
    if (v && typeof v === 'object') {
      if (v.type === 'image_url') return { type: 'text', text: '[图片]' };
      if (v.type === 'video_url') return { type: 'text', text: '[视频]' };
    }
    if (typeof v === 'string' && v.length > 30000) return v.slice(0, 30000) + '…(存储截断)';
    return v;
  }));
  const data = JSON.stringify(slim);
  try { localStorage.setItem('glm_sessions', data); }
  catch (e) { toast('本地会话缓存写入失败（浏览器存储可能已满）: ' + e.message, 'warn'); }   // 修复 建议㊶（二轮）：原完全静默
  try {
    if (window.pywebview && window.pywebview.api) await callApi('save_sessions', [data]);
  } catch (e) { toast('会话历史保存失败：' + e.message, 'warn'); }   // v1.2 R3：静默吞错 → 可见
  };
  const now = Date.now();
  if (now - _saveLastRun >= SAVE_THROTTLE_MS) {
    _saveLastRun = now;
    return _enqueueSave(run);
  }
  // 窗口内：合并为一次 trailing 执行（run 在执行时才读全局 sessions，落的是最新末态）
  if (!_saveTrailer) {
    _saveTrailer = new Promise((resolve) => {
      setTimeout(() => {
        _saveTrailer = null;
        _saveLastRun = Date.now();
        resolve(_enqueueSave(run));
      }, SAVE_THROTTLE_MS - (now - _saveLastRun));
    });
  }
  return _saveTrailer;
}
function getCurrentSession() { return sessions.find(s => s.id === currentSessionId); }

function rememberDeletedSession(id) {
  // 修复 W24（二轮）：删除写入墓碑——saveSessions 后端写失败时，下次启动的双源合并
  // 不再把该 id 从后端旧列表里复活
  try {
    let tomb = [];
    try { tomb = JSON.parse(localStorage.getItem('glm_deleted_ids') || '[]'); } catch (e) {}
    if (!tomb.includes(id)) { tomb.push(id); localStorage.setItem('glm_deleted_ids', JSON.stringify(tomb)); }
  } catch (e) {}
}
