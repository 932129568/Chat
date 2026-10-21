# -*- coding: utf-8 -*-
"""生成 api-reference.md（deliverables/）：从 Api 类实扫——get_api_info 契约面
+ _V12_EXTRA 隐身面分组，签名/docstring 首段抽取。零手抄（手抄必漂移）。
用法：python tools/gen_api_reference.py（CI/发布前跑，输出即文档）。
"""
import inspect
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.api import Api, _V12_EXTRA  # noqa: E402

GROUPS = [
    ('契约面 · get_api_info 列名（v1.0.0 起逐字节锁定）', 'legacy'),
    ('隐身面 · _V12_EXTRA（v1.2.5 起新增方法，自省不列、前端可直接调）', 'extra'),
]

_SKIP = {'get_api_info', '_set_window', 'clear_caches'}


def _sig(fn):
    try:
        return str(inspect.signature(fn))
    except (TypeError, ValueError):
        return '(?)'


def _doc(fn):
    d = inspect.getdoc(fn) or ''
    lines = [l.strip() for l in d.splitlines() if l.strip()]
    return lines[0] if lines else ''


def main():
    api = Api()
    contract_methods = set(json.loads(api.get_api_info())['methods'])
    out = []
    out.append('# Harbor js_api 接口参考')
    out.append('')
    out.append('> 本文档由 `tools/gen_api_reference.py` 从 `backend/api.py` 实扫生成'
               '（签名 + docstring 首段），发布前刷新——**勿手抄**（手抄必漂移）。')
    out.append('>')
    out.append('> - **契约面**：`get_api_info` 列出的方法（与 v1.0.0 legacy 逐字节'
               '一致，`tests/test_api_contract.py` 门禁）')
    out.append('> - **隐身面**：`_V12_EXTRA` 登记的新方法（自省不列出，防契约漂移；'
               '前端经 pywebview 桥直接调用）')
    out.append('')
    out.append('**方法总数**：契约面 %d + 隐身面 %d = %d'
               % (len(contract_methods), len(_V12_EXTRA),
                  len(contract_methods) + len(_V12_EXTRA)))
    out.append('')
    for title, kind in GROUPS:
        out.append('## %s' % title)
        out.append('')
        out.append('| 方法 | 签名 | 说明 |')
        out.append('|---|---|---|')
        names = sorted(contract_methods) if kind == 'legacy' else sorted(_V12_EXTRA)
        for n in names:
            if n in _SKIP:
                continue
            fn = getattr(api, n, None)
            if fn is None:
                out.append('| `%s` | — | （legacy 快照方法，本仓无实现体） |' % n)
                continue
            out.append('| `%s` | `%s` | %s |'
                       % (n, _sig(fn).replace('|', '\\|'),
                          _doc(fn).replace('|', '\\|')
                          or '（v1.0.0 legacy 契约方法）'))
        out.append('')
    path = os.path.join(ROOT, 'deliverables', 'api-reference.md')
    with io.open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out) + '\n')
    print('written:', path, '| lines:', len(out))


if __name__ == '__main__':
    main()
