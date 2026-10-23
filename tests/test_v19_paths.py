# -*- coding: utf-8 -*-
"""v1.9.0 T01 路径常量与 frozen 打包核对回归。

锁定（deliverables/dev-plan/v19-m1m2-design.md §B-T01 测试点）：
- test_new_path_constants：A2.4 六常量逐字在位（config.json 零污染铁律）；
- test_ensure_dirs_creates_platform_dir：ensure_dirs 建 PLATFORM_DIR（secrets 落盘前置）；
- test_spec_datas_has_prompts：Harbor.spec datas 已声明 prompts 目录（frozen 安全，零改核对）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import fresh_home  # noqa: E402

from backend import paths  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A2.4 六常量逐字快照（相对 CONFIG_DIR 的文件名/目录名）
_NEW_CONSTANTS = {
    'BROWSER_SESSIONS_FILE': 'browser_sessions.json',
    'READER_FILE': 'reader.json',
    'AUDIT_CHAIN_FILE': 'audit_chain.json',
    'CHECKPOINTS_FILE': 'checkpoints.json',
    'PLATFORM_DIR': 'platform',
    'BROWSER_PROFILE_DIR': 'browser_profile',
}


class TestNewPathConstants:
    def test_new_path_constants(self):
        """六常量全部落在 ~/.glm-chat（CONFIG_DIR）下，逐字采用 A2.4。"""
        for name, leaf in _NEW_CONSTANTS.items():
            assert hasattr(paths, name), name
            got = getattr(paths, name)
            assert got == os.path.join(paths.CONFIG_DIR, leaf), name
        # 全部为 CONFIG_DIR 直属（config.json 零污染铁律：新配置独立文件）
        assert paths.CONFIG_DIR == os.path.join(os.path.expanduser('~'), '.glm-chat')

    def test_constants_not_polluting_config_path(self):
        """config.json 路径本身未被改动（契约红线）；新常量互不相同。"""
        assert paths.CONFIG_PATH == os.path.join(paths.CONFIG_DIR, 'config.json')
        new_paths = [getattr(paths, name) for name in _NEW_CONSTANTS]
        assert paths.CONFIG_PATH not in new_paths
        assert len(set(new_paths)) == len(new_paths)


class TestEnsureDirs:
    def test_ensure_dirs_creates_platform_dir(self, fresh_home):
        """ensure_dirs 创建 PLATFORM_DIR（M1.4 secrets 落盘前置）。"""
        assert not os.path.isdir(paths.PLATFORM_DIR)
        paths.ensure_dirs()
        assert os.path.isdir(paths.PLATFORM_DIR)
        # 既有目录语义不变
        assert os.path.isdir(paths.CONFIG_DIR)
        assert os.path.isdir(paths.WEBVIEW_DATA_DIR)
        # 幂等（重复调用不抛）
        paths.ensure_dirs()
        assert os.path.isdir(paths.PLATFORM_DIR)


class TestSpecFrozenSafe:
    def test_spec_datas_has_prompts(self):
        """Harbor.spec datas 声明 backend/prompts（frozen 下 loader 定位同口径）。"""
        with open(os.path.join(PROJECT_ROOT, 'Harbor.spec'), encoding='utf-8') as f:
            spec = f.read()
        assert "('backend/prompts', 'backend/prompts')" in spec
        # send2trash / PIL.ImageGrab hiddenimports 在位（platform/win 运行时可选依赖）
        assert "'send2trash'" in spec and "'PIL.ImageGrab'" in spec
