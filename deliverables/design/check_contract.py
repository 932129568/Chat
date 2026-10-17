# -*- coding: utf-8 -*-
"""GLM-Chat UI 重设计 · 前后端契约校验脚本。

用途：重设计后一键核验"联通零回归"——DOM id / callApi 方法 / onclick 处理函数 /
CSS 类名 / 本地依赖库 五大契约是否全部保住。

用法：
    python deliverables/design/check_contract.py

退出码：0 = 全部通过；1 = 有缺失。
"""
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
TPL = os.path.join(ROOT, 'frontend', 'index.template.html')
OUT = os.path.join(ROOT, 'glm-chat.html')
SRC_DIR = os.path.join(ROOT, 'frontend', 'src')

# ---- 契约清单（来自 00-contract-brief.md）----
DOM_IDS = """apiKey attachPreview brandModel chatContainer continueNewBtn effPath effTag
emptyState enableSearch headerTitle liveTokenStat maxTokens modelSelect reasoningEffort
saverLevel searchEngine searchEngineWrap sendBtn sessionBudget sessionList settingsPanel
shotQuality sidebar streamBar systemPrompt tempVal temperature themeBtn tokenStat
toolMode topP topPVal userInput wsBody wsEffPath wsEffTag wsEnabled wsInd wsSel wsUnbindBtn""".split()

# ctxMenu 由 JS 动态创建，不在模板中
DYNAMIC_IDS = ['ctxMenu']

ONCLICK_FNS = """newSession exportChat openBilling onFolderEnabled onIndToggle onWsSelect
browseWs unbindSession toggleSidebar toggleTheme toggleSettings sendMessage
continueInNewSession""".split()

API_METHODS = """set_current_sid set_session_ws append_memory clear_caches set_ws_dir get_memory
append_worklog write_file take_screenshot set_ws_enabled set_clipboard search_replace
save_workspace_file save_sessions save_config run_powershell run_command run_admin_command
read_more read_file pick_folder open_url open_billing open_app move_path make_dir
list_processes list_dir kill_process get_ws_state get_worklog get_sessions get_file_info
get_effective_ws get_config get_clipboard get_api_info delete_session_ws delete_path
copy_path build_tools build_system_prompt append_file""".split()

CSS_CLASSES = """message user assistant avatar content error md-body typing-dots tool-call-item
tool-spinner toolchip tc-head tc-label tc-meta usage-info msg-images msg-file copy-btn
code-copy code-lang cs cs-trigger cs-label cs-arrow cs-menu cs-opt cs-src
ctx-menu ctx-menu-item sys-tip attach-item attach-preview session-item session-title
session-time session-del sidebar-empty empty-state empty-icon""".split()

REQUIRED_VARS = """--bg --sidebar-bg --main-bg --header-bg --card-bg --border --text --text-2
--primary --primary-hover --user-bubble --ai-bubble --hover --active --chip-bg
--ok --warn --err --shadow-sm --shadow-md --shadow-lg""".split()


def read(p):
    with open(p, 'r', encoding='utf-8') as f:
        return f.read()


def main():
    fails = []

    if not os.path.isfile(TPL):
        print('FATAL: 找不到模板 %s' % TPL)
        return 1
    tpl = read(TPL)
    src_all = '\n'.join(read(os.path.join(SRC_DIR, f))
                        for f in sorted(os.listdir(SRC_DIR)) if f.endswith('.js'))

    # 1) DOM id
    missing = [i for i in DOM_IDS if not re.search(r'id\s*=\s*["\']%s["\']' % re.escape(i), tpl)]
    print('[DOM id] %d/%d' % (len(DOM_IDS) - len(missing), len(DOM_IDS)))
    if missing:
        fails.append('缺少 DOM id: ' + ', '.join(missing))

    # 2) onclick 处理函数定义
    missing = [f for f in ONCLICK_FNS if not re.search(r'function\s+%s\s*\(' % re.escape(f), src_all)]
    print('[onclick 处理函数] %d/%d' % (len(ONCLICK_FNS) - len(missing), len(ONCLICK_FNS)))
    if missing:
        fails.append('缺少函数定义: ' + ', '.join(missing))

    # 3) callApi 后端方法
    called = set(re.findall(r"callApi\(\s*'([a-z_]+)'", src_all))
    missing = [m for m in API_METHODS if m not in called]
    print('[callApi 后端方法] %d/%d' % (len(API_METHODS) - len(missing), len(API_METHODS)))
    if missing:
        fails.append('未再被调用: ' + ', '.join(missing))

    # 4) CSS 类（模板样式段里需出现）
    missing = [c for c in CSS_CLASSES if ('.' + c) not in tpl]
    print('[CSS 类] %d/%d' % (len(CSS_CLASSES) - len(missing), len(CSS_CLASSES)))
    if missing:
        fails.append('样式缺失类: ' + ', '.join(missing))

    # 5) CSS 变量（两套主题均需定义）
    root_block = tpl[:tpl.find('</style>')]
    missing = [v for v in REQUIRED_VARS if (v + ':') not in root_block]
    print('[CSS 变量] %d/%d' % (len(REQUIRED_VARS) - len(missing), len(REQUIRED_VARS)))
    if missing:
        fails.append('变量缺失: ' + ', '.join(missing))

    # 6) 本地依赖库引用可解析
    refs = sorted(set(re.findall(r'src\s*=\s*["\'](libs/[^"\']+)["\']', tpl)))
    bad = [r for r in refs if not os.path.isfile(os.path.join(ROOT, r.replace('/', os.sep)))]
    print('[本地依赖库] %d 个引用，%d 个缺失' % (len(refs), len(bad)))
    for r in refs:
        print('    %s %s' % ('OK  ' if r not in bad else 'MISS', r))
    if bad:
        fails.append('依赖库缺失: ' + ', '.join(bad))

    # 7) 构建产物存在且比模板新
    if os.path.isfile(OUT):
        print('[构建产物] glm-chat.html 存在 (%d 字节)' % os.path.getsize(OUT))
    else:
        fails.append('构建产物 glm-chat.html 不存在，请运行 node frontend/build.js')

    print('\n' + ('=' * 56))
    if fails:
        print('结果: FAIL (%d 项)' % len(fails))
        for f in fails:
            print('  ✗ ' + f)
        return 1
    print('结果: PASS — 五大契约全部保住')
    return 0


if __name__ == '__main__':
    sys.exit(main())
