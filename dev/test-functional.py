#!/usr/bin/env python3
# shdgjy v0.4.x 全流程功能测试
# 架构：PHP 在线模式（php -S）+ 离线模式（python http.server，无 PHP → 降级）
# 覆盖：API 层、浏览器在线保存、跨设备数据一致性、改密轮换凭证、
#       离线降级生成文件、file:// 打开、390px 手机布局
import json, subprocess, time, sys, os, urllib.request, urllib.error, base64

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_FILE = os.path.join(ROOT, 'shdgjy-data.json')
GD = '/home/spark/.local/bin/geckodriver'
GPORT, PHP_PORT, PY_PORT = 4480, 8140, 8141
BASE_ON = f'http://127.0.0.1:{PHP_PORT}'    # 在线（PHP）
BASE_OFF = f'http://127.0.0.1:{PY_PORT}'    # 离线（无 PHP）
VERSION = 'v0.4.0'

for k in list(os.environ):
    if 'proxy' in k.lower() or 'PROXY' in k:
        del os.environ[k]

if os.path.exists(DATA_FILE):
    os.remove(DATA_FILE)

php = subprocess.Popen(['php', '-S', f'127.0.0.1:{PHP_PORT}', '-t', ROOT],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
pysrv = subprocess.Popen([sys.executable, '-m', 'http.server', str(PY_PORT), '-d', ROOT],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
gd = subprocess.Popen([GD, '--port', str(GPORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2)

PASS = FAIL = 0
def ok(name, cond, extra=''):
    global PASS, FAIL
    if cond: PASS += 1; print(f'  PASS {name}')
    else:    FAIL += 1; print(f'  FAIL {name}  {extra}')

def http(method, url, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data: req.add_header('Content-Type', 'application/json')
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        r = op.open(req, timeout=timeout)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except Exception: return e.code, None

def api(method, path, body=None):
    url = f'http://127.0.0.1:{GPORT}{path}'
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data: req.add_header('Content-Type', 'application/json')
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try: return json.loads(op.open(req, timeout=120).read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except Exception: return {'error': f'HTTP {e.code}'}

sid = None
def click(el_id):
    api('POST', f'/session/{sid}/execute/sync',
        {'script': f"document.getElementById('{el_id}').click(); return null", 'args': []})
def jsx(script):
    r = api('POST', f'/session/{sid}/execute/sync', {'script': script, 'args': []})
    if not isinstance(r, dict): return None
    v = r.get('value')
    if isinstance(v, dict) and 'error' in v: return None
    return v
def goto(url):
    api('POST', f'/session/{sid}/url', {'url': url})
    time.sleep(1.2)
def txt(el_id):
    return jsx(f"return document.getElementById('{el_id}').textContent") or ''
def set_input(el_id, value, ev='input'):
    return jsx(("var e=document.getElementById('%s'); e.value=%s; "
                "e.dispatchEvent(new Event('%s',{bubbles:true})); return e.value.length") % (el_id, json.dumps(value), ev))
def wait_login_result(timeout=25):
    t0 = time.time()
    while time.time() - t0 < timeout:
        err = txt('login-err')
        if err: return ('err:' + err, time.time() - t0)
        t = jsx("var e=document.getElementById('toast'); return e.classList.contains('show') ? e.textContent : ''")
        if t: return ('toast:' + t, time.time() - t0)
        v = jsx("return [!document.getElementById('view-user').classList.contains('hidden'),"
                "!document.getElementById('view-admin').classList.contains('hidden')]")
        if v and v[0]: return ('user', time.time() - t0)
        if v and v[1]: return ('admin', time.time() - t0)
        time.sleep(0.1)
    return ('timeout', timeout)
def do_login(u, p):
    t0 = time.time()
    while time.time() - t0 < 4.0:
        if jsx("return document.getElementById('toast').classList.contains('show')") is not True: break
        time.sleep(0.15)
    set_input('li-user', u)
    set_input('li-pass', p)
    click('btn-login')
    return wait_login_result()
def wait_conn(timeout=15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        c = jsx("return window.__t?window.__t.conn():null")
        if c and c.get('ready'): return c['mode']
        time.sleep(0.2)
    return None
def shot(name):
    r = api('GET', f'/session/{sid}/screenshot')
    if isinstance(r.get('value'), str):
        d = os.path.join(HERE, 'shots'); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, name), 'wb').write(base64.b64decode(r['value']))

try:
    sess = api('POST', '/session', {'capabilities': {'alwaysMatch': {
        'moz:firefoxOptions': {'args': ['-headless']}}}})
    sid = sess['value']['sessionId']
    api('POST', f'/session/{sid}/window/rect', {'width': 2560, 'height': 1440})
    time.sleep(0.5)

    # ============ 阶段 0：API 层（urllib 直测 PHP 接口）============
    print('== 阶段0：API 接口 ==')
    st, j = http('GET', f'{BASE_ON}/shdgjy-api.php')
    ok('Z1 初始 GET → nodata', st == 200 and j == {'ok': False, 'code': 'nodata'}, str(j))
    wk1 = 'a' * 64
    st, j = http('POST', f'{BASE_ON}/shdgjy-api.php', {'wk': wk1, 'd': {'fmt': 'H1', 'x': 1}})
    ok('Z2 首次 POST 初始化', st == 200 and j == {'ok': True}, str(j))
    st, j = http('GET', f'{BASE_ON}/shdgjy-api.php')
    ok('Z3 GET 返回初始化数据', st == 200 and j and j.get('ok') and j['data'] == {'fmt': 'H1', 'x': 1}, str(j)[:80])
    st, j = http('POST', f'{BASE_ON}/shdgjy-api.php', {'wk': 'b' * 64, 'd': {'fmt': 'H1', 'x': 2}})
    ok('Z4 错误凭证 → 403', st == 403 and j and j.get('code') == 'denied', str(j))
    st, j = http('POST', f'{BASE_ON}/shdgjy-api.php', {'wk': 'bad', 'd': {}})
    ok('Z5 坏格式 → 400', st == 400 and j and j.get('code') == 'badreq', str(j))
    st, j = http('POST', f'{BASE_ON}/shdgjy-api.php', {'wk': wk1, 'd': {'fmt': 'H1', 'x': 3}})
    ok('Z6 正确凭证更新', st == 200 and j == {'ok': True}, str(j))
    wk2 = '9' * 64
    st, j = http('POST', f'{BASE_ON}/shdgjy-api.php', {'wk': wk1, 'nw': wk2, 'd': {'fmt': 'H1', 'x': 4}})
    ok('Z9a 旧凭证+nw 切换成功', st == 200 and j == {'ok': True}, str(j))
    st, j = http('POST', f'{BASE_ON}/shdgjy-api.php', {'wk': wk1, 'd': {'fmt': 'H1', 'x': 5}})
    ok('Z9b 切换后旧凭证失效', st == 403 and j and j.get('code') == 'denied', str(j))
    st, j = http('POST', f'{BASE_ON}/shdgjy-api.php', {'wk': wk2, 'd': {'fmt': 'H1', 'x': 6}})
    ok('Z9c 新凭证生效', st == 200 and j == {'ok': True}, str(j))
    st, j = http('GET', f'{BASE_ON}/shdgjy-api.php')
    ok('Z9d 数据为最后一次写入', j and j.get('data') == {'fmt': 'H1', 'x': 6}, str(j)[:80])
    raw = open(DATA_FILE).read()
    ok('Z7 数据文件存凭证再哈希(不含wk原文)', '"w"' in raw and wk1 not in raw)
    st, j = http('GET', f'{BASE_ON}/shdgjy-data.json')
    ok('Z8 数据文件可直接GET(暴露面=密文,已文档化)', st == 200 and 'w' in (j or {}))
    os.remove(DATA_FILE)  # 回到干净初始态，浏览器流程从 empty 开始

    # ============ 阶段 A：在线模式（PHP）============
    print('== 阶段A：在线模式 ==')
    goto(f'{BASE_ON}/shdgjy.html')
    ok('A1 连接模式 empty(服务器无数据)', wait_conn() == 'empty')
    ok('A1 版本号', VERSION in (jsx("return document.body.textContent") or ''))
    ok('A1 应用无JS错误', jsx("return window.__t?window.__t.version:'undefined'") == '0.4.0')
    shot('a1-login.png')

    r, dt = do_login('chen1', 'wrongpass')
    ok('A2 失败浮窗文案', r == 'toast:❌核验未通过，请重试！', r)
    ok('A2 密码清空/用户名保留',
       jsx("return document.getElementById('li-pass').value") == '' and
       jsx("return document.getElementById('li-user').value") == 'chen1')
    time.sleep(2.3)
    ok('A2 浮窗2秒消失', jsx("return document.getElementById('toast').classList.contains('show')") is False)

    set_input('li-user', 'someuser')
    ok('A3 ×按钮显示', jsx("return document.getElementById('clear-user').classList.contains('show')") is True)
    click('clear-user'); time.sleep(0.2)
    ok('A3 ×清空并回焦', jsx("return document.getElementById('li-user').value") == '' and
       jsx("return document.activeElement.id") == 'li-user')

    r, _ = do_login('user', 'admin')
    ok('A4 管理员登录', r == 'admin')
    ok('A4 empty模式提示', '首次保存' in txt('sync-note'), txt('sync-note'))
    ok('A4 保存按钮文案', jsx("return document.getElementById('btn-save').textContent") == '保 存')

    click('btn-import')
    imp = "用户名,姓名,车牌号\nchen1,陈大山,沪A11111\nchen2,陈二水,沪B22222\nchen3,陈三石,皖C33333\nchen1,重复人,沪D99999\nbadline,缺列"
    set_input('imp-text', imp)
    click('btn-imp-ok'); time.sleep(0.3)
    ok('A5 导入后 3 人', txt('row-count') == '共 3 人', txt('row-count'))
    jsx("document.querySelectorAll('.modal.open').forEach(function(m){m.classList.remove('open')}); return null")

    click('btn-add')
    set_input('f-user', 'wangwu'); set_input('f-name', '王大力'); set_input('f-plate', '沪C33333')
    click('btn-edit-ok'); time.sleep(0.2)
    ok('A6 添加后 4 人', txt('row-count') == '共 4 人')

    jsx("var row=[].slice.call(document.querySelectorAll('#tbody tr')).filter(function(tr){return tr.cells[0].textContent==='chen1'})[0];"
        "if(row){row.querySelector('.row-btn').click()} return row?1:0")
    time.sleep(0.2)
    set_input('f-name', '陈大山峰'); set_input('f-plate', '沪A12345')
    click('btn-edit-ok'); time.sleep(0.2)
    ok('A7 编辑生效', '陈大山峰' in txt('tbody'))

    del2 = ("var row=[].slice.call(document.querySelectorAll('#tbody tr')).filter(function(tr){return tr.cells[0].textContent==='chen2'})[0];"
            "if(row){row.querySelector('.row-btn.del').click()} return row?1:0")
    jsx(del2); time.sleep(0.2)
    click('btn-confirm-ok'); time.sleep(0.2)
    ok('A8 删除后 3 人', txt('row-count') == '共 3 人', txt('row-count'))

    set_input('search-box', '沪A')
    ok('A9 搜索过滤', txt('row-count') == '匹配 1 / 3 人', txt('row-count'))
    set_input('search-box', '')
    ok('A9 dirty 提示', jsx("return document.getElementById('save-bar').classList.contains('show')"))

    click('btn-set')
    set_input('set-unified', 'shdgjy2026ok')
    click('btn-set-ok'); time.sleep(0.2)

    # 在线保存 → POST 到服务器
    click('btn-save')
    okd = False
    t0 = time.time()
    while time.time() - t0 < 30:
        if '已保存到服务器' in txt('toast'): okd = True; break
        time.sleep(0.2)
    ok('A10 在线保存成功提示', okd, txt('toast'))
    time.sleep(0.5)
    ok('A10 数据文件已生成', os.path.exists(DATA_FILE))
    st, j = http('GET', f'{BASE_ON}/shdgjy-api.php')
    ok('A10 服务器数据为密文格式', st == 200 and j and j.get('ok') and j['data'].get('fmt') == 'H1')
    ok('A10 dirty 清除+时间更新', jsx("return window.__t.state()").get('dirty') is False and
       '数据更新时间 20' in txt('data-time'), txt('data-time'))
    shot('a10-admin-online.png')

    # 跨设备一致性：刷新页面（模拟另一台设备），数据来自服务器
    goto(f'{BASE_ON}/shdgjy.html')
    ok('A11 刷新后连接 online', wait_conn() == 'online')
    r, _ = do_login('chen1', 'shdgjy2026ok')
    ok('A11 新设备普通用户登录(服务器数据)', r == 'user')
    ok('A11 核验信息正确', txt('u-name') == '陈大山峰' and txt('u-plate') == '沪A12345')
    shot('a11-user.png')
    click('btn-logout-u'); time.sleep(0.4)

    r, _ = do_login('chen1', '12345678')
    ok('A12 旧统一密码失效', r == 'toast:❌核验未通过，请重试！', r)
    time.sleep(2.2)

    # 改管理员密码 → 保存 → 凭证轮换
    r, _ = do_login('user', 'admin')
    ok('A13 管理员登录', r == 'admin')
    click('btn-set')
    set_input('set-admin-pass', 'newadmin77'); set_input('set-admin-pass2', 'newadmin77')
    click('btn-set-ok'); time.sleep(0.2)
    click('btn-save')
    okd = False
    t0 = time.time()
    while time.time() - t0 < 30:
        if '已保存到服务器' in txt('toast'): okd = True; break
        time.sleep(0.2)
    ok('A14 改密后保存成功', okd, txt('toast'))
    time.sleep(0.5)
    st, j = http('POST', f'{BASE_ON}/shdgjy-api.php', {'wk': 'c' * 64, 'd': {'fmt': 'H1'}})
    ok('A14 伪造凭证写入被拒', st == 403 and j and j.get('code') == 'denied', str(j))
    click('btn-logout-a'); time.sleep(0.5)
    r, _ = do_login('user', 'admin')
    ok('A15 旧管理员密码失效', r == 'toast:❌核验未通过，请重试！', r)
    time.sleep(2.2)
    r, _ = do_login('user', 'newadmin77')
    ok('A15 新管理员密码生效', r == 'admin')

    # ============ 阶段 B：离线降级（无 PHP 服务器）============
    print('== 阶段B：离线降级 ==')
    goto(f'{BASE_OFF}/shdgjy.html')
    ok('B1 连接模式 offline', wait_conn() == 'offline')
    r, _ = do_login('user', 'admin')
    ok('B2 离线用内嵌初始数据登录', r == 'admin', r)
    ok('B2 离线提示', '离线模式' in txt('sync-note'), txt('sync-note'))
    ok('B2 按钮文案', jsx("return document.getElementById('btn-save').textContent") == '保存并生成文件')
    click('btn-import')
    set_input('imp-text', 'litest,李测试,沪T00001')
    click('btn-imp-ok'); time.sleep(0.3)
    jsx("document.querySelectorAll('.modal.open').forEach(function(m){m.classList.remove('open')}); return null")
    click('btn-save')
    t0 = time.time()
    while time.time() - t0 < 20:
        if jsx("return document.getElementById('modal-export').classList.contains('open')"): break
        time.sleep(0.25)
    ok('B3 离线保存→导出弹窗', jsx("return document.getElementById('modal-export').classList.contains('open')"))
    exp = jsx("return window.__t.generateFile()")
    html = exp['html'] if isinstance(exp, dict) else ''
    ok('B3 生成文件完整', html.startswith('<!DOCTYPE html>') and html.rstrip().endswith('</html>'))
    ok('B3 无明文泄露', ('李测试' not in html) and ('litest' not in html))
    ok('B3 无会话残留', 'modal open' not in html and 'save-bar show' not in html)
    ok('B3 版本保留', VERSION in html)
    shot('b3-offline-export.png')

    # ============ 阶段 C：file:// 直开 ============
    print('== 阶段C：file:// 离线打开 ==')
    goto('file://' + os.path.join(ROOT, 'shdgjy.html'))
    ok('C1 file:// 连接 offline', wait_conn() == 'offline')
    r, _ = do_login('user', 'admin')
    ok('C1 file:// 管理员可登录', r == 'admin', r)

    # ============ 阶段 D：390px 手机 ============
    print('== 阶段D：390px ==')
    harness = os.path.join(HERE, 'harness.html')
    with open(harness, 'w', encoding='utf-8') as f:
        f.write(f'<!DOCTYPE html><html><body style="margin:0">\n'
                f'<iframe id="f" src="{BASE_ON}/shdgjy.html" style="width:390px;height:844px;border:0"></iframe>\n'
                '</body></html>')
    goto(f'{BASE_ON}/dev/harness.html')
    time.sleep(1.5)
    m = jsx("var d=document.getElementById('f').contentWindow.document;"
            "var r=[d.getElementById('li-user'),d.getElementById('btn-login')].map(function(e){var b=e.getBoundingClientRect();return [Math.round(b.left),Math.round(b.right),Math.round(b.width)]});"
            "return r")
    ok('D1 登录框适配390px', m and all(row[1] <= 391 for row in m) and m[0][2] > 200, str(m))

finally:
    print(f'\n结果: {PASS} 通过, {FAIL} 失败')
    try:
        if sid: api('DELETE', f'/session/{sid}')
    except Exception: pass
    for p in (gd, php, pysrv):
        p.terminate()
    sys.exit(1 if FAIL else 0)
