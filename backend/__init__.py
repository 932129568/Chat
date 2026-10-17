# -*- coding: utf-8 -*-
"""Harbor 后端包：分层架构（门面 + services + 基础设施）。

- api.py            对外契约层（pywebview js_api），零业务逻辑，纯委托
- services/         业务层，按域拆分，构造注入依赖
- paths.py          路径常量与 frozen 适配
- runtime.py        进程级可变状态（带锁）
- errors.py         IPC 返回协议
- logging_setup.py  落盘日志
- tools_schema.py   build_tools 唯一数据源
"""
