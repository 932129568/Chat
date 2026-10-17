# -*- coding: utf-8 -*-
"""IPC 返回协议（legacy main.py 中 31 处 json.dumps 的统一出口）。

legacy 的返回形态：json.dumps(payload, ensure_ascii=False)，
错误统一为 {'error': msg}。此处保持逐字节一致。
"""
import json


def ok(payload):
    """成功返回：payload 为 dict/list 等可 JSON 化对象。

    修复 W1：不可序列化对象（如 bytes/自定义类）原样穿透会在 js_api 桥炸掉
    返回协议；default=str 兜底降级为字符串，保证返回永远是合法 JSON。"""
    try:
        return json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps(payload, ensure_ascii=False, default=str)


def err(msg):
    """错误返回：{'error': msg}。"""
    return json.dumps({'error': str(msg)}, ensure_ascii=False)
