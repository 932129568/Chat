# -*- coding: utf-8 -*-
"""干净复测：独立 WebView2 profile + 正确点击 ☰（折叠侧栏），抓前后两帧。"""
import ctypes, os, subprocess, sys, time, zlib, struct
from ctypes import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
PY = r'C:\Users\陈\.workbuddy\binaries\python\envs\default\Scripts\python.exe'
ROOT = r'C:\Users\陈\Desktop\GLM-Chat-v1.0.0-完整开发包'
OUT = os.path.join(ROOT, 'outputs')
PROFILE = r'C:\Users\陈\.workbuddy\test_webview_profile'


def find_harbor():
    out = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if not n:
            return True
        b = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, b, n + 1)
        if 'Harbor' in b.value:
            out.append(hwnd)
        return True
    user32.EnumWindows(cb, 0)
    return out[0] if out else None


class BIH(ctypes.Structure):
    _fields_ = [('biSize', wintypes.DWORD), ('biWidth', wintypes.LONG), ('biHeight', wintypes.LONG),
                ('biPlanes', wintypes.WORD), ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
                ('biSizeImage', wintypes.DWORD), ('biXPelsPerMeter', wintypes.LONG), ('biYPelsPerMeter', wintypes.LONG),
                ('biClrUsed', wintypes.DWORD), ('biClrImportant', wintypes.DWORD)]


def save_png(path, w, h, pixels):
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    raw = b''.join(b'\x00' + pixels[y * w * 4:(y + 1) * w * 4] for y in range(h))
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(raw, 6))
    png += chunk(b'IEND', b'')
    open(path, 'wb').write(png)


def shoot(path):
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    hdc = user32.GetDC(None)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, sw, sh)
    gdi32.SelectObject(mdc, bmp)
    gdi32.BitBlt(mdc, 0, 0, sw, sh, hdc, 0, 0, 0x00CC0020)
    buf = ctypes.create_string_buffer(sw * sh * 4)
    bi = BIH()
    bi.biSize = 40; bi.biWidth = sw; bi.biHeight = -sh
    bi.biPlanes = 1; bi.biBitCount = 32; bi.biCompression = 0
    gdi32.GetDIBits(mdc, bmp, 0, sh, buf, ctypes.byref(bi), 0)
    save_png(path, sw, sh, buf.raw)
    gdi32.DeleteObject(bmp); gdi32.DeleteDC(mdc); user32.ReleaseDC(None, hdc)
    print('saved', path)


def main():
    env = dict(os.environ)
    env['WEBVIEW2_USER_DATA_FOLDER'] = PROFILE   # 独立 profile，避开运行中实例的目录锁
    p = subprocess.Popen([PY, 'main.py'], cwd=ROOT, env=env)
    hwnd = None
    for _ in range(60):
        time.sleep(0.5)
        hwnd = find_harbor()
        if hwnd:
            break
    if not hwnd:
        print('window not found'); p.kill(); sys.exit(1)
    time.sleep(8)
    shoot(os.path.join(OUT, 'fix_before.png'))
    # ☰ 按钮：client x = rail60 + mainNav132 + sidebar264 + header padding16 ≈ 472，按钮中心 ≈ 488
    pt = wintypes.POINT(488, 26)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.6)
    user32.SetCursorPos(pt.x, pt.y)
    time.sleep(0.3)
    user32.mouse_event(0x0002, pt.x, pt.y, 0, 0)   # LEFTDOWN
    time.sleep(0.05)
    user32.mouse_event(0x0004, pt.x, pt.y, 0, 0)   # LEFTUP
    time.sleep(2.5)                                 # 等 240ms 折叠过渡完成
    shoot(os.path.join(OUT, 'fix_after.png'))
    p.kill()
    print('done')


if __name__ == '__main__':
    main()
