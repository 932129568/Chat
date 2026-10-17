# -*- coding: utf-8 -*-
"""生成 GLM-Chat v3 设计预览页（注入 mock 后端桥 + 演示数据），用于视觉走查。

v3 版：基于构建产物 glm-chat.html，注入 mock 桥与演示会话（含 usage / 工具调用记录 / __ms 耗时），
产出 v3 双主题预览（图标导航 + 多面板 + 数据分析面板）。

用法：
    python deliverables/design/make_preview_v3.py light
    python deliverables/design/make_preview_v3.py dark
产出：
    deliverables/design/v3/preview-v3-<theme>.html
"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SRC = os.path.join(ROOT, 'glm-chat.html')
OUT_DIR = os.path.join(ROOT, 'deliverables', 'design', 'v3')

METHODS = """set_current_sid set_session_ws append_memory clear_caches set_ws_dir get_memory
append_worklog write_file take_screenshot set_ws_enabled set_clipboard search_replace
save_workspace_file save_sessions save_config run_powershell run_command run_admin_command
read_more read_file pick_folder open_url open_billing open_app move_path make_dir
list_processes list_dir kill_process get_ws_state get_worklog get_sessions get_file_info
get_effective_ws get_config get_clipboard get_api_info delete_session_ws delete_path
copy_path build_tools build_system_prompt append_file
get_cwd cache_tool_output get_ws_enabled get_session_ws list_recent_ws set_workspace
copy_into_ws rpc""".split()
_seen = set()
METHODS = [m for m in METHODS if not (m in _seen or _seen.add(m))]


def _usage(p, c, cached, model):
    return {"role_waste_guard": None} if False else {
        "prompt_tokens": p, "completion_tokens": c, "total_tokens": p + c,
        "model": model, "prompt_tokens_details": {"cached_tokens": cached}}


def _tool(name, call_id, payload, ms=None):
    m = {"role": "tool", "tool_call_id": call_id, "content": json.dumps(payload, ensure_ascii=False), "__tool": name}
    if ms is not None:
        m["__ms"] = ms
    return m


# 演示数据：全部字段结构与真实运行时一致（usage / tool_calls / role:tool / __ms）
DEMO_SESSIONS = [
    {"id": "s_demo_1", "title": "重构 backend 目录结构", "createdAt": 1760100000000, "updatedAt": 1760103600000,
     "messages": [
         {"role": "user", "content": "帮我把 main.py 里的 Api 类拆成 backend/services，保持 js_api 契约不变。"},
         {"role": "assistant", "content": "我先看一下当前结构，再给出拆分方案。\n\n## 拆分方案\n\n1. `backend/api.py` 作为门面，保持公开方法签名不变\n2. 按职责下沉到 `services/`",
          "usage": _usage(12480, 862, 11200, "glm-5.3-flash")},
         {"role": "assistant", "content": None, "tool_calls": [
             {"id": "c1", "function": {"name": "read_file", "arguments": '{"path":"backend/api.py"}'}},
             {"id": "c2", "function": {"name": "list_dir", "arguments": '{"path":"backend"}'}}]},
         _tool("read_file", "c1", {"ok": True, "content": "class Api: ...(前 2000 行)"}, 210),
         _tool("list_dir", "c2", {"ok": True, "output": "api.py\nmain.py\nservices/"}, 90),
         {"role": "assistant", "content": None, "tool_calls": [
             {"id": "c3", "function": {"name": "write_file", "arguments": '{"path":"backend/services/file_service.py","content":"..."}'}},
             {"id": "c4", "function": {"name": "run_command", "arguments": '{"cmd":"pytest tests/ -q"}'}}]},
         _tool("write_file", "c3", {"ok": True, "path": "backend/services/file_service.py"}, 145),
         _tool("run_command", "c4", {"ok": True, "output": "31 passed in 12.4s"}, 12480),
         {"role": "assistant", "content": "拆分完成，回归测试 **31 passed**。契约方法签名未改动。",
          "usage": _usage(21500, 340, 19800, "glm-5.3-flash")}]},
]
# 再补 5 个轻会话，让趋势图有真实的跨会话形状
for i in range(2, 7):
    p = 3000 + i * 1700
    DEMO_SESSIONS.append({
        "id": "s_demo_%d" % i,
        "title": ["截图省 token 策略", "工具 schema 单一数据源", "压缩 CLI 输出", "缓存命中率排查", "工作区路径 jail"][i - 2],
        "createdAt": 1760000000000 + i * 86400000,
        "updatedAt": 1760000600000 + i * 86400000,
        "messages": [
            {"role": "user", "content": "demo"},
            {"role": "assistant", "content": "demo 回复。", "usage": _usage(p, 420 + i * 60, int(p * 0.78), "glm-5.3-flash" if i % 2 else "glm-5.3-flashx")},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "d%d" % i, "function": {"name": "list_dir", "arguments": '{"path":"."}'}}]},
            _tool("list_dir", "d%d" % i, {"ok": True, "output": "..." if i != 4 else {"error": "目录不存在"}}, 60 + i * 25),
        ]})
# 修正 i=4 的错误工具返回
DEMO_SESSIONS[4]["messages"][3]["content"] = json.dumps({"error": "目录不存在"})

MOCK = """<script>
/* ===== v3 预览用 mock 后端桥（仅视觉走查，不参与打包）===== */
(function(){
  var METHODS = %s;
  var CONFIG = {
    api_key:'sk-demo-preview-key', model:'glm-5.3-flash', tool_mode:'full',
    temperature:1.0, top_p:0.95, max_tokens:16384, reasoning_effort:'auto',
    system_prompt:'你是一名专业的软件开发工程师。', enable_search:false,
    search_engine:'search_pro', shot_quality:'low', saver_level:'std', session_budget:1
  };
  var SESSIONS = %s;
  var WS = {ws:'C:/Users/chen/Desktop/GLM-Chat', bound:false, enabled:true,
            recent:[{path:'C:/Users/chen/Desktop/GLM-Chat', name:'GLM-Chat'}]};
  function J(o){ return JSON.stringify(o); }
  var api = {};
  METHODS.forEach(function(m){
    api[m] = function(){
      switch(m){
        case 'get_memory': return '[]';
        case 'get_config': return J(CONFIG);
        case 'get_sessions': return J(SESSIONS);
        case 'get_api_info': return J({version:'v3-preview', exe:'preview', methods:METHODS});
        case 'get_ws_state': return J(WS);
        case 'get_effective_ws': return J({root:WS.ws, source:'global', enabled:true});
        case 'get_cwd': return WS.ws;
        case 'build_tools': return J([]);
        case 'build_system_prompt': return J('preview');
        default: return J({ok:true});
      }
    };
  });
  window.pywebview = { api: api };
  try {
    localStorage.setItem('glm_theme', '%s');
    localStorage.setItem('glm_fx', '%s');
  } catch(e){}
  /* 演示注入：工具调用三态卡片 + 打开分析面板，方便一眼走查 */
  window.addEventListener('load', function(){
    setTimeout(function(){
      var box = document.getElementById('chatContainer');
      if (box && !document.getElementById('emptyState')) {
        box.insertAdjacentHTML('beforeend',
          '<div class="message assistant"><div class="avatar">AI</div><div class="content">' +
          '<div class="tool-call-item"><span class="tool-spinner"></span><span>read_file · backend/api.py</span></div>' +
          '<div class="tool-call-item done"><span class="tc-dot"></span><span>write_file · backend/services/file_service.py · 已写入 3.2 KB</span></div>' +
          '<div class="tool-call-item fail"><span class="tc-dot"></span><span>run_command · pytest tests/ -q · ✗ 退出码 1：1 failed, 31 passed</span></div>' +
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
    # P2-3：特效开关可由参数控制（--fx off 演示「特效关」持久化），默认开
    fx = '0' if '--fx' in variant or variant.startswith('fxoff') else '1'
    open_panel = ''
    if variant == 'analytics':
        open_panel = "switchPanel('analytics');"
    elif variant == 'settings':
        open_panel = "document.getElementById('settingsPanel').classList.add('show');"
    elif variant == 'workspace':
        open_panel = "switchPanel('workspace');"
    variant_tag = '' if variant.startswith('fxoff') else variant
    html = open(SRC, 'r', encoding='utf-8').read()
    mock = MOCK % (json.dumps(METHODS), json.dumps(DEMO_SESSIONS, ensure_ascii=False), theme, fx, open_panel)
    marker = '<style>'
    idx = html.find(marker)
    if idx < 0:
        print('FATAL: 找不到 <style> 注入点')
        return 1
    out = html[:idx] + mock + html[idx:]
    # 预览页位于 deliverables/design/v3/，libs 相对仓库根上溯三级
    out = out.replace('src="libs/', 'src="../../../libs/')
    name = 'preview-v3-%s%s%s.html' % (theme, ('-' + variant_tag) if variant_tag else '', '-fxoff' if fx == '0' else '')
    out = out.replace('<title>GLM Chat</title>', '<title>GLM Chat v3 · 设计预览 %s</title>' % name)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    open(path, 'w', encoding='utf-8').write(out)
    print('已生成 %s (%d 字节)' % (path, len(out)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
