# -*- coding: utf-8 -*-
"""Harbor 入口：装配 backend 并启动 pywebview 窗口。

业务逻辑全部在 backend/ 包（门面 + services + 基础设施）；
本文件只做装配与启动，`import main` 不产生副作用（webview 延迟导入）。
"""
import atexit
import datetime
import os
import sys

from backend import paths
from backend.api import API_VERSION, Api
from backend.fio import cleanup_stale_tmps
from backend.logging_setup import setup_logging
from backend.services.local_proxy import shutdown_proxy
from backend.services.update_service import APP_VERSION, cleanup_old_backup


def _write_api_log(api):
    """API 方法清单落盘（legacy L1249-1268 原样搬迁，供发布后核对契约）。"""
    try:
        try:
            src = os.path.abspath(__file__)
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(src)).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            src, mtime = 'unknown', 'unknown'
        try:
            exe_path = sys.executable if getattr(sys, 'frozen', False) else 'python(main.py)'
        except Exception:
            exe_path = 'unknown'
        methods = sorted(n for n in dir(api) if not n.startswith('_') and callable(getattr(api, n)))
        with open(paths.API_METHODS_LOG, 'w', encoding='utf-8') as f:
            f.write('api_version : %s\n' % API_VERSION)
            f.write('exe_path    : %s\n' % exe_path)
            f.write('main_src    : %s (%s)\n' % (src, mtime))
            f.write('started_at  : %s\n' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            f.write('methods     : %s\n' % ', '.join(methods))
    except Exception:
        pass


def _enable_context_menu(window):
    """强制开启 WebView2 右键菜单（pywebview 非 debug 模式默认关闭）。
    CoreWebView2 只能在 UI 线程访问；loaded 回调在后台线程，
    必须 BeginInvoke 切回 UI 线程，否则报
    'CoreWebView2 can only be accessed from the UI thread' / E_NOINTERFACE。"""
    try:
        form = window.native
        if form is None:
            print('[ctxmenu] 窗口未就绪，前端自定义右键菜单兜底')
            return

        def _find_ctrl():
            # 只能在 UI 线程里找控件、读属性
            for name in ('web_view', 'webview', 'webView'):
                ctrl = getattr(form, name, None)
                if ctrl is not None:
                    return ctrl
            try:
                for c in form.Controls:
                    if 'WebView2' in c.GetType().FullName:
                        return c
            except Exception:
                pass
            return None

        def _ui_work():
            try:
                ctrl = _find_ctrl()
                core = getattr(ctrl, 'CoreWebView2', None) if ctrl is not None else None
                if core is None:
                    print('[ctxmenu] CoreWebView2 暂不可用，前端自定义右键菜单兜底')
                    return
                core.Settings.AreDefaultContextMenusEnabled = True
                core.Settings.AreDevToolsEnabled = True
                print('[ctxmenu] 原生右键菜单已开启')
            except Exception as e:
                print('[ctxmenu] UI 线程内开启失败，前端自定义右键菜单兜底:', e)

        from System import Action
        form.BeginInvoke(Action(_ui_work))
    except Exception as e:
        print('[ctxmenu] 开启失败，前端自定义右键菜单兜底:', e)


def main():
    # 复核修正：前置初始化纳入兜底——原 ensure_dirs/setup_webview_env/
    # setup_logging/cleanup_old_backup 在 S9 兜底 try 之外，HOME 只读/重定向
    # 等异常时直接崩（console=False 零痕迹，日志也尚未建立）
    log = None
    try:
        paths.ensure_dirs()
        paths.setup_webview_env()
        log = setup_logging()
        cleanup_old_backup(log)   # 建议㉖：清理上次自更新残留的 .bak/sentinel
        # 修复（本轮）：fio.cleanup_stale_tmps 原无调用方（死代码）——启动时清理
        # 历史遗留的原子写临时文件（崩溃未来得及 os.replace 的 .glm_tmp_*，原会
        # 永久驻留 CONFIG_DIR/TOOLCACHE_DIR 等）。目录取 paths 下实际存在的常量；
        # plans/checkpoints 是 plan_service 落在 CONFIG_DIR 下的子目录（paths 无
        # 独立常量，按同口径推导）。清理失败不影响启动。
        try:
            _tmp_dirs = [paths.CONFIG_DIR, paths.TOOLCACHE_DIR,
                         os.path.join(paths.CONFIG_DIR, 'plans'),
                         os.path.join(paths.CONFIG_DIR, 'checkpoints')]
            _cleaned = cleanup_stale_tmps(_tmp_dirs)
            if _cleaned:
                log.info('启动清理原子写残留临时文件 %d 个', _cleaned)
        except Exception as e:
            log.debug('原子写残留清理失败（不影响启动）: %r', e)
    except Exception as _init_err:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, 'Harbor 启动初始化失败：\n\n%s\n\n'
                   '（用户目录不可写或磁盘异常；修复后重试）' % _init_err,
                'Harbor 启动失败', 0x10)
        except Exception:
            print('Harbor 启动失败:', _init_err)
        return 1

    try:   # 修复 S9：启动路径异常兜底（叠加日志后不再零痕迹）
        import webview  # 延迟导入：保证 `import main` 在无 webview 环境可用（可测试性）

        # 复核批（2026-10-24 真机实证）：WebView2 把无交互窗口按后台页处置——
        # rAF 停止派发/定时器降频/渲染面挂起（流式生成冻结直到下一次输入强制
        # 重绘）。pywebview 5.4 edgechromium 硬编码 AdditionalBrowserArguments
        # （覆盖 WEBVIEW2_* 环境变量），只能包一层 BrowserView.__init__ 在
        # CreationProperties 就位后追加禁用后台化旗标（此时异步初始化尚未
        # 跑消息循环，无竞态）。失败静默（非 Windows/未来版本兼容）。
        def _patch_webview2_foreground():
            try:
                from webview.platforms import edgechromium as _ec
                _EXTRA = (' --disable-backgrounding-occluded-windows'
                          ' --disable-renderer-backgrounding'
                          ' --disable-background-timer-throttling')
                _orig_init = _ec.BrowserView.__init__

                def _init(self, *a, **k):
                    _orig_init(self, *a, **k)
                    try:
                        props = self.webview.CreationProperties
                        props.AdditionalBrowserArguments = \
                            (props.AdditionalBrowserArguments or '') + _EXTRA
                        self.webview.CreationProperties = props
                    except Exception:
                        pass
                _ec.BrowserView.__init__ = _init
            except Exception:
                pass
        _patch_webview2_foreground()

        html_path = paths.get_html_path()
        api = Api()
        _write_api_log(api)

        # v1.3 MCP：进程退出时按规范关停全部 stdio 子进程（关 stdin→等→TERM→KILL）
        atexit.register(api.mcp_shutdown)
        # v1.9.0 M3：浏览器驱动服务随进程退出关闭全部会话（daemon sweeper 双保险）
        atexit.register(api._driver.shutdown)
        # v1.6 HF-P0：本地 CORS 代理随进程退出关停（daemon 线程，双保险）
        atexit.register(shutdown_proxy)

        window = webview.create_window(
            # 修复（2026-10-17）：窗口标题显示**应用版本**（APP_VERSION，用户感知版本），
            # 不再是 API_VERSION（js_api 契约版本，被契约差分钉死永远 v1.0.0）——
            # 原标题让用户永远看到 v1.0.0，无法判断自己跑的版本/更新是否生效
            'Harbor [v' + APP_VERSION + ']',
            url=html_path,
            js_api=api,
            width=1180,
            height=800,
            min_size=(860, 620),
        )
        api._set_window(window)  # Window 引用放 RuntimeState，不挂 js_api 实例（同时武装护栏）

        # v1.8.0 B 域：搜索次窗装配（照 api._set_window 注入模式——680×520 隐藏
        # 备用，CAPTCHA 接管时置顶；创建失败不阻塞启动：search_browser.open_url
        # 自动回落 urllib 直连抓取，联调规范 §5.1③ 降级链）
        # 修复（2026-10-20 启动崩溃）：次窗 url **必须与主窗口同盘符**——pywebview
        # webview/__init__.py:277 对所有 is_local_url 窗口取 commonpath，而
        # 'about:blank' 被 is_local_url 判 True（util.py:75 不排除它），与主窗口
        # 'file:///C:/...' commonpath 时报「Paths don't have the same drive」
        # （file: vs about: 伪盘符）直接崩在 webview.start()。指向主窗口同一
        # harbor.html（次窗 hidden，加载什么无所谓，用时 load_url 导航）。
        try:
            _search_win = webview.create_window(
                'Harbor 搜索', url=html_path, js_api=None,
                width=680, height=520, hidden=True)
            api._search.set_window(_search_win)
            atexit.register(api._search.shutdown)   # 退出时停回收线程 + 销毁次窗
        except Exception as e:            log.warning('搜索次窗装配失败（搜索将回落 urllib 直连抓取）: %r', e)

        window.events.loaded += lambda: _enable_context_menu(window)

        # 修复（2026-10-21 用户实测 P1）：关窗后进程永驻。pywebview 的
        # webview.start() 要等**所有**窗口关闭才返回——「Harbor 搜索」次窗
        # （hidden=True，CAPTCHA 接管时置顶）用户永远关不掉，start() 于是
        # 永不返回，两个 Harbor 进程（onefile 父子）全部残留。
        # 实测复现：关主窗 6s 后 [24556,12132] 仍在；窗口枚举可见
        # 「Harbor 搜索」真窗口（hidden 只是初始不可见）。
        # 修法：主窗 closing 时显式 destroy 其余窗口，start() 随即返回，
        # atexit（mcp_shutdown 等）正常跑完，进程树干净退出。
        def _on_main_closing():
            try:
                for w in list(webview.windows):
                    if w is not window:
                        w.destroy()
                        log.info('关窗时销毁次窗: %s', getattr(w, 'title', '?'))
            except Exception as e:
                log.warning('关窗销毁次窗失败: %r', e)
            return True     # 允许主窗继续关闭
        window.events.closing += _on_main_closing

        # 真机测试 CDP 开关（2026-10-17）：GLM_CDP_PORT 环境变量设置时才开启
        # remote-debugging 端口（默认不设=生产零行为差异；pywebview 的
        # AdditionalBrowserArguments 硬编码会覆盖 WEBVIEW2_* 环境变量，只能走
        # 它自己的 settings['REMOTE_DEBUGGING_PORT']）。用于 GUI 自动化回归。
        _cdp_port = os.environ.get('GLM_CDP_PORT', '').strip()
        if _cdp_port:
            try:
                webview.settings['REMOTE_DEBUGGING_PORT'] = int(_cdp_port)
                log.info('CDP 调试端口已开启：%s（真机测试模式）', _cdp_port)
            except Exception as e:
                log.warning('CDP 端口开启失败：%r', e)

        webview.start()
    except Exception as e:
        try:
            log.exception('Harbor 启动失败')
        except Exception:
            pass
        # console=False 下用户双击“什么都没发生”是最差体验：弹原生框提示
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, 'Harbor 启动失败：\n\n%s\n\n请确认已安装 WebView2 Runtime '
                   '（Windows 11 自带；否则到微软官网下载安装）。\n日志：%s'
                   % (e, os.path.join(paths.LOG_DIR, 'harbor.log')),
                'Harbor 启动失败', 0x10)
        except Exception:
            try:
                print('Harbor 启动失败:', e)
            except Exception:
                pass
        raise SystemExit(1)


if __name__ == '__main__':
    main()
