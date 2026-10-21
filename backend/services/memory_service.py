# -*- coding: utf-8 -*-
"""memory_service：结构化记忆（v1.8.0 W11 + 交接文档「记忆结构化三类」）。

四件套（deep-research W11 规格）：
1. **结构化三类**：fact（事实）/ preference（偏好）/ rule（规则）——旧数据
   （无 kind 字段）读时懒迁移为 fact；写入时经 classify() 自动分类。
2. **规则提取**：「以后都/每次/永远/禁止/必须」句式 → rule；「我喜欢/偏好」
   → preference；其余 fact。句式优先于关键词（规则是用户显式约束）。
3. **关键词检索**：中文无分词依赖——字级 bigram 重叠打分（query × item
   2-gram Jaccard 式）+ rule 权重加成 + 时间衰减；纯函数可测。
4. **系统提示注入**：build_system_prompt 尾部注入「相关记忆」段（≤5 条，
   ≤800 字）——在 INTENTIONAL_DELTAS 白名单内（契约测试单独断言结构）。

存储：~/.glm-chat/memory.json（config_service 的 MEMORY_PATH，与 config.json
隔离铁律）。条目 {text, ts, kind, key?}；上限 200 条（超出淘汰最旧 fact，
rule/preference 不淘汰——用户显式约束优先保留）。
"""
import datetime
import json
import os
import re

KINDS = ('fact', 'preference', 'rule')

# 规则句式（用户显式约束——最高优先级分类）
_RULE_PATTERNS = (
    r'以后都', r'以后一律', r'每次都要', r'永远不要', r'任何时候都',
    r'禁止', r'必须', r'不允许', r'务必',
)
# 偏好句式
_PREF_PATTERNS = (
    r'我喜欢', r'我不喜欢', r'偏好', r'习惯用', r'倾向于', r'prefer',
)
# 中文停用字（bigram 打分时降权——防「的/了/是」虚高）
_STOP_CHARS = set('的了是我你他她它在有和就不都也很与及或对着被把让从往按依')
_MAX_ITEMS = 200
_INJECT_LIMIT = 5
_INJECT_MAX_CHARS = 800


def classify(text):
    """文本 → kind（rule > preference > fact 优先级）。"""
    t = str(text or '')
    for p in _RULE_PATTERNS:
        if p in t:
            return 'rule'
    for p in _PREF_PATTERNS:
        if p in t:
            return 'preference'
    return 'fact'


def _bigrams(s):
    """字级 bigram 集合（中文无分词；ASCII 词也按字符滑窗，短词降敏）。"""
    s = re.sub(r'\s+', '', str(s or '').lower())
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _tokens(s):
    """去停用字的 bigram（打分口径）。"""
    bg = _bigrams(s)
    return {g for g in bg if not (len(g) == 2 and g[0] in _STOP_CHARS and g[1] in _STOP_CHARS)}


def retrieve(query, items, limit=5):
    """关键词检索（纯函数）：bigram 重叠 + kind 加成 + 时间衰减。

    Args:
        query: 检索词（当前用户消息/任务上下文）。
        items: memory 条目数组（{text, ts, kind}）。
        limit: 返回条数。

    Returns:
        按相关度降序的条目列表（原对象引用，不拷贝）。
    """
    qt = _tokens(query)
    if not qt or not items:
        return []
    now = datetime.datetime.now()
    scored = []
    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        it_tokens = _tokens(it.get('text') or '')
        if not it_tokens:
            continue
        overlap = len(qt & it_tokens)
        if overlap == 0:
            continue
        # Jaccard 式归一（query 侧为主——query 短时不被长 item 稀释）
        score = overlap / max(1, len(qt))
        # kind 加成：rule 是显式约束，检索时优先（×1.3）
        if it.get('kind') == 'rule':
            score *= 1.3
        elif it.get('kind') == 'preference':
            score *= 1.1
        # 时间衰减：30 天半衰（新的记忆更可能仍有效）
        try:
            ts = it.get('_ts_dt') or _parse_ts(it.get('ts'))
            if ts:
                age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
                score *= 0.5 ** (age_days / 30.0)
        except Exception:
            pass
        scored.append((score, -idx, it))     # -idx：同分新的（数组尾部）优先
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [it for _, _, it in scored[:int(limit)]]


def _parse_ts(ts):
    """memory.json 的 'MM-DD HH:MM' 形态 → datetime（跨年按当前年推断）。"""
    try:
        m = re.match(r'(\d{2})-(\d{2}) (\d{2}):(\d{2})', str(ts or ''))
        if not m:
            return None
        now = datetime.datetime.now()
        return datetime.datetime(now.year, int(m.group(1)), int(m.group(2)),
                                 int(m.group(3)), int(m.group(4)))
    except Exception:
        return None


