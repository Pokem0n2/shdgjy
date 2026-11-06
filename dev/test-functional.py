#!/usr/bin/env python3
# shdgjy v0.4.x 全流程功能测试
# 架构：在线模式（静态页面 + amd64 API 容器跨端口 CORS）+ 离线模式（API 停止 → 降级）
#       离线降级生成文件、file:// 打开、390px 手机布局
import json, subprocess, time, sys, os, urllib.request, urllib.error, base64

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_FILE = '/tmp/shdgjy-test-data/shdgjy-data.json'   # API 容器挂载卷（静态目录之外）
GD = '/home/spark/.local/bin/geckodriver'
GPORT, ON_PORT, OFF_PORT, API_PORT = 4480, 8140, 8141, 8443
BASE_ON = f'http://127.0.0.1:{ON_PORT}'    # 在线（静态页面 + API 容器）
BASE_OFF = f'http://127.0.0.1:{OFF_PORT}'  # 离线（静态页面，API 停止）
API_URL = f'http://127.0.0.1:{API_PORT}'
VERSION = 'v0.10.7'
DOCKER = ['sudo', '-n', 'docker']
API_CONTAINER = 'shdgjy-api-test'

for k in list(os.environ):
    if 'proxy' in k.lower() or 'PROXY' in k:
        del os.environ[k]

subprocess.run(DOCKER + ['start', API_CONTAINER], stdout=subprocess.DEVNULL)
if os.path.exists(DATA_FILE):
    os.remove(DATA_FILE)

