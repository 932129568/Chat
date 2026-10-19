# -*- coding: utf-8 -*-
"""极简 CDP 客户端：连 Harbor 调试端口，读页面真实状态（readyState/异常/挂起）。
零依赖：手写 WebSocket 握手 + 帧解析（client→server 须掩码，server→client 不掩码）。"""
import ctypes, json, socket, struct, subprocess, sys, time, base64, os

PY = r'C:\Users\陈\.workbuddy\binaries\python\envs\default\Scripts\python.exe'
ROOT = r'C:\Users\陈\Desktop\GLM-Chat-v1.0.0-完整开发包'
PORT = 9222


def find_harbor():
    out = []
    user32 = ctypes.windll.user32
    @ctypes.WINFUNCTYPE(ctypes.c_void_p if False else ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, lp):
        pass
    return out


def http_get(path):
    s = socket.create_connection(('127.0.0.1', PORT), timeout=5)
    s.sendall(('GET %s HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n' % path).encode())
    buf = b''
    while True:
        d = s.recv(65536)
        if not d:
            break
        buf += d
    s.close()
    head, _, body = buf.partition(b'\r\n\r\n')
    return body.decode('utf-8', 'replace')


def ws_connect(url):
    # url 形如 ws://127.0.0.1:9222/devtools/page/XXXX
    u = url.split('://', 1)[1]
    hostport, _, path = u.partition('/')
    host, _, port = hostport.partition(':')
    s = socket.create_connection((host, int(port)), timeout=10)
    key = base64.b64encode(os.urandom(16)).decode()
    req = ('GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
           'Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n' % (path, hostport, key))
    s.sendall(req.encode())
    buf = b''
    while b'\r\n\r\n' not in buf:
        d = s.recv(4096)
        if not d:
            raise RuntimeError('WS 握手失败')
        buf += d
    return s


def ws_send(s, obj):
    data = json.dumps(obj).encode()
    header = bytearray([0x81])  # FIN + text
    mask = os.urandom(4)
    n = len(data)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126)
        header += struct.pack('>H', n)
    else:
        header.append(0x80 | 127)
        header += struct.pack('>Q', n)
    header += mask
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    s.sendall(bytes(header) + masked)


def ws_recv(s, timeout=8):
    s.settimeout(timeout)
    try:
        b0 = s.recv(1)
        if not b0:
            return None
        b1 = s.recv(1)
        n = b1[0] & 0x7F
        if n == 126:
            n = struct.unpack('>H', s.recv(2))[0]
        elif n == 127:
            n = struct.unpack('>Q', s.recv(8))[0]
        payload = b''
        while len(payload) < n:
            payload += s.recv(n - len(payload))
        return json.loads(payload.decode('utf-8', 'replace'))
    except socket.timeout:
        return None


def cdp_eval(ws, expr, mid):
    ws_send(ws, {'id': mid, 'method': 'Runtime.evaluate',
                 'params': {'expression': expr, 'returnByValue': True, 'awaitPromise': True}})
    while True:
        msg = ws_recv(ws)
        if msg is None:
            return {'error': 'timeout'}
        if msg.get('id') == mid:
            return msg


def main():
    env = dict(os.environ)
    env['GLM_CDP_PORT'] = str(PORT)
    env['WEBVIEW2_USER_DATA_FOLDER'] = r'C:\Users\陈\.workbuddy\test_webview_profile'  # 独立 profile 避锁
    p = subprocess.Popen([PY, 'main.py'], cwd=ROOT, env=env)
    time.sleep(12)  # 等窗口 + 页面加载
    try:
        pages = json.loads(http_get('/json/list'))
    except Exception as e:
        print('CDP 连接失败:', e)
        p.kill()
        return
    page = [x for x in pages if x.get('type') == 'page']
    if not page:
        print('无 page 目标:', pages)
        p.kill()
        return
    ws = ws_connect(page[0]['webSocketDebuggerUrl'])
    mid = [1]
    def ev(expr):
        mid[0] += 1
        r = cdp_eval(ws, expr, mid[0])
        res = r.get('result', {})
        if 'exceptionDetails' in r:
            return 'EXC: ' + json.dumps(r['exceptionDetails'].get('exception', {}))[:200]
        return res.get('result', {}).get('value', res)
    print('readyState:', ev('document.readyState'))
    print('body子元素数:', ev('document.body ? document.body.children.length : -1'))
    print('body HTML 长度:', ev('document.body ? document.body.innerHTML.length : -1'))
    print('body class:', ev('document.body ? document.body.className : "-"'))
    print('body bg 计算值:', ev('getComputedStyle(document.body).backgroundColor'))
    print('rail 存在:', ev('!!document.getElementById("rail")'))
    print('main 宽度:', ev('(()=>{const m=document.querySelector(".main");return m?Math.round(m.getBoundingClientRect().width):-1})()'))
    print('窗口宽:', ev('window.innerWidth'))
    print('boot 错误标记:', ev('window.__errs ? JSON.stringify(window.__errs) : "no-handler"'))
    print('当前 JS 是否卡死（发个微任务看回包）:', ev('Promise.resolve(42)'))
    # 收集一条控制台/异常（等 3 秒）
    print('--- 监听异常 3s ---')
    ws_send(ws, {'id': 99, 'method': 'Runtime.enable'})
    for _ in range(20):
        m = ws_recv(ws, timeout=1)
        if m and m.get('method') in ('Runtime.exceptionThrown', 'Runtime.consoleAPICalled'):
            print(json.dumps(m)[:400])
    p.kill()


if __name__ == '__main__':
    main()
