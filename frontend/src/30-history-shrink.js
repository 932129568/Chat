/* ================= A2 历史瘦身（发送副本瘦身，原始历史保留） ================= */
/* 修复 TOK-3（v1.4）：收紧一档——keepTail 8→6 / toolMax 600→450 / aiMax 1200→900。
 * 收紧与 UX-1 透明化（弱化标记 + 可恢复备份）同批上线，标记可见对冲「AI 忘了」反噬。
 * read_file/read_more 豁免规则一字不动（原文保留机制不变）。 */
const SHRINK = { keepTail: 6, toolMax: 450, aiMax: 900 };
const SHRINK_LEN = { toolHead: 300, toolTail: 120, aiHead: 500, aiTail: 150 };

/** 工具结果瘦身副本（shrinkHistoryForApi 与 UX-1 标记共用同一口径，防两处漂移） */
function shrinkToolCopy(c) {
  return c.slice(0, SHRINK_LEN.toolHead) +
    '\n…[旧工具结果已瘦身省 token,原' + c.length + '字;需精确原文请重新调用对应工具(read_file 传 force=true)]…\n' +
    c.slice(-SHRINK_LEN.toolTail);
}
/** AI 回复瘦身副本（同上） */
function shrinkAiCopy(c) {
  return c.slice(0, SHRINK_LEN.aiHead) + '\n…[旧回复已瘦身,原' + c.length + '字]…\n' +
    c.slice(-SHRINK_LEN.aiTail);
}
function shrinkHistoryForApi(msgs) {
  if (!Array.isArray(msgs) || msgs.length <= SHRINK.keepTail) return msgs;
  const cut = msgs.length - SHRINK.keepTail;
  const out = msgs.slice();
  for (let i = 0; i < cut; i++) {
    const m = out[i];
    if (!m) continue;
    if (m.role === 'tool' && typeof m.content === 'string' && m.content.length > SHRINK.toolMax && m.__tool !== 'read_file' && m.__tool !== 'read_more') {
      out[i] = Object.assign({}, m, { content: shrinkToolCopy(m.content) });
    } else if (m.role === 'assistant' && typeof m.content === 'string' && m.content.length > SHRINK.aiMax) {
      out[i] = Object.assign({}, m, { content: shrinkAiCopy(m.content) });
    }
  }
  return out;
}

/**
 * 修复 UX-1（v1.4）：发送副本瘦身透明化——与 shrinkHistoryForApi 同口径计算哪些消息
 * 在发送副本里会被瘦身，在对应消息元素（data-midx）上打弱化标记，
 * hover 显示摘要开头。AI 实际收到的与 UI 展示的差异从此可见（「AI 忘了」困惑的对冲）。
 */
function applyShrinkMarkers(msgs) {
  const box = document.getElementById('chatContainer');
  if (!box) return;
  const clear = () => box.querySelectorAll('[data-shrunk]').forEach(el => {
    el.removeAttribute('data-shrunk');
    const b = el.querySelector('.shrink-badge');
    if (b) b.remove();
  });
  clear();
  if (!Array.isArray(msgs) || msgs.length <= SHRINK.keepTail) return;
  const cut = msgs.length - SHRINK.keepTail;
  for (let i = 0; i < cut; i++) {
    const m = msgs[i];
    if (!m) continue;
    let shrunkLen = 0, head = '';
    if (m.role === 'tool' && typeof m.content === 'string' && m.content.length > SHRINK.toolMax && m.__tool !== 'read_file' && m.__tool !== 'read_more') {
      shrunkLen = shrinkToolCopy(m.content).length; head = m.content.slice(0, 60);
    } else if (m.role === 'assistant' && typeof m.content === 'string' && m.content.length > SHRINK.aiMax) {
      shrunkLen = shrinkAiCopy(m.content).length; head = m.content.slice(0, 60);
    }
    if (!shrunkLen) continue;
    const el = box.querySelector('[data-midx="' + i + '"]');
    if (!el || el.hasAttribute('data-shrunk')) continue;
    el.setAttribute('data-shrunk', '1');
    const badge = document.createElement('div');
    badge.className = 'shrink-badge';
    badge.textContent = '已瘦身 · 原文 ' + m.content.length + ' 字 → 发送约 ' + shrunkLen + ' 字';
    badge.title = '发送给 AI 的副本已瘦身；摘要开头：' + head + '…';
    el.appendChild(badge);
  }
}