def inject_block(items, limit=_INJECT_LIMIT, max_chars=_INJECT_MAX_CHARS):
    """系统提示词注入段（相关记忆；空记忆 → '' 不加段）。

    格式：
        【长期记忆】用户此前的显式约束与偏好（相关条目，供参考，勿与用户
        当前指令冲突时以当前指令为准）：
        - [规则] 以后都先写测试再写实现
        - [偏好] 我喜欢简洁的回复
    """
    if not items:
        return ''
    lines = ['【长期记忆】用户此前的显式约束与偏好（相关条目；如与用户当前指令'
             '冲突，以当前指令为准）：']
    total = len(lines[0])
    used = 0
    for it in items[:int(limit)]:
        if not isinstance(it, dict):
            continue
        text = str(it.get('text') or '').strip()
        if not text:
            continue
        if len(text) > 200:
            text = text[:200] + '…'
        kind = it.get('kind') if it.get('kind') in KINDS else 'fact'
        _label = {'rule': '规则', 'preference': '偏好', 'fact': '事实'}
        line = '- [%s] %s' % (_label.get(kind, kind), text)
        if total + len(line) + 1 > max_chars:
            break
        lines.append(line)
        total += len(line) + 1
        used += 1
    if not used:
        return ''
    return '\n'.join(lines)


def normalize_item(entry):
    """入参归一：旧/脏条目 → {text, ts, kind}（kind 缺省自动分类）。"""
    e = dict(entry) if isinstance(entry, dict) else {'text': str(entry or '')}
    text = str(e.get('text') or '').strip()
    e['text'] = text
    if not e.get('ts'):
        e['ts'] = datetime.datetime.now().strftime('%m-%d %H:%M')
    kind = e.get('kind')
    if kind not in KINDS:
        e['kind'] = classify(text)      # 旧数据懒迁移 + 新写入自动分类
    return e


def dedupe_key(entry):
    """去重键：rule/preference 按规范化文本（同规则不重复存）；fact 不去重
    （同一事实的更新版本自然按时间衰减让位）。"""
    e = entry if isinstance(entry, dict) else {}
    if e.get('kind') in ('rule', 'preference'):
        return re.sub(r'\s+', '', str(e.get('text') or '')).lower()
    return None


class MemoryService:
    """结构化记忆服务（memory.json 独立文件；config.json 零污染）。

    append/list/delete 保持既有 js_api 语义（config_service 的同名方法
    转调此处）；新增 retrieve/inject_block 能力面。
    """

    def __init__(self, path, logger=None):
        self._path = path
        self._log = logger

    # ---- 读写 ----
    def _load(self):
        try:
            if os.path.exists(self._path):
                with open(self._path, encoding='utf-8') as f:
                    arr = json.load(f)
                if isinstance(arr, list):
                    return arr
        except Exception as e:
            if self._log:
                self._log.warning('memory.json 读取失败: %r', e)
        return []

    def _save(self, items):
        from .config_service import atomic_write_json
        atomic_write_json(self._path, items[-_MAX_ITEMS:])

    def append(self, entry):
        """追加（自动分类 + rule/preference 去重 + 上限淘汰）。

        淘汰策略：超出上限时淘汰最旧 fact；rule/preference 不动（用户显式
        约束优先保留）——全是指令类时允许超限（极端场景保指令不保事实）。
        """
        e = normalize_item(entry)
        # 注：空 text 不拒绝（与 legacy append_memory 行为对齐——契约测试钉住
        # {'k':'v'} 这类无 text 条目也入库；分类对空串回落 fact）
        items = self._load()
        key = dedupe_key(e)
        if key:
            items = [x for x in items
                     if not (isinstance(x, dict)
                             and dedupe_key(x) == key)]
        items.append(e)
        if len(items) > _MAX_ITEMS:
            head = [x for x in items[:-1]
                    if not (isinstance(x, dict) and x.get('kind') in ('rule', 'preference'))]
            if head:
                oldest = min(range(len(head)),
                             key=lambda i: str((head[i] or {}).get('ts') or ''))
                drop = head[oldest]
                items = [x for x in items if x is not drop]
        self._save(items)
        return {'ok': True, 'kind': e['kind'], 'total': len(items)}

    def list(self):
        """全部条目（读取时懒迁移 kind——旧数据无 kind 自动分类，不落盘）。"""
        out = []
        for x in self._load():
            if isinstance(x, dict):
                y = normalize_item(x)
                y.setdefault('ts', x.get('ts') or y['ts'])
                out.append(y)
        return out

    def delete(self, index):
        """删第 index 条（边界校验同 delete_memory 口径）。"""
        items = self._load()
        if not isinstance(index, int) or isinstance(index, bool) \
                or index < 0 or index >= len(items):
            return {'error': '下标越界：%r（共 %d 条）' % (index, len(items))}
        removed = items.pop(index)
        self._save(items)
        return {'ok': True, 'removed': removed, 'remaining': len(items)}

    # ---- 检索 / 注入 ----
    def retrieve(self, query, limit=5):
        return retrieve(query, self.list(), limit)

    def inject_for(self, query, limit=_INJECT_LIMIT):
        """系统提示词注入段（按 query 相关度取 top N）。"""
        return inject_block(self.retrieve(query, limit), limit=limit)
