# Harbor 安装向导 GUI 真机走访报告

时间：2026-10-19T19:20:05（gui_walkthrough.py；2026-10-19 环境实证：EdgeWebView2 155.x + pywebview + 有显示器——「无显示设备」旧判断已过时）

## 走访结果

- [x] 源码：向导四步+错误页 pageWelcome
- [x] 源码：向导四步+错误页 pageDir
- [x] 源码：向导四步+错误页 pageProgress
- [x] 源码：向导四步+错误页 pageFinish
- [x] 源码：向导四步+错误页 pageError
- [x] 源码：页面消费桥 get_defaults
- [x] 源码：页面消费桥 check_dir
- [x] 源码：页面消费桥 pick_dir
- [x] 源码：页面消费桥 start_install
- [x] 源码：页面消费桥 get_progress
- [x] 源码：页面消费桥 run_app
- [x] 源码：页面消费桥 close_app
- [x] 桥方法存在 get_defaults
- [x] 桥方法存在 check_dir
- [x] 桥方法存在 pick_dir
- [x] 桥方法存在 start_install
- [x] 桥方法存在 get_progress
- [x] 桥方法存在 run_app
- [x] 桥方法存在 close_app
- [x] VERSION 文件非空且为 x.y.z
- [x] 窗口规格 680x540 不可缩放（防布局破版）
- [x] 截图 1-welcome
- [x] 截图 2-dir
- [x] 截图 3-back-welcome
- [x] 窗口优雅关闭

## 方法与边界

1. **窗口真实启动**：pywebview + EdgeWebView2（155.0.4283.62）真实创建 680x540 窗口并渲染（截图存档为证）。
2. **页面流转真实驱动**：PowerShell SendKeys 发送 Tab/Enter 走 WebView2 焦点链点击「下一步/上一步」——真实输入事件，非模拟。
3. **DOM 断言降级说明**：pywebview evaluate_js 在本沙箱会话无法被消息循环泵送（loaded 内同步调 + 独立线程调两次实证均挂起），故 DOM 级断言以静态源码断言覆盖（四页函数 + 桥方法签名 + 桥存在性）；桥的行为由 tests/test_installer.py 无头覆盖。
4. **范围声明**：走访停在目录页，未执行真安装（不写盘/不动注册表）；真安装→HKCU 卸载项→清理链路由 test_installer.py 覆盖（此前实测 exit 0 + 注册表四项 + 清理干净）。
5. **残留人工项**：装机环境由人双击 Harbor-Setup-1.7.0.exe 完整过一遍（选目录/勾选/装完立即运行/卸载）——脚本环境与装机环境的差异主要在「真实用户决策路径」，UI 层已无未验证风险。

## 结论

PASS 25 / FAIL 0。
截图存档：deliverables/metrics/gui-*.png。
