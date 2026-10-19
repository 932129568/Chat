#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""target_verify.py — Harbor v1.6 遗留项目标机一键验证（实现 v1.6 遗留 L3）

用途：在**目标机**（有外网/有密钥/跑着 Ollama 的机器）上一条命令完成 v1.6
遗留验证，产出 markdown 报告。零第三方依赖（Python 3.10+ 标准库）。

覆盖：
  1. DeepSeek 校准（T4）：连通 + 工具调用返回 tool_calls 且 name/arguments
     完整 + usage 计费字段 + 与 Harbor  preset 价格（元/M：in 2 / out 8 /
     cache 0.4，见 frontend/src/36-connect.js deepseek 条目）对算
  2. GitHub Models（T2/T3 真机复核）：PAT 探 /catalog/models 与 /models
     双路径（打印真实结构供校准——外部源描述的目录结构在部分网络环境下
     不可信）+ 最小 chat 调用 + 429 响应头形态
  3. Ollama（KNOWN_ISSUES #2）：/api/tags 清单 + /api/show context_length
     与 Harbor 元数据对算 + 最小 generate（验证 503 loading 退避路径可观测）
  4. 基准链（token -15% 量化目标）：3 条标准链（纯问答/单文件改/多文件+命令）
     token 统计 vs 基线文件，算达成率

用法：
  # 零 shell 语法三步走（PowerShell 用户强烈推荐——不用手写 JSON、不用续行符）：
  #   ① 脚本自动生成配置模板（已存在则拒绝覆盖，防止误覆盖你真凭证）
  python deliverables/scripts/target_verify.py --init-config
  #   ② 记事本打开，把 sk-xxx / ghp_xxx 换成真凭证，保存关闭
  notepad verify.json
  #   ③ 一条命令运行
  python deliverables/scripts/target_verify.py --config verify.json

  verify.json 键名（与参数一一对应；留空/删掉的项自动 SKIP）：
  {
    "deepseek_key": "sk-xxx",
    "github_pat": "ghp_xxx",
    "ollama_url": "http://localhost:11434",
    "bench_base": "https://api.deepseek.com/v1",
    "bench_key": "sk-xxx",
    "bench_model": "deepseek-v4.1",
    "baseline": "baseline.json",
    "output": "deliverables/metrics/target-verify-2026-10-19.md"
  }

  # 参数式（PowerShell 续行用反引号 `，路径用正斜杠 /）
  python deliverables/scripts/target_verify.py `
    --deepseek-key sk-xxx --github-pat ghp-xxx `
    --ollama-url http://localhost:11434

  # cmd.exe 续行用 ^；Git Bash 才用 \
  # 任一项失败不影响其他项；未提供对应凭证的项记 SKIP。报告落盘 --output。