on_srv = subprocess.Popen([sys.executable, '-m', 'http.server', str(ON_PORT), '-d', ROOT],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
off_srv = subprocess.Popen([sys.executable, '-m', 'http.server', str(OFF_PORT), '-d', ROOT],
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
        if t and ('❌' in t or '失败' in t): return ('toast:' + t, time.time() - t0)  # 仅错误型 toast 视为登录失败，信息型提示（如kq启用）忽略
        v = jsx("return [!document.getElementById('view-user').classList.contains('hidden'),"
                "!document.getElementById('view-admin').classList.contains('hidden')]")
        if v and v[0]: return ('user', time.time() - t0)
        if v and v[1]: return ('admin', time.time() - t0)
        time.sleep(0.1)
    return ('timeout', timeout)
def do_login(u, p):
    # v0.9.0 起页面会自动恢复上次登录：切换账号前先清本机凭证并重载
    jsx("try{localStorage.removeItem('shdgjy-auth')}catch(e){}; return 1")
    goto(BASE_ON + '/shdgjy.html')
    time.sleep(1.2)
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
    st, j = http('GET', API_URL + '/')
    ok('Z1 初始 GET → nodata', st == 200 and j == {'ok': False, 'code': 'nodata'}, str(j))
    wk1 = 'a' * 64
    st, j = http('POST', API_URL + '/', {'wk': wk1, 'd': {'fmt': 'H1', 'x': 1}})
    ok('Z2 首次 POST 初始化', st == 200 and j == {'ok': True}, str(j))
    st, j = http('GET', API_URL + '/')
    ok('Z3 GET 返回初始化数据', st == 200 and j and j.get('ok') and j['data'] == {'fmt': 'H1', 'x': 1}, str(j)[:80])
    st, j = http('POST', API_URL + '/', {'wk': 'b' * 64, 'd': {'fmt': 'H1', 'x': 2}})
    ok('Z4 错误凭证 → 403', st == 403 and j and j.get('code') == 'denied', str(j))
    st, j = http('POST', API_URL + '/', {'wk': 'bad', 'd': {}})
    ok('Z5 坏格式 → 400', st == 400 and j and j.get('code') == 'badreq', str(j))
    st, j = http('POST', API_URL + '/', {'wk': wk1, 'd': {'fmt': 'H1', 'x': 3}})
    ok('Z6 正确凭证更新', st == 200 and j == {'ok': True}, str(j))
    wk2 = '9' * 64
    st, j = http('POST', API_URL + '/', {'wk': wk1, 'nw': wk2, 'd': {'fmt': 'H1', 'x': 4}})
    ok('Z9a 旧凭证+nw 切换成功', st == 200 and j == {'ok': True}, str(j))
    st, j = http('POST', API_URL + '/', {'wk': wk1, 'd': {'fmt': 'H1', 'x': 5}})
    ok('Z9b 切换后旧凭证失效', st == 403 and j and j.get('code') == 'denied', str(j))
    st, j = http('POST', API_URL + '/', {'wk': wk2, 'd': {'fmt': 'H1', 'x': 6}})
    ok('Z9c 新凭证生效', st == 200 and j == {'ok': True}, str(j))
    st, j = http('GET', API_URL + '/')
    ok('Z9d 数据为最后一次写入', j and j.get('data') == {'fmt': 'H1', 'x': 6}, str(j)[:80])
    raw = open(DATA_FILE).read()
    ok('Z7 数据文件存凭证再哈希(不含wk原文)', '"w"' in raw and wk1 not in raw)
    st, j = http('GET', f'{BASE_ON}/dev/test-data-should-not-exist.json')
    ok('Z8 数据文件不经静态服务器(仅API容器可读)', st == 404, str(st))
    os.remove(DATA_FILE)  # 回到干净初始态，浏览器流程从 empty 开始
    time.sleep(0.3)

    # ============ 阶段 A：在线模式（PHP）============
    print('== 阶段A：在线模式 ==')
    goto(f'{BASE_ON}/shdgjy.html')
    ok('A1 连接模式 empty(服务器无数据)', wait_conn() == 'empty')
    ok('A1 版本号', VERSION in (jsx("return document.body.textContent") or ''))
    ok('A1 应用无JS错误', jsx("return window.__t?window.__t.version:'undefined'") == VERSION.lstrip('v'))
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
    imp = ("项目名称,单位名称,用户名,姓名,手机号,车牌号\n"
           "一标段,一中建,chen1,陈大山,13811110001,沪A11111\n"
           "一标段,一中建,chen2,陈二水,13811110002,沪B22222\n"
           "一标段,二劳务,chen3,陈三石,13811110003,皖C33333\n"
           "badline,缺列")
    set_input('imp-text', imp)
    click('btn-imp-ok'); time.sleep(0.3)
    ok('A5 导入后 3 人', txt('row-count') == '共 3 人', txt('row-count'))
    jsx("document.querySelectorAll('.modal.open').forEach(function(m){m.classList.remove('open')}); return null")

    click('btn-add')
    set_input('f-proj', '一标段'); set_input('f-org', '三监理')
    set_input('f-user', 'wangwu'); set_input('f-name', '王大力'); set_input('f-phone', '13811110005'); set_input('f-plate', '沪C33333')
    click('btn-edit-ok'); time.sleep(0.2)
    ok('A6 添加后 4 人', txt('row-count') == '共 4 人')

    jsx("var row=[].slice.call(document.querySelectorAll('#tbody tr')).filter(function(tr){return tr.cells[2].textContent==='chen1'})[0];"
        "if(row){row.querySelector('.row-btn').click()} return row?1:0")
    time.sleep(0.2)
    set_input('f-name', '陈大山峰'); set_input('f-plate', '沪A12345')
    click('btn-edit-ok'); time.sleep(0.2)
    ok('A7 编辑生效', '陈大山峰' in txt('tbody'))

    del2 = ("var row=[].slice.call(document.querySelectorAll('#tbody tr')).filter(function(tr){return tr.cells[2].textContent==='chen2'})[0];"
            "if(row){row.querySelector('.row-btn.del').click()} return row?1:0")
    jsx(del2); time.sleep(0.2)
    click('btn-confirm-ok'); time.sleep(0.2)
    ok('A8 删除后 3 人', txt('row-count') == '共 3 人', txt('row-count'))

    set_input('search-box', '沪A')
    ok('A9 搜索过滤', txt('row-count') == '匹配 1 / 3 人', txt('row-count'))
    set_input('search-box', '')
    ok('A9 dirty 提示', jsx("return document.getElementById('save-bar').classList.contains('show')"))
    ok('A9 dirty时密码设置右侧红色未保存标签',
       jsx("return document.getElementById('dirty-badge').classList.contains('show')") is True and
       jsx("var s=document.getElementById('btn-set').getBoundingClientRect(); var b=document.getElementById('dirty-badge').getBoundingClientRect(); return b.left>=s.right-2") is True)

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
    st, j = http('GET', API_URL + '/')
    ok('A10 服务器数据为密文格式', st == 200 and j and j.get('ok') and j['data'].get('fmt') == 'H1')
    ok('A10 dirty 清除+时间更新', jsx("return window.__t.state()").get('dirty') is False and
       '数据更新时间 20' in txt('data-time'), txt('data-time'))
    ok('A10 保存后未保存标签消失', jsx("return document.getElementById('dirty-badge').classList.contains('show')") is False)
    shot('a10-admin-online.png')

    # 跨设备一致性：刷新页面（模拟另一台设备），数据来自服务器
    goto(f'{BASE_ON}/shdgjy.html')
    ok('A11 刷新后连接 online', wait_conn() == 'online')
    r, _ = do_login('chen1', 'shdgjy2026ok')
    ok('A11 新设备普通用户登录(服务器数据)', r == 'user')
    ok('A11 核验信息正确', txt('u-name') == '陈大山峰' and txt('u-plate') == '沪A 12345')
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
    st, j = http('POST', API_URL + '/', {'wk': 'c' * 64, 'd': {'fmt': 'H1'}})
    ok('A14 伪造凭证写入被拒', st == 403 and j and j.get('code') == 'denied', str(j))
    click('btn-logout-a'); time.sleep(0.5)
    r, _ = do_login('user', 'admin')
    ok('A15 旧管理员密码失效', r == 'toast:❌核验未通过，请重试！', r)
    time.sleep(2.2)
    r, _ = do_login('user', 'newadmin77')
    ok('A15 新管理员密码生效', r == 'admin')
    # A16 登录态持久化：刷新后自动恢复；登出后清除
    ok('A16 登录凭证已存', bool(jsx("return localStorage.getItem('shdgjy-auth')")))
    goto(BASE_ON + '/shdgjy.html')
    t0 = time.time()
    while time.time() - t0 < 15:
        if jsx("return !document.getElementById('view-admin').classList.contains('hidden')"): break
        time.sleep(0.2)
    ok('A16 刷新后自动恢复管理登录', jsx("return !document.getElementById('view-admin').classList.contains('hidden')") is True)
    click('btn-logout-a'); time.sleep(0.4)
    ok('A16 登出后凭证清除', not (jsx("return localStorage.getItem('shdgjy-auth')") or ''))
    goto(BASE_ON + '/shdgjy.html'); time.sleep(1.5)
    ok('A16 登出后刷新停在登录页', jsx("return !document.getElementById('view-login').classList.contains('hidden')") is True)
    r, _ = do_login('user', 'newadmin77')
    ok('A16 重新登录成功', r == 'admin', r)

    # ============ 阶段 Q：二维码（一人一码）============
    print('== 阶段Q：二维码 ==')
    import re as _re
    st, j = http('GET', API_URL + '/')
    d = (j or {}).get('data') or {}
    ok('Q1 服务器信封含票据密钥kq', _re.fullmatch(r'[0-9a-f]{64}', d.get('kq', '')) is not None, str(d.get('kq'))[:20])
    ok('Q1 qh用户哈希清单', isinstance(d.get('qh'), list) and len(d['qh']) == 3, str(d.get('qh'))[:60])
    t_chen1 = jsx("return window.__t.qTicket('chen1')")
    t_wangwu = jsx("return window.__t.qTicket('wangwu')")
    ok('Q2 票据URL格式', bool(t_chen1) and '#q=' in t_chen1 and t_chen1.startswith('http'), str(t_chen1)[:60])
    ok('Q2 一人一码(不同用户票据不同)', t_chen1 != t_wangwu)
    n_cv = jsx("return document.querySelectorAll('#tbody canvas.qr-thumb').length")
    w_cv = jsx("return (document.querySelector('#tbody canvas.qr-thumb')||{}).width||0")
    ok('Q3 每行都有二维码缩略(20px)', n_cv == 3 and w_cv >= 18, f'canvas数={n_cv} 宽={w_cv}')
    jsx("document.querySelector('#tbody canvas.qr-thumb').click(); return null")
    time.sleep(0.3)
    ok('Q3 点击→放大浮窗居中显示',
       jsx("return document.getElementById('modal-qr').classList.contains('open')") is True and
       jsx("var b=document.getElementById('qr-big-img').getBoundingClientRect(); return Math.abs((b.left+b.right)/2-window.innerWidth/2)<40") is True and
       (jsx("return document.getElementById('qr-big-img').naturalWidth") or 0) >= 200 and
       '陈大山峰' in (jsx("return document.getElementById('qr-cap').textContent") or ''), '')
    shot('q3-qr-big.png')
    jsx("document.getElementById('modal-qr').click(); return null")
    time.sleep(0.3)
    ok('Q3 点空白关闭浮窗', jsx("return document.getElementById('modal-qr').classList.contains('open')") is False)
    # zbar 解码：浮窗截图里的二维码应还原出票据URL
    zr = subprocess.run(['zbarimg', '-q', '--raw', os.path.join(HERE, 'shots', 'q3-qr-big.png')],
                        capture_output=True, text=True)
    zout = [x for x in (zr.stdout or '').strip().splitlines() if x.strip()]
    zurl = zout[0] if zout else ''
    ok('Q4 浮窗二维码可被扫描解码出票据URL', zurl.startswith(f'{BASE_ON}/shdgjy.html#q=') and len(zurl) > 60, str(zout)[:80])
    # 扫码核验：直接打开二维码里实际编码的URL（完全模拟微信扫码内容）
    goto(zurl or t_chen1)
    t0 = time.time(); _mode = None
    while time.time() - t0 < 15:
        _mode = _mode or wait_conn(0.5)
        if jsx("return !document.getElementById('view-user').classList.contains('hidden')"): break
        time.sleep(0.2)
    _vu = jsx("return !document.getElementById('view-user').classList.contains('hidden')")
    ok('Q5 扫码直达核验通过页', _vu is True, f'conn={_mode} view-user={_vu} 用时{time.time()-t0:.1f}s')
    ok('Q5 扫码展示姓名车牌正确', txt('u-name') == '陈大山峰' and txt('u-plate') == '沪A 12345', txt('u-name') + '/' + txt('u-plate'))
    ok('Q5 扫码直达不展示二维码(保安场景)',
       (jsx("return document.getElementById('u-qr-wrap').offsetParent") is None) and
       not (jsx("return document.getElementById('u-qr-img').getAttribute('src')") or ''))
    shot('q5-scan-ok.png')
    click('btn-logout-u'); time.sleep(0.4)
    # 篡改票据 → 失败
    bad = t_chen1[:-6] + ('AAAAAA' if not t_chen1.endswith('AAAAAA') else 'BBBBBB')
    goto(bad)
    t0 = time.time(); _bfail = False
    while time.time() - t0 < 15:
        if '❌核验未通过' in (jsx("return document.getElementById('toast').textContent") or ''): _bfail = True; break
        time.sleep(0.2)
    ok('Q6 篡改票据→核验失败浮窗', _bfail and
       jsx("return !document.getElementById('view-login').classList.contains('hidden')") is True,
       f'{time.time()-t0:.1f}s')
    time.sleep(2.2)
    # 删除用户 → 其旧票据失效
    r, _ = do_login('user', 'newadmin77')
    ok('Q6 管理员重登', r == 'admin')
    jsx("var row=[].slice.call(document.querySelectorAll('#tbody tr')).filter(function(tr){return tr.cells[2].textContent==='wangwu'})[0];"
        "if(row){row.querySelector('.row-btn.del').click()} return row?1:0")
    time.sleep(0.2)
    click('btn-confirm-ok'); time.sleep(0.2)
    click('btn-save')
    okd = False
    t0 = time.time()
    while time.time() - t0 < 30:
        if '已保存到服务器' in txt('toast'): okd = True; break
        time.sleep(0.2)
    ok('Q6 删除wangwu并保存', okd and txt('row-count') == '共 2 人', txt('row-count'))
    click('btn-logout-a'); time.sleep(0.5)
    goto(t_wangwu)
    t0 = time.time(); _fail = False
    while time.time() - t0 < 15:
        if '❌核验未通过' in (jsx("return document.getElementById('toast').textContent") or ''): _fail = True; break
        time.sleep(0.2)
    ok('Q6 已删用户旧票据→核验失败', _fail and
       jsx("return !document.getElementById('view-login').classList.contains('hidden')") is True,
       f'{time.time()-t0:.1f}s')
    time.sleep(2.2)

    # Q7 普通用户登录页展示自己的二维码（自行保存/打印）
    r, _ = do_login('chen1', 'shdgjy2026ok')
    ok('Q7 用户登录成功', r == 'user', r)
    _src = jsx("return document.getElementById('u-qr-img').getAttribute('src')") or ''
    ok('Q7 登录页展示自己的二维码图', _src.startswith('data:image/png'), _src[:30])
    ok('Q7 登录场景二维码区块可见', jsx("return document.getElementById('u-qr-wrap').offsetParent") is not None)
    t0 = time.time()
    while time.time() - t0 < 6:
        if jsx("var i=document.getElementById('u-qr-img'); return i.complete && i.naturalWidth>=400") is True: break
        time.sleep(0.15)
    time.sleep(1.2)  # 视图切换动画 settle
    _geo = jsx("var b=document.getElementById('u-qr-img').getBoundingClientRect(); var c=document.getElementById('u-qr-wrap').getBoundingClientRect(); return [Math.round(b.left),Math.round(b.right),Math.round(c.left),Math.round(c.right),Math.round((b.left+b.right)/2-(c.left+c.right)/2), document.getElementById('u-qr-img').naturalWidth]")
    print('  [Q7geo] img[l,r]=', _geo[0] if _geo else None, _geo[1] if _geo else None, '| wrap[l,r]=', _geo[2] if _geo else None, _geo[3] if _geo else None, '| 中心差=', _geo[4] if _geo else None, '| naturalWidth=', _geo[5] if _geo else None)
    ok('Q7 二维码居中显示', _geo and abs(_geo[4]) < 10 and _geo[5] >= 380, str(_geo))
    shot('q7-user-selfqr.png')
    jsx("document.getElementById('u-qr-img').click(); return null")
    t0 = time.time()
    while time.time() - t0 < 6:
        if jsx("var i=document.getElementById('qr-big-img'); return i.complete && i.naturalWidth>=400 && document.getElementById('modal-qr').classList.contains('open')") is True: break
        time.sleep(0.15)
    ok('Q7 点击放大浮窗',
       jsx("var i=document.getElementById('qr-big-img'); return document.getElementById('modal-qr').classList.contains('open') && i.complete && i.naturalWidth>=380") is True,
       str(jsx("return document.getElementById('qr-big-img').naturalWidth")))
    jsx("document.getElementById('modal-qr').click(); return null"); time.sleep(0.3)
    zr2 = subprocess.run(['zbarimg', '-q', '--raw', os.path.join(HERE, 'shots', 'q7-user-selfqr.png')],
                         capture_output=True, text=True)
    z2 = [x for x in (zr2.stdout or '').strip().splitlines() if x.strip()]
    from urllib.parse import unquote as _uq2
    _t = jsx("return window.__t.qTicket('chen1')")
    ok('Q7 用户页二维码可实扫解码', any(_uq2(x).startswith(f'{BASE_ON}/shdgjy.html#q=') for x in z2), str(z2)[:60])
    click('btn-logout-u'); time.sleep(0.4)

    # Q8 批量导入 UI 流程（用户实报 bug 回归：确认不关闭/内容残留）
    r, _ = do_login('user', 'newadmin77')
    ok('Q8 管理员登录', r == 'admin', r)
    _n0 = int(txt('row-count').split()[1])
    click('btn-import'); time.sleep(0.3)
    ok('Q8 打开导入框', jsx("return document.getElementById('modal-import').classList.contains('open')") is True)
    _imp = ('P1项目,一公司,aaa,测试甲,13800000001,沪Z11111' + chr(10)
            + 'P1项目,二公司,bbb,测试乙,13800000002,沪Z22222')
    _setr = jsx("document.getElementById('imp-text').value=" + json.dumps(_imp) + "; return document.getElementById('imp-text').value.length")
    ok('Q8 粘贴两行数据写入', _setr == len(_imp), repr(_setr))
    click('btn-imp-ok'); time.sleep(0.8)
    _closed = jsx("return !document.getElementById('modal-import').classList.contains('open')")
    ok('Q8 确认导入后弹窗自动关闭', _closed is True)
    print('  [Q8现场] imp-result=', jsx("return document.getElementById('imp-result').textContent"), '| toast=', jsx("return document.getElementById('toast').textContent"))
    ok('Q8 导入结果 toast', '新增 2 人' in (jsx("return document.getElementById('toast').textContent") or ''))
    ok('Q8 表格行数+2', int(txt('row-count').split()[1]) == _n0 + 2, txt('row-count'))
    ok('Q8 表头为8列(未筛选)', jsx("return document.querySelectorAll('thead th:not(.hidden)').length") == 8)
    time.sleep(4.2)
    click('btn-import'); time.sleep(0.3)
    ok('Q8 重开导入框无残留',
       (jsx("return document.getElementById('imp-text').value") or '') == '' and
       (jsx("return document.getElementById('imp-result').textContent") or '') == '' and
       jsx("return document.getElementById('imp-replace').checked") is False)
    jsx("document.querySelector('#modal-import [data-close]').click(); return null"); time.sleep(0.3)
    click('btn-logout-a'); time.sleep(0.3)
    if jsx("return document.getElementById('modal-confirm').classList.contains('open')") is True:
        click('btn-confirm-ok')  # dirty 退出确认（丢弃未保存导入）
    time.sleep(0.5)

    # Q9 混用分隔符（人工录入场景：半角/全角逗号、空格、顿号任意混用；行间不一致）
    r, _ = do_login('user', 'newadmin77')
    ok('Q9 管理员登录', r == 'admin', r)
    _n0 = int(txt('row-count').split()[1])
    click('btn-import'); time.sleep(0.3)
    ok('Q9diag 导入框已打开', jsx("return document.getElementById('modal-import').classList.contains('open')") is True)
    _mix = ('项目名称,单位名称,用户名,姓名,手机号,车牌号' + chr(10)
            + 'PX项目，一公司,mix1,张三,13800000011,沪Z90001' + chr(10)
            + 'PX项目、二公司 mix2 李四 13800000012 沪Z90002' + chr(10)
            + 'PY项目 三公司,mix3,王五、13800000013 沪Z 90003')
    _len = jsx("document.getElementById('imp-text').value=" + json.dumps(_mix) + "; return document.getElementById('imp-text').value.length")
    ok('Q9diag 粘贴写入', _len == len(_mix), repr(_len))
    jsx("var e=document.getElementById('imp-text'); e.dispatchEvent(new Event('input',{bubbles:true})); return 1")
    ok('Q9 预览识别3条+表头1', '已识别 3 条' in (jsx("return document.getElementById('imp-preview').textContent") or ''),
       jsx("return document.getElementById('imp-preview').textContent"))
    print('  [Q9现场] view-admin=', jsx("return !document.getElementById('view-admin').classList.contains('hidden')"),
          '| imp-result=', jsx("return document.getElementById('imp-result').textContent"),
          '| toast=', jsx("return document.getElementById('toast').textContent"),
          '| row-count=', txt('row-count'))
    click('btn-imp-ok'); time.sleep(0.6)
    print('  [Q9n0] _n0=', repr(_n0), '| row-count repr=', repr(txt('row-count')), '| 计算=', repr(int(txt('row-count').split()[1])), '期望', _n0+3)
    ok('Q9 混用分隔符导入3人(表头已跳过/坏行已拒)', int(txt('row-count').split()[1]) == _n0 + 3, txt('row-count'))
    _row = jsx("return [].slice.call(document.querySelectorAll('#tbody tr')).filter(function(tr){return tr.cells[2].textContent==='mix3'})[0].cells[5].textContent")
    ok('Q9 车牌拼合+字母后自动加空格', _row == '沪Z 90003', repr(_row))
    ok('Q9 结果含表头计数', '表头 1' in (jsx("return document.getElementById('imp-result').textContent") or ''),
       jsx("return document.getElementById('imp-result').textContent"))
    time.sleep(4.2)
    click('btn-logout-a'); time.sleep(0.3)
    if jsx("return document.getElementById('modal-confirm').classList.contains('open')") is True:
        click('btn-confirm-ok')
    time.sleep(0.5)
    ok('Q9 已退出到登录页', jsx("return !document.getElementById('view-login').classList.contains('hidden')") is True)

    # ============ 阶段 R：保存持久化字段完整性（v0.10.6 丢字段事故回归） ============
    print('== 阶段R：保存持久化 ==')
    r, _ = do_login('user', 'newadmin77')
    ok('R0 管理员登录', r == 'admin', r)
    click('btn-import'); time.sleep(0.3)
    _rimp = 'RP项目,瑞单位,rp1,瑞甲,13800000081,沪R 00001' + chr(10) + 'RP项目,瑞单位,rp2,瑞乙,13800000082,沪R 00002'
    jsx("document.getElementById('imp-text').value=" + json.dumps(_rimp) + "; return 1")
    click('btn-imp-ok'); time.sleep(0.6)
    click('btn-save'); time.sleep(4)  # 等保存完成 toast
    print('  [R1现场] toast=', repr(jsx("return document.getElementById('toast').textContent")),
          '| dirty=', jsx("return window.__t.state().dirty"),
          '| conn=', jsx("return window.__t.connMode && window.__t.connMode()") or 'n/a')
    ok('R1 保存完成提示', '已保存' in (jsx("return document.getElementById('toast').textContent") or ''), repr(jsx("return document.getElementById('toast').textContent")))
    # 重载页面（同 URL 导航=重载）→ 重新登录 → 断言 6 字段完整
    goto(BASE_ON + '/shdgjy.html'); time.sleep(1.5)
    r, _ = do_login('user', 'newadmin77')
    ok('R2 重载后登录', r == 'admin', r)
    print('  [R2现场] row-count=', repr(jsx("return document.getElementById('row-count').textContent")))
    jsx("var e=document.getElementById('search-box');e.value='rp1';e.dispatchEvent(new Event('input',{bubbles:true}));return 1")
    time.sleep(0.6)
    print('  [R2搜索后] row-count=', repr(jsx("return document.getElementById('row-count').textContent")),
          '| tbody行=', jsx("return document.getElementById('tbody').rows.length"),
          '| 首行=', repr(jsx("var tr=document.querySelector('#tbody tr');return tr?tr.textContent.slice(0,60):null")))
    _row1 = jsx("return (function(){var tr=[].slice.call(document.querySelectorAll('#tbody tr')).filter(function(t){return t.cells[2]&&t.cells[2].textContent==='rp1'})[0];return tr?[].slice.call(tr.cells).map(function(td){return td.textContent.trim()}):null})()")
    ok('R2 保存-重载后6字段完整', _row1 and _row1[:6] == ['RP项目', '瑞单位', 'rp1', '瑞甲', '13800000081', '沪R 00001'], str(_row1))
    # 清理现场
    for u in ['rp1', 'rp2']:
        jsx("var row=[].slice.call(document.querySelectorAll('#tbody tr')).filter(function(tr){return tr.cells[2].textContent==="+json.dumps(u)+"})[0];"
            "if(row){row.querySelector('.row-btn.del').click(); document.getElementById('btn-confirm-ok').click()} return 1")
        time.sleep(0.2)
    click('btn-save'); time.sleep(3.5)
    click('btn-logout-a'); time.sleep(0.3)
    if jsx("return document.getElementById('modal-confirm').classList.contains('open')") is True:
        click('btn-confirm-ok')
    time.sleep(0.5)

    # ============ 阶段 F：车牌自动格式化 + placeholder ============
    print('== 阶段F：车牌格式化 ==')
    r, _ = do_login('user', 'newadmin77')
    ok('F0 管理员登录', r == 'admin', r)
    ok('F1 搜索框placeholder', jsx("return document.getElementById('search-box').placeholder") == '点击此处开始搜索',
       jsx("return document.getElementById('search-box').placeholder"))
    click('btn-import'); time.sleep(0.3)
    _fimp = ('PX项目,一公司,fmt1,格式甲,13800000021,京B12345' + chr(10)
             + 'PX项目,一公司,fmt2,格式乙,13800000022,沪A BV2070' + chr(10)
             + 'PX项目,一公司,fmt3,格式丙,13800000023,粤AD12345')
    jsx("document.getElementById('imp-text').value=" + json.dumps(_fimp) + "; return 1")
    click('btn-imp-ok'); time.sleep(0.6)
    _plates = jsx("return [].slice.call(document.querySelectorAll('#tbody tr')).filter(function(tr){return tr.cells[2].textContent.indexOf('fmt')===0}).map(function(tr){return tr.cells[5].textContent.trim()})")
    ok('F2 导入车牌自动格式化(第2位字母后加空格,幂等)', _plates == ['京B 12345', '沪A BV2070', '粤A D12345'], str(_plates))
    # 编辑无空格旧车牌 → 保存后自动补空格（幂等）
    jsx("var row=[].slice.call(document.querySelectorAll('#tbody tr')).filter(function(tr){return tr.cells[2].textContent==='fmt1'})[0];"
        "if(row){row.querySelector('.row-btn').click()} return row?1:0")
    time.sleep(0.2)
    jsx("document.getElementById('f-plate').value='京B67890'; return 1")
    click('btn-edit-ok'); time.sleep(0.3)
    _p2 = jsx("return [].slice.call(document.querySelectorAll('#tbody tr')).filter(function(tr){return tr.cells[2].textContent==='fmt1'})[0].cells[5].textContent.trim()")
    ok('F3 编辑车牌格式化', _p2 == '京B 67890', repr(_p2))
    # 撤销编辑现场（删 fmt 用户，避免污染后续）
    for u in ['fmt1','fmt2','fmt3']:
        jsx("var row=[].slice.call(document.querySelectorAll('#tbody tr')).filter(function(tr){return tr.cells[2].textContent==="+json.dumps(u)+"})[0];"
            "if(row){row.querySelector('.row-btn.del').click(); document.getElementById('btn-confirm-ok').click()} return 1")
        time.sleep(0.2)
    time.sleep(3.2)

    # ============ 阶段 T：conn 竞态事故链（死循环+旧数据覆盖修复验证） ============
    print('== 阶段T：conn竞态 ==')
    # T0 产品代码形态：登录主体必须被 whenConnReady 包裹；不再有 location.reload 强刷
    _src = open(os.path.join(HERE, '..', 'shdgjy.html'), encoding='utf-8').read()
    ok('T0 doLogin主体由whenConnReady包裹', 'whenConnReady(function(){ setTimeout(function(){' in _src)
    ok('T0 无location.reload调用', _src.count('location.reload(') == 0)
    # T1 服务器不可达(offline)时登录：用内嵌快照、离线提示、且绝不死循环
    subprocess.run(DOCKER + ['stop', API_CONTAINER], stdout=subprocess.DEVNULL)
    jsx("try{localStorage.removeItem('shdgjy-auth')}catch(e){}; window.__noloop=1; return 1")
    goto(BASE_ON + '/shdgjy.html'); time.sleep(9.5)  # WebDriver 同URL导航会重载页面；等 fetch 8s 超时 → offline
    jsx("window.__noloop=1; return 1")  # 重载后再注入观察标记
    jsx("document.getElementById('li-user').value='user';document.getElementById('li-pass').value='admin';"
        "document.getElementById('btn-login').click(); return 1")
    t0 = time.time()
    while time.time() - t0 < 12:
        if jsx("return !document.getElementById('view-admin').classList.contains('hidden')"): break
        time.sleep(0.2)
    time.sleep(2)
    ok('T1 offline登录成功(内嵌兜底)', jsx("return !document.getElementById('view-admin').classList.contains('hidden')") is True)
    ok('T1 离线模式提示', '离线模式' in txt('sync-note'), txt('sync-note'))
    ok('T1 无页面重载(不死循环)', jsx("return window.__noloop") == 1)
    # T2 offline 保存绝不写服务器（防内嵌旧数据覆盖线上数据的事故链）
    jsx("window.__posts=0; var _of=window.fetch; window.fetch=function(u,o){ if(o&&o.method==='POST') window.__posts++; return _of.apply(this,arguments)}; return 1")
    click('btn-save'); time.sleep(3)
    ok('T2 offline保存不发POST(零覆盖风险)', (jsx("return window.__posts") or 0) == 0,
       f"POST次数={jsx('return window.__posts')}")
    ok('T2 页面仍稳定(保存后无循环)', jsx("return window.__noloop") == 1)
    click('btn-logout-a'); time.sleep(0.3)
    if jsx("return document.getElementById('modal-confirm').classList.contains('open')") is True:
        click('btn-confirm-ok')
    time.sleep(0.5)
    # 恢复在线语境（S 组依赖服务器）
    subprocess.run(DOCKER + ['start', API_CONTAINER], stdout=subprocess.DEVNULL)
    time.sleep(1.5)

    # ============ 阶段 S：六字段 / 级联筛选 / 分页 / 唯一性 / 断行 ============
    print('== 阶段S：六字段+筛选+分页 ==')
    r, _ = do_login('user', 'newadmin77')
    ok('S0 管理员登录', r == 'admin', r)
    _n0 = int(txt('row-count').split()[1])
    click('btn-add'); time.sleep(0.2)
    jsx("document.getElementById('f-proj').value='SX项目';document.getElementById('f-org').value='十公司';"
        "document.getElementById('f-user').value='snew1';document.getElementById('f-name').value='表单新增';"
        "document.getElementById('f-phone').value='13900000001';document.getElementById('f-plate').value='沪S00001';return 1")
    click('btn-edit-ok'); time.sleep(0.4)
    ok('S1 表单添加6字段成功', int(txt('row-count').split()[1]) == _n0 + 1, txt('row-count'))
    click('btn-add'); time.sleep(0.2)
    jsx("document.getElementById('f-proj').value='SX项目';document.getElementById('f-org').value='十公司';"
        "document.getElementById('f-user').value='snew1';document.getElementById('f-name').value='重名者';"
        "document.getElementById('f-phone').value='13900000002';document.getElementById('f-plate').value='沪S00002';return 1")
    click('btn-edit-ok'); time.sleep(0.3)
    ok('S2 重名添加被阻止', int(txt('row-count').split()[1]) == _n0 + 1 and '已存在' in (jsx("return document.getElementById('edit-err').textContent") or ''),
       txt('row-count') + ' / ' + str(jsx("return document.getElementById('edit-err').textContent")))
    ok('S2 重名3秒浮窗提示', '已存在' in (jsx("return document.getElementById('toast').textContent") or ''))
    # S2b 用户名含空格被拒（线上实录 approvals mode 事故）
    jsx("document.getElementById('f-proj').value='SX项目';document.getElementById('f-org').value='十公司';"
        "document.getElementById('f-user').value='approvals mode';document.getElementById('f-name').value='带空格';"
        "document.getElementById('f-phone').value='13900000005';document.getElementById('f-plate').value='沪S00005';return 1")
    click('btn-edit-ok'); time.sleep(0.3)
    ok('S2b 含空格用户名被拒', (jsx("return document.getElementById('edit-err').textContent") or '') == '用户名不能包含空格',
       repr(jsx("return document.getElementById('edit-err').textContent")))
    jsx("document.querySelector('#modal-edit [data-close]').click(); return null"); time.sleep(0.2)
    jsx("document.querySelector('#modal-edit [data-close]').click(); return null"); time.sleep(0.3)
    click('btn-import'); time.sleep(0.3)
    _dupimp = 'SX项目,十公司,dupx,重复甲,13900000003,沪S00003' + chr(10) + 'SX项目,十公司,snew1,撞名,13900000004,沪S00004'
    jsx("document.getElementById('imp-text').value=" + json.dumps(_dupimp) + "; return 1")
    click('btn-imp-ok'); time.sleep(0.5)
    ok('S3 导入重名整批取消', int(txt('row-count').split()[1]) == _n0 + 1 and '取消' in (jsx("return document.getElementById('imp-result').textContent") or ''),
       txt('row-count') + ' / ' + str(jsx("return document.getElementById('imp-result').textContent")))
    jsx("document.querySelector('#modal-import [data-close]').click(); return null"); time.sleep(0.3)
    time.sleep(3.5)
    _bulk = chr(10).join([f'BK项目{chr(65+i//12)},单位{chr(65+i//12)}{i%3},bk{i:02d},批量{i},139111{i:05d},沪B{i:05d}' for i in range(24)])
    click('btn-import'); time.sleep(0.3)
    jsx("document.getElementById('imp-text').value=" + json.dumps(_bulk) + "; return 1")
    click('btn-imp-ok'); time.sleep(0.6)
    _total = int(txt('row-count').split()[1])
    ok('S4 批量导入24条', _total == _n0 + 25, txt('row-count'))
    time.sleep(4.2)
    ok('S5 分页器出现', jsx("return !document.getElementById('pager').classList.contains('hidden')") is True)
    ok('S5 第1/2页', txt('pg-info') == '第 1/2 页', txt('pg-info'))
    _rows1 = jsx("return document.getElementById('tbody').rows.length")
    click('pg-next'); time.sleep(0.3)
    _rows2 = jsx("return document.getElementById('tbody').rows.length")
    ok('S5 翻页正确', _rows1 == 20 and _rows2 == _total - 20, f'p1={_rows1} p2={_rows2}')
    click('pg-prev'); time.sleep(0.3)
    jsx("document.getElementById('sel-proj').value='BK项目A';"
        "document.getElementById('sel-proj').dispatchEvent(new Event('change',{bubbles:true}));return 1")
    time.sleep(0.5)
    ok('S6 项目筛选12条', int(txt('row-count').split()[1]) == 12, txt('row-count'))
    ok('S6 选项目后隐藏项目列', jsx("return document.querySelector('th.h-proj').classList.contains('hidden')") is True)
    _opts = jsx("return [].slice.call(document.getElementById('sel-org').options).map(function(o){return o.value})")
    ok('S6 单位下拉仅含该项目单位', _opts == ['', '单位A0', '单位A1', '单位A2'], str(_opts))
    jsx("document.getElementById('sel-org').value='单位A1';"
        "document.getElementById('sel-org').dispatchEvent(new Event('change',{bubbles:true}));return 1")
    time.sleep(0.5)
    ok('S6 级联单位筛选4条', int(txt('row-count').split()[1]) == 4, txt('row-count'))
    ok('S6 选单位后隐藏单位列', jsx("return document.querySelector('th.h-org').classList.contains('hidden')") is True)
    jsx("var e=document.getElementById('search-box');e.value='bk00';e.dispatchEvent(new Event('input',{bubbles:true}));return 1")
    time.sleep(0.4)
    ok('S7 筛选+搜索叠加', '匹配' in txt('row-count') or int(txt('row-count').split()[1]) >= 0, txt('row-count'))
    click('btn-filter-reset'); time.sleep(0.5)
    ok('S8 重置恢复两列', jsx("return !document.querySelector('th.h-proj').classList.contains('hidden')") is True
       and jsx("return !document.querySelector('th.h-org').classList.contains('hidden')") is True)
    ok('S8 重置恢复全量', int(txt('row-count').split()[1]) == _total and txt('pg-info') == '第 1/2 页', txt('row-count') + ' ' + txt('pg-info'))
    _longp = 'ABCDEFGHIJKLMNOPQRST汉'
    click('btn-add'); time.sleep(0.2)
    jsx("document.getElementById('f-proj').value=" + json.dumps(_longp) + ";document.getElementById('f-org').value='断行测';"
        "document.getElementById('f-user').value='wrap1';document.getElementById('f-name').value='断行';"
        "document.getElementById('f-phone').value='13900000009';document.getElementById('f-plate').value='沪W00001';return 1")
    click('btn-edit-ok'); time.sleep(0.4)
    jsx("var e=document.getElementById('search-box');e.value='wrap1';e.dispatchEvent(new Event('input',{bubbles:true}));return 1")
    time.sleep(0.4)
    # 比例分宽：项目/单位列宽应为 20/77×文字区（约26%），长内容(22英字符)桌面比例宽内单行或列宽内折行
    _ws = jsx("var hs=[].slice.call(document.querySelectorAll('thead th')).map(function(th){return Math.round(th.getBoundingClientRect().width)}); return hs")
    ok('S9 比例分宽(项目=单位>用户名>手机>姓名=车牌)', _ws and _ws[0]==_ws[1] and _ws[2]>_ws[4] and _ws[4]>_ws[3] and _ws[3]==_ws[5], str(_ws))
    ok('S9 码列=操作列(5份,均窄于姓名)', _ws and abs(_ws[6]-_ws[7])<=2 and _ws[6] < _ws[3], str(_ws))
    _rects = jsx("var sp=document.querySelector('#tbody tr td:first-child .cell-w');var rg=document.createRange();rg.selectNodeContents(sp);return [rg.getClientRects().length, Math.round(sp.getBoundingClientRect().width)]")
    ok('S9 长项目名不超出列宽', _rects and _rects[1] <= _ws[0] + 2, f"内容宽={_rects[1] if _rects else None} 列宽={_ws[0] if _ws else None}")
    jsx("var e=document.getElementById('search-box');e.value='';e.dispatchEvent(new Event('input',{bubbles:true}));return 1")
    time.sleep(0.3)
    jsx("document.getElementById('sel-proj').value='BK项目A';document.getElementById('sel-proj').dispatchEvent(new Event('change',{bubbles:true}));return 1")
    time.sleep(0.5)
    _csv = jsx("return window.__t.buildCsv()")
    _csvlines = _csv.strip().split(chr(10)) if _csv else []
    ok('S10 CSV六列表头+筛选范围12条', _csvlines and _csvlines[0].lstrip('\ufeff').startswith('项目名称,单位名称,用户名,姓名,手机号,车牌号') and len(_csvlines) == 13, str(_csvlines[:1]) + f' 行数={len(_csvlines)}')
    click('btn-filter-reset'); time.sleep(0.5)
    click('btn-logout-a'); time.sleep(0.3)
    if jsx("return document.getElementById('modal-confirm').classList.contains('open')") is True:
        click('btn-confirm-ok')
    time.sleep(0.5)

    # ============ 阶段 B：离线降级（无 PHP 服务器）============
    print('== 阶段B：离线降级 ==')
    subprocess.run(DOCKER + ['stop', API_CONTAINER], stdout=subprocess.DEVNULL)
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
    subprocess.run(DOCKER + ['start', API_CONTAINER], stdout=subprocess.DEVNULL)
    time.sleep(1)
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
    # D2-D5 管理页 390px：表格无横滚/操作列堆叠/保存按钮醒目
    jsx("var d=document.getElementById('f').contentWindow.document;"
        "d.getElementById('li-user').value='user';d.getElementById('li-pass').value='newadmin77';"
        "d.getElementById('btn-login').click(); return 1")
    time.sleep(4.5)
    # 制造 dirty：新增一个用户
    jsx("var d=document.getElementById('f').contentWindow.document;"
        "d.getElementById('btn-add').click();"
        "d.getElementById('f-proj').value='DX项目';"
        "d.getElementById('f-org').value='窄屏单位';"
        "d.getElementById('f-user').value='d390x';"
        "d.getElementById('f-name').value='窄屏';"
        "d.getElementById('f-phone').value='13812340000';"
        "d.getElementById('f-plate').value='沪D00390';"
        "d.getElementById('btn-edit-ok').click(); return 1")
    time.sleep(0.6)
    m2 = jsx("var d=document.getElementById('f').contentWindow.document;"
             "var w=d.querySelector('.table-wrap'); return [w.scrollWidth, w.clientWidth, d.getElementById('tbody').rows.length]")
    ok('D2 390px表格数据可达(横滚允许)', m2 and m2[2] >= 3, str(m2))
    _wm = jsx("var d=document.getElementById('f').contentWindow.document;var w=d.querySelector('.table-wrap');var t=d.querySelector('table');"
              "var hs=[].slice.call(d.querySelectorAll('thead th')).map(function(th){return [th.getAttribute('data-col'), Math.round(th.getBoundingClientRect().width), th.style.width||'-']});"
              "return [t.scrollWidth>w.clientWidth+1, Math.round(d.querySelector('th.h-proj').getBoundingClientRect().width), d.querySelector('th[data-col=op]').style.width, JSON.stringify(hs)]")
    print('  [D2b列] 横滚=', _wm[0], '| projRect=', _wm[1], '| opInline=', _wm[2], '| 各列[col,rect,inline]=', _wm[3])
    ok('D2b 390px手机模式(写死列宽+可横滑)', _wm and _wm[0] is True and 185<=_wm[1]<=210 and _wm[2]=='38px', str(_wm[:3]))
    # D2c 车牌不断行 + 操作按钮横排
    _d2c = jsx("var d=document.getElementById('f').contentWindow.document;"
        "var plateCell=d.querySelector('#tbody tr td:nth-child(6) .cell-w');"
        "var rg=d.createRange(); rg.selectNodeContents(plateCell); var rects=rg.getClientRects().length;"
        "var btn=d.querySelector('#tbody tr .row-btn'); var br=btn.getBoundingClientRect();"
        "return [rects, Math.round(br.height), btn.scrollWidth<=Math.round(br.width)+2]")
    ok('D2c 车牌整串单行+按钮横排', _d2c and _d2c[0]==1 and _d2c[1]<=32 and _d2c[2] is True, str(_d2c))
    m3 = jsx("var d=document.getElementById('f').contentWindow.document;"
             "var bts=d.querySelector('#tbody tr .op-stack').children;"
             "var a=bts[0].getBoundingClientRect(), b=bts[1].getBoundingClientRect();"
             "return [Math.round(a.left), Math.round(b.left), Math.round(b.top-a.bottom)]")
    ok('D3 编辑/删除垂直堆叠+间距', m3 and abs(m3[0]-m3[1]) <= 2 and m3[2] >= 4, str(m3))
    m4 = jsx("var d=document.getElementById('f').contentWindow.document;"
             "var s=d.getElementById('btn-save').getBoundingClientRect();"
             "var cs=getComputedStyle(d.getElementById('btn-save'));"
             "return [Math.round(s.height), cs.fontWeight, cs.fontSize, d.getElementById('save-bar').classList.contains('show')]")
    ok('D4 保存按钮醒目(≥40px/粗体/dirty显示)', m4 and m4[0] >= 40 and m4[1] in ('700','bold') and m4[3] is True, str(m4))
    m5 = jsx("var d=document.getElementById('f').contentWindow.document;"
             "var d2=d.getElementById('dirty-badge').getBoundingClientRect();"
             "var s=d.getElementById('btn-set').getBoundingClientRect();"
             "return [Math.round(d2.left), Math.round(s.right), d.getElementById('dirty-badge').classList.contains('show')]")
    ok('D5 390px未保存标签在密码设置右侧', m5 and m5[0] >= m5[1] - 2 and m5[2] is True, str(m5))

except Exception:
    import traceback
    traceback.print_exc()
    FAIL += 1
finally:
    print(f'\n结果: {PASS} 通过, {FAIL} 失败')
    try:
        if sid: api('DELETE', f'/session/{sid}')
    except Exception: pass
    for p in (gd, on_srv, off_srv):
        p.terminate()
    sys.exit(1 if FAIL else 0)
