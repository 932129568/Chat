# -*- coding: utf-8 -*-
"""路径常量与 PyInstaller frozen 适配。

从 legacy main.py L23-26/L133-134/L1239-1244 原样搬迁。
所有路径在 import 时基于 expanduser('~') 计算（与 legacy 行为一致），
测试通过重定向 USERPROFILE/HOME 环境变量隔离。
"""
import os
import sys

CONFIG_DIR_NAME = '.glm-chat'

CONFIG_DIR = os.path.join(os.path.expanduser('~'), CONFIG_DIR_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')
SESSIONS_PATH = os.path.join(CONFIG_DIR, 'sessions.json')
# v1.8.0 历史自选存放（2026-10-21 用户需求）：history.json 独立文件存用户选的
# 目录（config.json 零污染铁律——契约测试比对 config.json）。空/缺失 = 默认
# SESSIONS_PATH（~/.glm-chat/sessions.json）。
HISTORY_FILE = os.path.join(CONFIG_DIR, 'history.json')
MEMORY_PATH = os.path.join(CONFIG_DIR, 'memory.json')
SESSION_WS_FILE = os.path.join(CONFIG_DIR, 'session_ws.json')
RECENT_WS_FILE = os.path.join(CONFIG_DIR, 'recent_ws.json')
WS_ENABLED_FILE = os.path.join(CONFIG_DIR, 'ws_enabled.json')
# v1.3 MCP：服务器配置独立文件（Claude 兼容结构；不碰 config.json——契约红线）
MCP_SERVERS_FILE = os.path.join(CONFIG_DIR, 'mcp_servers.json')
TOOLCACHE_DIR = os.path.join(CONFIG_DIR, 'toolcache')
SCREENSHOTS_DIR = os.path.join(CONFIG_DIR, 'screenshots')
LOG_DIR = os.path.join(CONFIG_DIR, 'logs')
API_METHODS_LOG = os.path.join(CONFIG_DIR, 'api_methods.log')
WEBVIEW_DATA_DIR = os.path.join(CONFIG_DIR, 'webview_data')


def ensure_dirs():
    """创建运行必需目录（legacy: 模块级 makedirs webview_data + Api.__init__ 建 config_dir）。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(WEBVIEW_DATA_DIR, exist_ok=True)


def setup_webview_env():
    """固定 WebView2 用户数据目录（legacy L133-135：import 即执行；这里改为入口显式调用，
    使 `import backend` 无副作用、可在无 GUI 环境使用）。"""
    os.environ['WEBVIEW2_USER_DATA_FOLDER'] = WEBVIEW_DATA_DIR


def get_html_path():
    """PyInstaller onefile 下 html 在 sys._MEIPASS，开发时在 main.py 同目录。"""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'harbor.html')
