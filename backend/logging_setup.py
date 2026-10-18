# -*- coding: utf-8 -*-
"""落盘日志（v1.0.0 零日志，生产问题不可诊断；重构补齐）。

- 入口调用 setup_logging()；测试不调用时 handler 为空，消息被 NullHandler 吸收
- 日志路径可通过参数重定向（测试隔离）
"""
import logging
import os
from logging.handlers import RotatingFileHandler

from . import paths

LOGGER_NAME = 'harbor'
LOG_FILE_NAME = 'harbor.log'
_FMT = '%(asctime)s %(levelname)s [%(threadName)s] %(message)s'


def setup_logging(log_dir=None, level=logging.INFO):
    logger = logging.getLogger(LOGGER_NAME)
    # 修复 S1：原 `if logger.handlers: return` 被模块级 NullHandler 恒真卡住，
    # RotatingFileHandler 永远不会挂上 → 落盘日志完全失效。
    # 已初始化判断限定文件 handler（NullHandler 不算已初始化）。
    # 修复 ⑥（三轮）：删冗余死分支——RotatingFileHandler 本就是 FileHandler 子类，
    # 第二个 isinstance 检查恒被第一个覆盖。
    if any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        return logger
    logger.setLevel(level)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    log_dir = log_dir or paths.LOG_DIR
    try:
        os.makedirs(log_dir, exist_ok=True)
        fh = RotatingFileHandler(os.path.join(log_dir, LOG_FILE_NAME),
                                 maxBytes=2 * 1024 * 1024, backupCount=3, encoding='utf-8')
        fh.setFormatter(logging.Formatter(_FMT))
        logger.addHandler(fh)
    except Exception:
        # 日志初始化失败不影响主流程
        pass
    return logger


def get_logger():
    return logging.getLogger(LOGGER_NAME)


# 导入即挂 NullHandler：未 setup_logging 时不向 stderr 喷消息（保留给调用方决定）
_logger = logging.getLogger(LOGGER_NAME)
if not _logger.handlers:
    _logger.addHandler(logging.NullHandler())