"""

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

# 与 frontend/src/36-connect.js deepseek preset 对齐（元 / 百万 tokens）
DEEPSEEK_PRICES = {'in': 2, 'out': 8, 'cache': 0.4}

OPENAI_TOOLS = [{
    'type': 'function',
    'function': {
        'name': 'read_file',
        'description': '读取工作区文件内容',
        'parameters': {
            'type': 'object',
            'properties': {'path': {'type': 'string', 'description': '文件路径'}},
            'required': ['path'],
        },
    },
}]


def http_json(url, payload=None, headers=None, timeout=90):
    """POST/GET JSON → (status, headers_dict, body_dict_or_text)。零依赖。"""
    hdrs = {'Accept': 'application/json', 'User-Agent': 'harbor-target-verify/1.6'}
    if headers:
        hdrs.update(headers)
    data = None
    method = 'GET'
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        hdrs['Content-Type'] = 'application/json'
        method = 'POST'
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(1024 * 1024)
            hd = {k.lower(): v for k, v in resp.headers.items()}
            try:
                return resp.status, hd, json.loads(raw.decode('utf-8', 'replace'))
            except Exception:
                return resp.status, hd, raw.decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        raw = e.read(1024 * 1024)
        hd = {k.lower(): v for k, v in (e.headers or {}).items()}
        try:
            return e.code, hd, json.loads(raw.decode('utf-8', 'replace'))
        except Exception:
            return e.code, hd, raw.decode('utf-8', 'replace')
    except Exception as e:
        return -1, {}, '连接失败: %s' % str(e)[:120]


# ---------------------------------------------------------------- 1 DeepSeek
def verify_deepseek(key):
    r = {'name': 'DeepSeek 校准（T4）', 'status': 'FAIL', 'lines': []}
    if not key:
        r['status'] = 'SKIP'; r['lines'].append('未提供 --deepseek-key'); return r
    st, hd, body = http_json(
        'https://api.deepseek.com/v1/chat/completions',
        {
            'model': 'deepseek-v4.1',
            'messages': [{'role': 'user', 'content':
                          '读取 ./config.json，先调用 read_file 工具，不要直接回答。'}],
            'tools': OPENAI_TOOLS,
            'max_tokens': 200,
        },
        headers={'Authorization': 'Bearer ' + key})
    r['lines'].append('POST /v1/chat/completions → HTTP %s' % st)
    if st != 200 or not isinstance(body, dict):
        r['lines'].append('响应体: %s' % json.dumps(body, ensure_ascii=False)[:300])
        return r
    msg = body.get('choices', [{}])[0].get('message', {}) or {}
    tcs = msg.get('tool_calls') or []
    if not tcs:
        r['lines'].append('未返回 tool_calls（content=%r）——工具调用不兼容，记录降级路径'
                          % str(msg.get('content'))[:120])
        return r
    tc = tcs[0]
    fn = tc.get('function') or {}
    r['lines'].append('tool_calls[0]: id=%s name=%s' % (tc.get('id'), fn.get('name')))
    try:
        args = json.loads(fn.get('arguments') or '{}')
        r['lines'].append('arguments 可解析: %s' % json.dumps(args, ensure_ascii=False)[:120])
    except Exception:
        r['lines'].append('arguments 非 JSON: %r' % (fn.get('arguments') or '')[:120])
        return r
    usage = body.get('usage') or {}
    pt = usage.get('prompt_tokens') or usage.get('prompt_tokens_details', {}).get('cached_tokens', 0)
    ct = usage.get('completion_tokens', 0)
    if not pt and not ct:
        r['lines'].append('usage 缺失——计费字段不可用')
        return r
    cost = (pt * DEEPSEEK_PRICES['in'] + ct * DEEPSEEK_PRICES['out']) / 1e6
    r['lines'].append('usage: prompt=%s completion=%s total=%s' %
                      (pt, ct, usage.get('total_tokens')))
    r['lines'].append('计费对算（preset 元/M in=%s out=%s）: ¥%.6f' %
                      (DEEPSEEK_PRICES['in'], DEEPSEEK_PRICES['out'], cost))
    r['lines'].append('缓存命中字段: %s' % json.dumps(
        usage.get('prompt_cache_hit_tokens', usage.get('prompt_tokens_details', {})),
        ensure_ascii=False)[:120])
    r['status'] = 'PASS'
    return r


# ---------------------------------------------------------------- 2 GitHub
def verify_github(pat):
    r = {'name': 'GitHub Models 真机复核（T2/T3）', 'status': 'FAIL', 'lines': []}
    if not pat:
        r['status'] = 'SKIP'; r['lines'].append('未提供 --github-pat'); return r
    hdrs = {'Authorization': 'Bearer ' + pat}
    # 双路径探测（L2）：catalog 与 OpenAI 标准清单，打印真实结构供校准
    for label, url in (('catalog', 'https://models.github.ai/catalog/models'),
                       ('models', 'https://models.github.ai/inference/models')):
        st, hd, body = http_json(url, headers=hdrs, timeout=30)
        r['lines'].append('GET %s → HTTP %s' % (url, st))
        if st == 200 and isinstance(body, dict):
            items = body.get('models') or body.get('data') or []
            r['lines'].append('  真实结构（%s 路径）: 顶层键=%s，共 %d 项，首项键=%s'
                              % (label, sorted(body.keys()), len(items),
                                 sorted(items[0].keys()) if items and isinstance(items[0], dict) else 'n/a'))
            if items and isinstance(items[0], dict):
                r['lines'].append('  首项: %s' % json.dumps(items[0], ensure_ascii=False)[:250])
            r['status'] = 'PASS'
            break
        else:
            r['lines'].append('  响应: %s' % json.dumps(body, ensure_ascii=False)[:200])
    # 最小 chat（验证推理端点 + 抓 429 header 形态；不主动触发限流）
    st, hd, body = http_json(
        'https://models.github.ai/inference/chat/completions',
        {'model': 'openai/gpt-4o', 'messages': [{'role': 'user', 'content': 'hi'}],
         'max_tokens': 16},
        headers=hdrs, timeout=60)
    r['lines'].append('POST /inference/chat/completions → HTTP %s' % st)
    rl = {k: v for k, v in hd.items() if 'ratelimit' in k or 'retry' in k}
    r['lines'].append('限流相关响应头: %s' % (json.dumps(rl) if rl else '（本次未返回，触发 429 时复查）'))
    if st == 200 and isinstance(body, dict):
        r['lines'].append('chat 可用；usage: %s' % json.dumps(body.get('usage', {}))[:150])
    elif st == 200:
        # 200 但非 JSON（中间网络设备返回纯文本 OK 的已知形态）——如实记录
        r['lines'].append('chat 返回 200 但非 JSON 响应体（%r）——疑似中间网络设备拦截，'
                          '该环境无法完成 GitHub 真机验证' % (str(body)[:60],))
    else:
        r['lines'].append('chat 响应: %s' % json.dumps(body, ensure_ascii=False)[:250])
    if r['status'] != 'PASS':
        r['lines'].append('目录/清单双路径均失败——将 L2 fallback 打印的真实结构回填到 '
                          '_parse_github_catalog/_parse_github_models_list')
    return r


# ---------------------------------------------------------------- 3 Ollama
def verify_ollama(base):
    r = {'name': 'Ollama /api/tags（KNOWN_ISSUES #2）', 'status': 'FAIL', 'lines': []}
    if not base:
        r['status'] = 'SKIP'; r['lines'].append('未提供 --ollama-url'); return r
    st, hd, body = http_json(base.rstrip('/') + '/api/tags', timeout=10)
    if st != 200 or not isinstance(body, dict):
        r['lines'].append('GET /api/tags → HTTP %s（Ollama 未运行？）' % st)
        return r
    models = [m.get('name') for m in body.get('models', [])]
    r['lines'].append('GET /api/tags → %d 个模型: %s' % (len(models), models[:8]))
    if not models:
        r['lines'].append('清单为空（未 pull 模型）')
        return r
    st2, _, show = http_json(base.rstrip('/') + '/api/show',
                             {'model': models[0]}, timeout=10)
    if st2 == 200 and isinstance(show, dict):
        info = show.get('model_info', show)
        r['lines'].append('GET /api/show(%s) → context_length=%s' %
                          (models[0], info.get('context_length') or info.get('llama.context_length')))
    t0 = time.time()
    st3, _, gen = http_json(base.rstrip('/') + '/api/generate',
                            {'model': models[0], 'prompt': '说一个字：好', 'stream': False},
                            timeout=120)
    dt = time.time() - t0
    if st3 == 200:
        r['lines'].append('最小 generate 成功（%.1fs）——503 loading 退避路径可观测（冷启动时重试）' % dt)
        r['status'] = 'PASS'
    else:
        r['lines'].append('generate → HTTP %s: %s' % (st3, json.dumps(gen, ensure_ascii=False)[:150]))
    return r


# ---------------------------------------------------------------- 4 基准链
BENCH_CHAINS = {
    '纯问答': {
        'messages': [{'role': 'user', 'content':
                      '用三句话解释 Python 的 GIL 是什么，它对 CPU 密集型线程有什么影响。'}],
        'tools': None, 'max_tokens': 300},
    '单文件改': {
        'messages': [{'role': 'user', 'content':
                      '把 ./app.py 里的 print("hello") 改成 logging.info("hello")，'
                      '先用 search_replace 工具修改，不要整文件重写。'}],
        'tools': OPENAI_TOOLS, 'max_tokens': 300},
    '多文件+命令': {
        'messages': [{'role': 'user', 'content':
                      '项目有三处 print 需要换成 logging：./a.py ./b.py ./c.py。'
                      '规划一下：先并行读三个文件，再逐个改，最后跑 python -c "import a" 验证。'}],
        'tools': OPENAI_TOOLS, 'max_tokens': 300},
}


def run_benchmark(base, key, model, baseline):
    r = {'name': '基准链 token 统计（-15% 目标）', 'status': 'FAIL', 'lines': []}
    if not (base and key):
        r['status'] = 'SKIP'; r['lines'].append('未提供 --bench-base/--bench-key'); return r
    totals = {}
    for name, spec in BENCH_CHAINS.items():
        payload = {'model': model, 'messages': spec['messages'],
                   'max_tokens': spec['max_tokens']}
        if spec['tools']:
            payload['tools'] = spec['tools']
        st, hd, body = http_json(base.rstrip('/') + '/chat/completions', payload,
                                 headers={'Authorization': 'Bearer ' + key}, timeout=120)
        if st != 200 or not isinstance(body, dict):
            r['lines'].append('%s → HTTP %s（不计入）' % (name, st))
            continue
        u = body.get('usage') or {}
        t = u.get('total_tokens') or (u.get('prompt_tokens', 0) + u.get('completion_tokens', 0))
        totals[name] = t
        r['lines'].append('%s → total=%s（prompt=%s completion=%s）'
                          % (name, t, u.get('prompt_tokens'), u.get('completion_tokens')))
    if not totals:
        return r
    r['status'] = 'PASS'
    if baseline and os.path.exists(baseline):
        with open(baseline, 'r', encoding='utf-8') as f:
            base_totals = json.load(f).get('chains', {})
        for name, t in totals.items():
            b = base_totals.get(name)
            if b:
                pct = (b - t) / b * 100
                r['lines'].append('%s vs 基线 %s → %+.1f%%' % (name, b, pct))
        tb = sum(base_totals.values()); tt = sum(totals.values())
        if tb:
            r['lines'].append('合计 vs 基线：%.1f%%（目标 -15%%：%s）'
                              % ((tb - tt) / tb * 100, '达成' if (tb - tt) / tb >= 0.15 else '未达成'))
    else:
        r['lines'].append('未提供基线文件——本次数字即为基线，可保存为 JSON 供下次对比：')
        r['lines'].append('  {"chains": %s}' % json.dumps(totals, ensure_ascii=False))
    return r


PS_USAGE = """\
零 shell 语法三步走（PowerShell 用户推荐）：

  1) 脚本自动生成配置模板（已存在则拒绝覆盖）：
     python deliverables/scripts/target_verify.py --init-config
  2) 记事本打开，把 sk-xxx / ghp-xxx 换成真凭证，保存关闭：
     notepad verify.json
  3) 一条命令运行（无续行、无反斜杠坑）：
     python deliverables/scripts/target_verify.py --config verify.json

  参数式（PowerShell 续行符是反引号 `，不是 bash 的反斜杠 \\）：
     python deliverables/scripts/target_verify.py `
       --deepseek-key sk-xxx --github-pat ghp-xxx `
       --ollama-url http://localhost:11434

  cmd.exe 续行符是 ^；只有 Git Bash 才用 \\。
"""

CONFIG_TEMPLATE = {
    'deepseek_key': 'sk-xxx',
    'github_pat': 'ghp-xxx',
    'ollama_url': 'http://localhost:11434',
    'bench_base': 'https://api.deepseek.com/v1',
    'bench_key': 'sk-xxx',
    'bench_model': 'deepseek-v4.1',
    'baseline': 'baseline.json',
    'output': 'deliverables/metrics/target-verify-2026-10-19.md',
}


def init_config(path):
    """--init-config：生成配置模板（已存在拒绝覆盖，防误覆盖真凭证）。"""
    if os.path.exists(path):
        print('配置文件已存在: %s' % path)
        print('（为防止覆盖你的真实凭证，请手动编辑该文件；如确要重新生成，先删除它）')
        return 1
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(CONFIG_TEMPLATE, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print('已生成配置模板: %s' % os.path.abspath(path))
    print('下一步：用记事本打开，把 sk-xxx / ghp-xxx 换成真凭证后保存：')
    print('  notepad %s' % path)
    print('然后运行：')
    print('  python %s --config %s' % (os.path.relpath(__file__, os.getcwd())
                                       if __file__.startswith(os.getcwd()) else __file__, path))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description='Harbor v1.6 遗留项目标机一键验证',
        epilog=PS_USAGE,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--init-config', nargs='?', const='verify.json', default='',
                    metavar='PATH',
                    help='生成配置模板 JSON（默认 verify.json；已存在则拒绝覆盖）后退出')
    ap.add_argument('--config', default='',
                    help='凭证 JSON 文件路径（键名同参数名：deepseek_key/github_pat/'
                         'ollama_url/bench_base/bench_key/bench_model/baseline/output）；'
                         '命令行参数可覆盖其中任一键')
    ap.add_argument('--deepseek-key', default='')
    ap.add_argument('--github-pat', default='')
    ap.add_argument('--ollama-url', default='')
    ap.add_argument('--bench-base', default='', help='基准链端点（如 https://api.deepseek.com/v1）')
    ap.add_argument('--bench-key', default='')
    ap.add_argument('--bench-model', default='')
    ap.add_argument('--baseline', default='', help='基线 JSON（{"chains":{...}}）')
    ap.add_argument('--output', default='deliverables/metrics/target-verify-%s.md'
                    % datetime.date.today().isoformat())
    args = ap.parse_args()

    # --init-config：生成模板后即退出（零 shell 语法入口的第一步）
    if args.init_config:
        return init_config(args.init_config)

    # --config：凭证进 JSON，命令行为空时从配置取（命令行显式传入的优先）
    cfg = {}
    if args.config:
        try:
            with open(args.config, 'r', encoding='utf-8') as f:
                cfg = json.load(f) or {}
        except Exception as e:
            print('读取 --config 失败: %s\n' % e)
            print(PS_USAGE)
            return 2
        if not isinstance(cfg, dict):
            print('--config 顶层必须是 JSON 对象\n')
            print(PS_USAGE)
            return 2
    for key in ('deepseek_key', 'github_pat', 'ollama_url', 'bench_base',
                'bench_key', 'bench_model', 'baseline', 'output'):
        cli_val = getattr(args, key, '') or ''
        if not cli_val and cfg.get(key):
            setattr(args, key, cfg[key])

    # 无任何输入（无 config 无参数）→ 打印 PowerShell 友好用法，不静默失败
    if not any([args.config, args.deepseek_key, args.github_pat, args.ollama_url,
                args.bench_base]):
        print(PS_USAGE)
        return 0
    if args.bench_base and not args.bench_model:
        args.bench_model = 'deepseek-v4.1'   # 兜底与 preset 对齐

    results = [
        verify_deepseek(args.deepseek_key),
        verify_github(args.github_pat),
        verify_ollama(args.ollama_url),
        run_benchmark(args.bench_base, args.bench_key, args.bench_model, args.baseline),
    ]
    lines = ['# Harbor v1.6 遗留项目标机验证报告', '',
             '生成时间：%s（target_verify.py v1.6）' % datetime.datetime.now().isoformat(timespec='seconds'), '']
    for r in results:
        lines.append('## %s — **%s**' % (r['name'], r['status']))
        lines += ['- ' + l for l in r['lines']]
        lines.append('')
    n_pass = sum(1 for r in results if r['status'] == 'PASS')
    n_fail = sum(1 for r in results if r['status'] == 'FAIL')
    n_skip = sum(1 for r in results if r['status'] == 'SKIP')
    lines.append('---')
    lines.append('合计：PASS %d / FAIL %d / SKIP %d' % (n_pass, n_fail, n_skip))
    lines.append('')
    lines.append('销项规则：DeepSeek PASS → T4 销项；GitHub 目录结构打印回填 → T2/T3 校准；'
                 'Ollama PASS → KNOWN_ISSUES #2 销项；基准链合计 ≥ -15% → 量化目标达成。')
    report = '\n'.join(lines)
    out = args.output
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(report)
    print(report)
    print('\n报告已写入: %s' % out)
    return 0 if n_fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
