# -*- coding: utf-8 -*-
"""FreeToken Desktop preset 回归（2026-10-20 用户实需求：接入 FreeToken Desktop 本地模型）。

真机取证（主理人探测）：FreeToken daemon 19000（控制面）+ 推理引擎 + API 代理
1919（OpenAI 兼容，免 Key，单模型语义——/v1/models 一次只返回当前启动的引擎）。
"""
import io
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PROJECT_ROOT, 'frontend', 'src')
TPL = os.path.join(PROJECT_ROOT, 'frontend', 'index.template.html')


def _fe(name):
    return io.open(os.path.join(SRC, name), encoding='utf-8').read()


def _tpl():
    return io.open(TPL, encoding='utf-8').read()


class TestFreetokenPreset:
    """preset 结构 + 顺序表 + 本地系归类 + 模板下拉（源码级断言）。"""

    def test_preset_entry(self):
        src = _fe('36-connect.js')
        assert "'freetoken':" in src or 'freetoken: {' in src, 'PRESETS 缺少 freetoken'
        seg = src.split('freetoken: {')[1].split('  },')[0]
        assert "name: 'FreeToken Desktop'" in seg
        assert "base_url: 'http://127.0.0.1:1919/v1'" in seg
        assert 'key_required: false' in seg, '本地代理免 Key'
        assert 'local: true' in seg, '必须走本地模型路径'
        assert 'prices: { in: 0, out: 0, cache: 0 }' in seg, '本地零费'
        assert 'models: []' in seg, '单模型语义：静态表为空靠探测'
        assert 'key_hint' in seg and '探测' in seg, 'key_hint 须说明探测与单模型语义'

    def test_order_and_local_ids(self):
        src = _fe('36-connect.js')
        lines = src.splitlines()
        order = ''
        for i, l in enumerate(lines):
            if l.startswith('const CONNECT_PRESET_ORDER'):
                order = l + (lines[i + 1] if i + 1 < len(lines) else '')
                break
        assert "'freetoken'" in order
        # 归类：本地系（localai）之后、custom 之前
        assert order.index("'localai'") < order.index("'freetoken'") < order.index("'custom'")
        local_ids = ''
        for l in lines:
            if l.startswith('const CONNECT_LOCAL_IDS'):
                local_ids = l
                break
        assert "'freetoken'" in local_ids, '必须进本地系 ID 集合（探测顺序/local 行为）'

    def test_template_option(self):
        tpl = _tpl()
        assert '<option value="freetoken">FreeToken Desktop</option>' in tpl
        # 位置：localai 之后 custom 之前
        assert tpl.index('value="localai"') < tpl.index('value="freetoken"') < tpl.index('value="custom"')

    def test_no_duplicate_option(self):
        tpl = _tpl()
        assert tpl.count('value="freetoken"') == 1


class TestFreetokenBackendCompat:
    """后端零改的依据：_parse_model_list 已覆盖 FreeToken 的 OpenAI 清单形态。"""

    def test_parse_freetoken_shape(self):
        from backend.services.local_model_service import _parse_model_list
        raw = json.dumps({'object': 'list', 'data': [
            {'id': 'Gemma4-26B-A4B-QAT-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf',
             'object': 'model', 'created': 1792461644, 'owned_by': 'FreeToken',
             'root': 'D:\\大模型\\freetoken\\...'}]}).encode()
        out = _parse_model_list(raw)
        assert out == ['Gemma4-26B-A4B-QAT-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf'], out

    def test_parse_plain_id_list(self):
        from backend.services.local_model_service import _parse_model_list
        out = _parse_model_list(json.dumps({'data': ['a.gguf', 'b.gguf']}).encode())
        assert out == ['a.gguf', 'b.gguf']


import json  # noqa: E402
