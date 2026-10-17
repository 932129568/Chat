# -*- coding: utf-8 -*-
"""生成 GLM-Chat 设计预览页（注入 mock 后端桥 + 演示数据），用于视觉走查。

用法：
    python deliverables/design/make_preview.py light
    python deliverables/design/make_preview.py dark
产出：
    deliverables/design/preview-<theme>.html
"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SRC = os.path.join(ROOT, 'glm-chat.html')
OUT_DIR = os.path.join(ROOT, 'deliverables', 'design')

METHODS = """set_current_sid set_session_ws append_memory clear_caches set_ws_dir get_memory
append_worklog write_file take_screenshot set_ws_enabled set_clipboard search_replace
save_workspace_file save_sessions save_config run_powershell run_command run_admin_command
read_more read_file pick_folder open_url open_billing open_app move_path make_dir
list_processes list_dir kill_process get_ws_state get_worklog get_sessions get_file_info
get_effective_ws get_config get_clipboard get_api_info delete_session_ws delete_path
copy_path build_tools build_system_prompt append_file
get_cwd cache_tool_output get_ws_enabled get_session_ws list_recent_ws set_workspace
copy_into_ws get_ws_enabled rpc""".split()
# 去重并保持顺序
_seen = set()
METHODS = [m for m in METHODS if not (m in _seen or _seen.add(m))]

DEMO_SESSIONS = [
    {
        "id": "s_demo_1",
        "title": "重构 backend 目录结构",
        "createdAt": 1760500000000,
        "updatedAt": 1760503600000,
        "messages": [
            {"role": "user", "content": "帮我把 main.py 里的 Api 类拆成 backend/services，保持 js_api 契约不变。"},
            {"role": "assistant", "content": "我先看一下当前的 `main.py` 结构，再给出拆分方案。\n\n## 拆分方案\n\n1. `backend/api.py` 作为门面，保持 50 个公开方法签名不变\n2. 按职责下沉到 `services/`：\n   - `config_service.py` — 配置与记忆\n   - `file_service.py` — 文件读写 + 路径 jail\n   - `cmd_service.py` — 命令执行 + 去重\n\n```python\nclass Api:\n    def __init__(self):\n        self._runtime = RuntimeState()\n        self._config = ConfigService()\n        self._files = FileService(self._runtime, self._workspace)\n```\n\n> 关键：`get_clipboard` / `set_clipboard` 这两个\"方言\"方法名不能改，前端按位置传参。",
             "usage": {"prompt_tokens": 12480, "completion_tokens": 862, "total_tokens": 13342,
                       "model": "glm-5.3-flash",
                       "prompt_tokens_details": {"cached_tokens": 11200}}},
            {"role": "assistant", "content": "现在读取 `backend/services/file_service.py` 确认路径校验逻辑。",
             "tool_calls": [
                 {"function": {"name": "read_file", "arguments": '{"path":"backend/services/file_service.py"}'}},
                 {"function": {"name": "run_command", "arguments": '{"cmd":"pytest tests/ -q"}'}}
             ]},
            {"role": "assistant", "content": "拆分完成，回归测试 **30 passed**。`_resolve_ws` 的路径 jail 判定未改动。",
             "usage": {"prompt_tokens": 21500, "completion_tokens": 340, "total_tokens": 21840,
                       "model": "glm-5.3-flash",
                       "prompt_tokens_details": {"cached_tokens": 19800}}}
        ]
    },
    {"id": "s_demo_2", "title": "截图省 token 策略", "createdAt": 1760400000000,
     "updatedAt": 1760400600000, "messages": [{"role": "user", "content": "截图怎么省 token？"}]},
    {"id": "s_demo_3", "title": "工具 schema 单一数据源", "createdAt": 1760300000000,
     "updatedAt": 1760300600000, "messages": [{"role": "user", "content": "前端 TOOLS 副本删掉。"}]}
]

MOCK = """<script>
/* ===== 预览用 mock 后端桥（仅视觉走查，不参与打包）===== */
(function(){
  var METHODS = %s;
  var CONFIG = {
    api_key:'sk-demo-preview-key', model:'glm-5.3-flash', tool_mode:'full',
    temperature:1.0, top_p:0.95, max_tokens:16384, reasoning_effort:'auto',
    system_prompt:'你是一名专业的软件开发工程师。', enable_search:false,
    search_engine:'search_pro', shot_quality:'low', saver_level:'std', session_budget:1
  };
  var SESSIONS = %s;
  var WS = {ws:'C:/Users/陈/Desktop/GLM-Chat-v1.0.0-完整开发包', bound:false, enabled:true,
            recent:[{path:'C:/Users/陈/Desktop/GLM-Chat-v1.0.0-完整开发包', name:'GLM-Chat'}]};
  function J(o){ return JSON.stringify(o); }
  var api = {};
  METHODS.forEach(function(m){
    api[m] = function(){
      switch(m){
        case 'get_memory': return '[]';
        case 'get_config': return J(CONFIG);
        case 'get_sessions': return J(SESSIONS);
        case 'get_api_info': return J({version:'v1.0.0', exe:'preview', methods:METHODS});
        case 'get_ws_state': return J(WS);
        case 'get_effective_ws': return J({root:WS.ws, source:'global', enabled:true});
        case 'get_cwd': return WS.ws;
        case 'build_tools': return J([]);
        case 'build_system_prompt': return J({ok:true, result:'preview'});
        default: return J({ok:true});
      }
    };
  });
  window.pywebview = { api: api };
  try { localStorage.setItem('glm_theme', '%s'); } catch(e){}
  /* 演示注入：工具调用三态卡片 + 可选展开设置面板 */
  window.addEventListener('load', function(){
    setTimeout(function(){
      var box = document.getElementById('chatContainer');
      if (box && !document.getElementById('emptyState')) {
        box.insertAdjacentHTML('beforeend',
          '<div class="message assistant"><div class="avatar">AI</div><div class="content">' +
          '<div class="tool-call-item"><span class="tool-spinner"></span><span>read_file · backend/services/file_service.py</span></div>' +
          '<div class="tool-call-item done"><span class="tc-dot"></span><span>write_file · backend/services/config_service.py · 已写入 3.2 KB</span></div>' +
          '<div class="tool-call-item fail"><span class="tc-dot"></span><span>run_command · pytest tests/ -q · ✗ 退出码 1：1 failed, 30 passed</span></div>' +
          '</div></div>');
        box.scrollTop = box.scrollHeight;
      }
      %s
    }, 1200);
  });
})();
</script>
"""


def main():
    theme = (sys.argv[1] if len(sys.argv) > 1 else 'light').lower()
    variant = (sys.argv[2] if len(sys.argv) > 2 else '').lower()
    if theme not in ('light', 'dark'):
        theme = 'light'
    open_settings = ("document.getElementById('settingsPanel').classList.add('show');"
                     if variant == 'settings' else '')
    sessions = [] if variant == 'empty' else DEMO_SESSIONS
    html = open(SRC, 'r', encoding='utf-8').read()
    mock = MOCK % (json.dumps(METHODS), json.dumps(sessions, ensure_ascii=False),
                   theme, open_settings)
    # 注入点：<style> 之前，保证 mock 在底部 app script 之前执行
    marker = '<style>'
    idx = html.find(marker)
    if idx < 0:
        print('FATAL: 找不到 <style> 注入点')
        return 1
    out = html[:idx] + mock + html[idx:]
    # 预览页位于 deliverables/design/，需把 libs/ 引用改为相对仓库根的路径
    out = out.replace('src="libs/', 'src="../../libs/')
    name = 'preview-%s%s.html' % (theme, ('-' + variant) if variant else '')
    out = out.replace('<title>GLM Chat</title>', '<title>GLM Chat · 设计预览 %s</title>' % name)
    path = os.path.join(OUT_DIR, name)
    open(path, 'w', encoding='utf-8').write(out)
    print('已生成 %s (%d 字节)' % (path, len(out)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
