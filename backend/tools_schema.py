# -*- coding: utf-8 -*-
"""工具 schema 唯一数据源（legacy Api.build_tools L1083-1237 逐字搬迁）。

内容一字未改——AI 已适配 v1.0.0 措辞，改文案 = 行为漂移。
ws_on 由调用方（Api 门面）从 RuntimeState 取后传入，本模块无状态、可单测。

v1.3：新增可选参数 mcp_tools——仅当 role=='full' 且 mcp_tools 非空时在列表尾部追加
（mcp_tools=None 默认 → 与 legacy 逐字节一致，契约差分测试天然通过）。
"""

import json

_S_READ_MORE = {'type': 'function', 'function': {'name': 'read_more',
    'description': '分页读取之前被截断的工具输出全文',
    'parameters': {'type': 'object', 'properties': {
        'cache_id': {'type': 'string'}, 'offset': {'type': 'integer'},
        'limit': {'type': 'integer'}}, 'required': ['cache_id']}}}


def build(role='full', ws_on=True, mcp_tools=None):
    if role == 'chat':
        return json.dumps([], ensure_ascii=False)
    tools = [dict(_S_READ_MORE)]
    if role == 'full':
        if ws_on:
            tools += [
                {'type': 'function', 'function': {'name': 'read_file',
                    'description': '读文件(带行号,一次可读2万行,常规文件一次读全;同版本重复读被拦截,需原文传force=true)',
                    'parameters': {'type': 'object', 'properties': {
                        'path': {'type': 'string'}, 'offset': {'type': 'integer'},
                        'limit': {'type': 'integer'}, 'force': {'type': 'boolean'}},
                        'required': ['path']}}},
                {'type': 'function', 'function': {'name': 'write_file',
                    'description': '整文件写入(UTF-8)。已存在且>20KB 会被拒,改用 search_replace',
                    'parameters': {'type': 'object', 'properties': {
                        'path': {'type': 'string'}, 'content': {'type': 'string'}},
                        'required': ['path', 'content']}}},
                {'type': 'function', 'function': {'name': 'append_file',
                    'description': '追加到文件末尾。10 分钟内同文件限 6 次',
                    'parameters': {'type': 'object', 'properties': {
                        'path': {'type': 'string'}, 'content': {'type': 'string'}},
                        'required': ['path', 'content']}}},
                {'type': 'function', 'function': {'name': 'search_replace',
                    'description': '精确原文局部替换,优先于整文件重写',
                    'parameters': {'type': 'object', 'properties': {
                        'path': {'type': 'string'}, 'old': {'type': 'string'},
                        'new': {'type': 'string'}, 'replace_all': {'type': 'boolean'}},
                        'required': ['path', 'old', 'new']}}},
                {'type': 'function', 'function': {'name': 'list_dir',
                    'description': '列目录,超过 200 项只回前 200+总数',
                    'parameters': {'type': 'object', 'properties': {
                        'path': {'type': 'string'}}, 'required': ['path']}}},
                {'type': 'function', 'function': {'name': 'make_dir',
                    'description': '创建文件夹',
                    'parameters': {'type': 'object', 'properties': {
                        'path': {'type': 'string'}}, 'required': ['path']}}},
                {'type': 'function', 'function': {'name': 'delete_path',
                    'description': '删除文件/目录(进回收站)',
                    'parameters': {'type': 'object', 'properties': {
                        'path': {'type': 'string'}}, 'required': ['path']}}},
                {'type': 'function', 'function': {'name': 'move_path',
                    'description': '移动/重命名',
                    'parameters': {'type': 'object', 'properties': {
                        'path': {'type': 'string'}, 'new_path': {'type': 'string'}},
                        'required': ['path', 'new_path']}}},
                {'type': 'function', 'function': {'name': 'copy_path',
                    'description': '复制文件/目录',
                    'parameters': {'type': 'object', 'properties': {
                        'path': {'type': 'string'}, 'new_path': {'type': 'string'}},
                        'required': ['path', 'new_path']}}},
                {'type': 'function', 'function': {'name': 'get_file_info',
                    'description': '文件大小/修改时间',
                    'parameters': {'type': 'object', 'properties': {
                        'path': {'type': 'string'}}, 'required': ['path']}}},
            ]
        tools += [
            {'type': 'function', 'function': {'name': 'run_command',
                'description': '执行 cmd 命令,输出超长自动截断落盘',
                'parameters': {'type': 'object', 'properties': {
                    'cmd': {'type': 'string'}, 'timeout': {'type': 'integer'}},
                    'required': ['cmd']}}},
            {'type': 'function', 'function': {'name': 'run_powershell',
                'description': '执行 PowerShell 命令,输出超长自动截断落盘',
                'parameters': {'type': 'object', 'properties': {
                    'cmd': {'type': 'string'}, 'timeout': {'type': 'integer'}},
                    'required': ['cmd']}}},
            {'type': 'function', 'function': {'name': 'run_admin_command',
                'description': '管理员权限命令,会弹原生确认框',
                'parameters': {'type': 'object', 'properties': {
                    'cmd': {'type': 'string'}}, 'required': ['cmd']}}},
            {'type': 'function', 'function': {'name': 'open_app',
                'description': '打开软件/文件/文件夹',
                'parameters': {'type': 'object', 'properties': {
                    'path': {'type': 'string'}}, 'required': ['path']}}},
            {'type': 'function', 'function': {'name': 'open_url',
                'description': '用默认浏览器打开网页',
                'parameters': {'type': 'object', 'properties': {
                    'url': {'type': 'string'}}, 'required': ['url']}}},
            {'type': 'function', 'function': {'name': 'take_screenshot',
                'description': '截取当前屏幕; 可选区域参数 left/top/width/height',
                'parameters': {'type': 'object', 'properties': {
                    'left': {'type': 'integer'}, 'top': {'type': 'integer'},
                    'width': {'type': 'integer'}, 'height': {'type': 'integer'}}}}},
            {'type': 'function', 'function': {'name': 'clipboard_read',
                'description': '读取系统剪贴板文本',
                'parameters': {'type': 'object', 'properties': {}}}},
            {'type': 'function', 'function': {'name': 'clipboard_write',
                'description': '写入系统剪贴板文本',
                'parameters': {'type': 'object', 'properties': {
                    'text': {'type': 'string'}}, 'required': ['text']}}},
            {'type': 'function', 'function': {'name': 'list_processes',
                'description': '列出进程(按内存降序, 可关键字过滤), 配合 kill_process',
                'parameters': {'type': 'object', 'properties': {
                    'keyword': {'type': 'string'}}, 'required': []}}},
            {'type': 'function', 'function': {'name': 'kill_process',
                'description': '结束进程(按 pid 或进程名), 请先 list_processes 确认再杀',
                'parameters': {'type': 'object', 'properties': {
                    'pid': {'type': 'integer'}, 'name': {'type': 'string'}},
                    'required': []}}},
            {'type': 'function', 'function': {'name': 'append_memory',
                'description': '写入跨会话长期记忆',
                'parameters': {'type': 'object', 'properties': {
                    'content': {'type': 'string'}}, 'required': ['content']}}},
        ]
    elif role == 'ro':
        if ws_on:
            tools += [
                {'type': 'function', 'function': {'name': 'read_file',
                    'description': '读文件片段(带行号)',
                    'parameters': {'type': 'object', 'properties': {
                        'path': {'type': 'string'}, 'offset': {'type': 'integer'},
                        'limit': {'type': 'integer'}, 'force': {'type': 'boolean'}},
                        'required': ['path']}}},
                {'type': 'function', 'function': {'name': 'list_dir',
                    'description': '列目录',
                    'parameters': {'type': 'object', 'properties': {
                        'path': {'type': 'string'}}, 'required': ['path']}}},
                {'type': 'function', 'function': {'name': 'get_file_info',
                    'description': '文件大小/修改时间',
                    'parameters': {'type': 'object', 'properties': {
                        'path': {'type': 'string'}}, 'required': ['path']}}},
            ]
        tools += [
            {'type': 'function', 'function': {'name': 'run_powershell',
                'description': '执行 PowerShell 命令',
                'parameters': {'type': 'object', 'properties': {
                    'cmd': {'type': 'string'}}, 'required': ['cmd']}}},
            {'type': 'function', 'function': {'name': 'open_app',
                'description': '打开软件/文件',
                'parameters': {'type': 'object', 'properties': {
                    'path': {'type': 'string'}}, 'required': ['path']}}},
            {'type': 'function', 'function': {'name': 'take_screenshot',
                'description': '截取当前屏幕',
                'parameters': {'type': 'object', 'properties': {}}}},
            {'type': 'function', 'function': {'name': 'clipboard_read',
                'description': '读取系统剪贴板文本',
                'parameters': {'type': 'object', 'properties': {}}}},
            {'type': 'function', 'function': {'name': 'list_processes',
                'description': '列出进程(按内存降序)',
                'parameters': {'type': 'object', 'properties': {
                    'keyword': {'type': 'string'}}, 'required': []}}},
            {'type': 'function', 'function': {'name': 'append_memory',
                'description': '写入跨会话长期记忆',
                'parameters': {'type': 'object', 'properties': {
                    'content': {'type': 'string'}}, 'required': ['content']}}},
        ]
    # v1.3 MCP：仅 full 角色且调用方显式传入时尾部追加（默认路径零变化）
    if role == 'full' and mcp_tools:
        tools += list(mcp_tools)
    return json.dumps(tools, ensure_ascii=False)
