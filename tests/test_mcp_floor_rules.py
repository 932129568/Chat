# -*- coding: utf-8 -*-
"""W10 MCP 楼层规则回归：tool_schemas 三道闸（描述长度/单 server 数/总数）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import fresh_home  # noqa: E402


def _mk_service():
    from backend.services.mcp_service import McpService
    from backend.services.guard_service import GuardService
    from backend.services.mcp_config_service import McpConfigService
    from backend.services.toolcache_service import ToolcacheService
    cfg = McpConfigService()
    guard = GuardService()
    return McpService(cfg, guard, ToolcacheService(do_cleanup=False))


def _seed_rt(svc, servers):
    """注册 enabled 服务器 + 塞运行时表（_rt）模拟 ok + 工具清单。"""
    for name in servers:
        svc._cfg.save_server(name, {'enabled': True, 'command': 'x'})
    with svc._lock:
        for name, tools in servers.items():
            svc._rt[name] = {'status': 'ok', 'tools': tools}


class TestFloorRules:
    def test_desc_truncation(self, fresh_home):
        svc = _mk_service()
        long_desc = 'x' * 900
        _seed_rt(svc, {'srv': [{'name': 't1', 'description': long_desc}]})
        with svc._lock:
            svc._rt['srv']['status'] = 'ok'
        out = svc.tool_schemas()
        assert len(out) == 1
        d = out[0]['function']['description']
        assert d.endswith('…[已截断]')
        assert len(d) <= svc.MAX_TOOL_DESC_CHARS + len('…[已截断]')
        assert svc._floor_stats['truncated_desc'] == 1

    def test_per_server_cap(self, fresh_home):
        svc = _mk_service()
        tools = [{'name': 't%d' % i, 'description': 'd'} for i in range(80)]
        _seed_rt(svc, {'srv': tools})
        out = svc.tool_schemas()
        assert len(out) == svc.MAX_TOOLS_PER_SERVER == 50
        assert svc._floor_stats['skipped_per_server'] == 30

    def test_total_cap(self, fresh_home):
        svc = _mk_service()
        # 5 个 server × 50 工具 = 250 → 总量闸 200 截断
        _seed_rt(svc, {('srv%d' % i): [
            {'name': 't%d' % j, 'description': 'd'} for j in range(50)]
            for i in range(5)})
        out = svc.tool_schemas()
        assert len(out) == svc.MAX_TOTAL_TOOLS == 200
        assert svc._floor_stats['skipped_total'] == 50

    def test_sorted_stable_order(self, fresh_home):
        svc = _mk_service()
        _seed_rt(svc, {'bbb': [{'name': 't', 'description': 'd'}],
                       'aaa': [{'name': 't', 'description': 'd'}],
                       'ccc': [{'name': 't', 'description': 'd'}]})
        out = svc.tool_schemas()
        names = [o['function']['name'] for o in out]
        assert names == ['mcp__aaa__t', 'mcp__bbb__t', 'mcp__ccc__t']

    def test_normal_passthrough(self, fresh_home):
        svc = _mk_service()
        _seed_rt(svc, {'srv': [
            {'name': 'get', 'description': '获取数据',
             'inputSchema': {'type': 'object', 'properties': {'q': {'type': 'string'}}}}]})
        out = svc.tool_schemas()
        assert out[0]['function']['description'] == '[MCP·srv] 获取数据'
        assert out[0]['function']['parameters']['properties']['q'] == {'type': 'string'}
        assert svc._floor_stats == {'truncated_desc': 0, 'skipped_per_server': 0,
                                    'skipped_total': 0, 'emitted': 1}

    def test_stats_zero_before_call(self, fresh_home):
        svc = _mk_service()
        assert svc._floor_stats['emitted'] == 0

    def test_build_tools_integration(self, fresh_home):
        """build_tools(include_mcp=True) 经 tool_schemas 拿定义——楼层闸生效。"""
        from backend.api import Api
        api = Api()
        svc = api._mcp
        _seed_rt(svc, {'srv': [{'name': 't%d' % i, 'description': 'd' * 800}
                               for i in range(60)]})
        # list_servers 需 enabled——直接绕过：tool_schemas 读 _cfg.list_servers
        # 该用例只验 tool_schemas 层（api 层 enabled 过滤由契约测试覆盖）
        out = svc.tool_schemas()
        assert len(out) == 50
        assert svc._floor_stats['truncated_desc'] == 50
