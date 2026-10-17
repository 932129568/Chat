# -*- coding: utf-8 -*-
"""原子写工具（修复 S8）：tmp + fsync + os.replace。

config.json / sessions.json / memory.json / guard.json / session_ws.json 等
原来都是 open('w') 截断式直写，写一半断电即半截 JSON、配置全丢。
统一走本模块：先写同目录临时文件再原子替换，崩溃最坏留 .tmp 不毁原文件。
"""
import json
import os
import tempfile


def _replace_with_retry(tmp, path, retries=5):
    """修复 W2（二轮）：Windows 下 os.replace 对「正被读取/杀软扫描中的目标文件」
    会抛 WinError 32——退避重试 5 次（原一次失败即保存失败）。"""
    import time
    last = None
    for i in range(retries):
        try:
            os.replace(tmp, path)
            # 修复 建议①（二轮）：目录项 fsync——文件 fsync 不保证目录项持久，
            # 掉电时可能丢替换结果（tmp 在、目标仍是旧内容）
            try:
                dfd = os.open(os.path.dirname(os.path.abspath(path)), os.O_RDONLY)
                try:
                    os.fsync(dfd)
                finally:
                    os.close(dfd)
            except Exception:
                pass
            return
        except PermissionError as e:      # WinError 32 共享冲突
            last = e
            time.sleep(0.05 * (i + 1))
    raise last


def cleanup_stale_tmps(dirs, prefix='.glm_tmp_'):
    """修复 建议①（二轮）：清理历史遗留的原子写临时文件（崩溃未来得及替换的）。
    仅清本进程创建风格的前缀文件，返回清理数量。"""
    cleaned = 0
    for d in dirs:
        try:
            if not os.path.isdir(d):
                continue
            for fn in os.listdir(d):
                if fn.startswith(prefix):
                    try:
                        os.remove(os.path.join(d, fn))
                        cleaned += 1
                    except Exception:
                        pass
        except Exception:
            pass
    return cleaned


def atomic_write_text(path, text, encoding='utf-8', newline=''):
    """同目录 tmp + fsync + os.replace（带 WinError32 退避重试）原子写入文本。"""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.glm_tmp_', dir=d)
    try:
        # 修复 建议②（二轮）：os.fdopen 自身抛错时 fd 泄漏——先包一层兜底 close
        try:
            f = os.fdopen(fd, 'w', encoding=encoding, newline=newline)
        except Exception:
            os.close(fd)
            raise
        with f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        _replace_with_retry(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise


def atomic_write_json(path, obj, indent=None):
    """json.dumps + 原子写（序列化参数与既有 json.dump 调用保持一致）。"""
    text = json.dumps(obj, ensure_ascii=False, indent=indent)
    atomic_write_text(path, text)


def atomic_write_text_mode(path, text, encoding, errors='replace'):
    """文本模式原子写：tmp + fsync + os.replace（带 WinError32 退避重试），换行翻译
    （newline=None，\n→os.linesep）与 legacy `open(path, 'w', encoding=...)` 逐字节一致——
    search_replace 写回专用，保契约差分零漂移（legacy 写回带平台换行翻译是钉死行为）。"""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.glm_tmp_', dir=d)
    try:
        try:
            f = os.fdopen(fd, 'w', encoding=encoding, errors=errors)
        except Exception:
            os.close(fd)
            raise
        with f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        _replace_with_retry(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise
