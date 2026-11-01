#!/usr/bin/env python3
# 390px 手机端截图：harness iframe + 整页截图 + PIL 裁剪
import json, subprocess, time, sys, os, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GD = '/home/spark/.local/bin/geckodriver'
PORT = 4465
HTTP_PORT = 8124
BASE = f'http://127.0.0.1:{HTTP_PORT}'
for k in list(os.environ):
    if 'proxy' in k.lower() or 'PROXY' in k:
        del os.environ[k]

server = subprocess.Popen([sys.executable, '-m', 'http.server', str(HTTP_PORT), '-d', ROOT],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
gd = subprocess.Popen([GD, '--port', str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2)

def api(method, path, body=None):
    url = f'http://127.0.0.1:{PORT}{path}'
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data: req.add_header('Content-Type', 'application/json')
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try: return json.loads(op.open(req, timeout=120).read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except Exception: return {'error': f'HTTP {e.code}'}

import base64
try:
    sess = api('POST', '/session', {'capabilities': {'alwaysMatch': {
        'moz:firefoxOptions': {'args': ['-headless']}}}})
    sid = sess['value']['sessionId']
    api('POST', f'/session/{sid}/window/rect', {'width': 700, 'height': 1100})
    harness = os.path.join(HERE, 'harness.html')
    with open(harness, 'w', encoding='utf-8') as f:
        f.write('<!DOCTYPE html><html><body style="margin:0">\n'
                f'<iframe id="f" src="{BASE}/shdgjy.html" style="width:390px;height:844px;border:0"></iframe>\n'
                '</body></html>')
    api('POST', f'/session/{sid}/url', {'url': f'{BASE}/dev/harness.html'})
    time.sleep(2)

    def jsx(script):
        r = api('POST', f'/session/{sid}/execute/sync', {'script': script, 'args': []})
        if not isinstance(r, dict): return None
        v = r.get('value')
        if isinstance(v, dict) and 'error' in v: return None
        return v
    def save(path):
        r = api('GET', f'/session/{sid}/screenshot')
        assert isinstance(r.get('value'), str), r
        open(path, 'wb').write(base64.b64decode(r['value']))
    F = "var d=document.getElementById('f').contentWindow.document;"
    # 登录页
    save(os.path.join(HERE, 'shots', 'm-login.png'))
    # 登录管理员（harness 与页面同为 http 同源，可跨 iframe 操作）
    jsx(F + "d.getElementById('li-user').value='user';"
            "d.getElementById('li-pass').value='admin';"
            "d.getElementById('btn-login').click(); return null")
    t0 = time.time(); ok_login = False
    while time.time() - t0 < 25:
        time.sleep(0.25)
        v = jsx(F + "return !d.getElementById('view-admin').classList.contains('hidden')")
        if v is True: ok_login = True; break
    print('admin logged in:', ok_login)
    assert ok_login, 'iframe 内管理员登录失败'
    save(os.path.join(HERE, 'shots', 'm-admin.png'))
    print('OK shots saved')
finally:
    try: api('DELETE', f'/session/{sid}')
    except Exception: pass
    gd.terminate(); server.terminate()
