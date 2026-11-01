#!/usr/bin/env python3
# shdgjy.html 全流程功能测试（geckodriver + headless Firefox，走真实 UI 点击路径）
# 覆盖：登录错误分支、管理员增删改查、批量导入、搜索、改统一密码、
#       保存生成新文件、导出文件二次登录验证（新密码生效/旧密码失效/数据完好）
# 用法：python3 dev/test-functional.py [--shots]   （--shots 额外输出截图）
import json, subprocess, time, sys, os, base64, urllib.request, urllib.error, signal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_TEST = os.path.join(HERE, 'out-test.html')
SHOTS = os.path.join(HERE, 'shots')
GD = '/home/spark/.local/bin/geckodriver'
PORT = 4463
HTTP_PORT = 8123
BASE = f'http://127.0.0.1:{HTTP_PORT}'

# 清代理，避免 WebDriver 本地调用被 FlClash 截走
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
    try:
        return json.loads(op.open(req, timeout=120).read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try: return json.loads(raw)
        except Exception: return {'error': f'HTTP {e.code}'}

PASS = FAIL = 0
def ok(name, cond, extra=''):
    global PASS, FAIL
    if cond: PASS += 1; print(f'  PASS {name}')
    else:    FAIL += 1; print(f'  FAIL {name}  {extra}')

def click(el_id):
    return api('POST', f'/session/{sid}/execute/sync',
               {'script': f"document.getElementById('{el_id}').click(); return null", 'args': []})

def jsx(script):
    r = api('POST', f'/session/{sid}/execute/sync', {'script': script, 'args': []})
    if not isinstance(r, dict): return None
    v = r.get('value')
    # WebDriver 错误响应的 value 是含 error 键的 dict，不能当正常返回值（否则 truthy 误判）
    if isinstance(v, dict) and 'error' in v: return None
    return v

def goto(url):
    api('POST', f'/session/{sid}/url', {'url': url})
    time.sleep(1.2)

def txt(el_id):
    return jsx(f"return document.getElementById('{el_id}').textContent") or ''

def set_input(el_id, value, ev='input'):
    js = ("var e=document.getElementById('%s'); e.value=%s; "
          "e.dispatchEvent(new Event('%s',{bubbles:true})); return e.value.length") % (el_id, json.dumps(value), ev)
    return jsx(js)

def wait_login_result(timeout=25):
    """提交登录后轮询，返回 (结果类型, 耗时秒)：err 文案 / user / admin"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        err = txt('login-err')
        if err: return ('err:' + err, time.time() - t0)
        v = jsx("return [!document.getElementById('view-user').classList.contains('hidden'),"
                "!document.getElementById('view-admin').classList.contains('hidden')]")
        if v and v[0]: return ('user', time.time() - t0)
        if v and v[1]: return ('admin', time.time() - t0)
        time.sleep(0.1)
    return ('timeout', timeout)

def do_login(u, p):
    set_input('li-user', u)
    set_input('li-pass', p)
    click('btn-login')
    return wait_login_result()

def shot(name):
    r = api('GET', f'/session/{sid}/screenshot')
    if isinstance(r.get('value'), str):
        os.makedirs(SHOTS, exist_ok=True)
        with open(os.path.join(SHOTS, name), 'wb') as f:
            f.write(base64.b64decode(r['value']))

sid = None
try:
    sess = api('POST', '/session', {'capabilities': {'alwaysMatch': {
        'moz:firefoxOptions': {'args': ['-headless']}}}})
    sid = sess['value']['sessionId']
    api('POST', f'/session/{sid}/window/rect', {'width': 2560, 'height': 1440})
    time.sleep(0.5)

    # ============ 阶段 A：初始文件 ============
    print('== 阶段A：初始 shdgjy.html ==')
    goto(f'{BASE}/shdgjy.html')
    ok('A1 登录视图可见', jsx("return !document.getElementById('view-login').classList.contains('hidden')"))
    ok('A1 版本号 v0.1.0', 'shdgjy v0.1.0' in (jsx("return document.body.textContent") or ''))
    ok('A1 应用无JS错误', jsx("return window.__t?window.__t.version:'undefined'") == '0.1.0')
    if '--shots' in sys.argv: shot('a1-login-desktop.png')

    r, dt = do_login('chen1', 'wrongpass')
    ok('A2 错误统一密码→密码错误', r == 'err:密码错误', f'{r} {dt:.1f}s')
    print(f'  (登录派生耗时 {dt:.2f}s)')

    r, _ = do_login('nouser99', '12345678')
    ok('A3 正确密码+不存在用户→用户名不存在', r == 'err:用户名不存在')

    r, _ = do_login('user', 'wrongadmin')
    ok('A4 管理员错误密码→密码错误', r == 'err:密码错误')

    r, _ = do_login('user', 'admin')
    ok('A5 管理员登录→管理视图', r == 'admin')
    ok('A5 初始 0 人', txt('row-count') == '共 0 人')

    # 批量导入：表头1行 + 有效3 + 粘贴内重复1 + 缺列1
    click('btn-import')
    imp = "用户名,姓名,车牌号\nchen1,陈大山,沪A11111\nchen2,陈二水,沪B22222\nchen3,陈三石,皖C33333\nchen1,重复人,沪D99999\nbadline,缺列"
    set_input('imp-text', imp)
    ok('A6 预览识别4条(含粘贴内重复行,去重在应用时)', txt('imp-preview') == '已识别 4 条有效数据，1 行无法识别', txt('imp-preview'))
    click('btn-imp-ok')
    time.sleep(0.3)
    ok('A6 导入后 3 人', txt('row-count') == '共 3 人', txt('row-count'))
    ok('A6 导入结果文案', '新增 3 人' in txt('imp-result') and '跳过重复 1 人' in txt('imp-result'), txt('imp-result'))
    ok('A6 表格含陈大山', '陈大山' in txt('tbody'))
    jsx("document.querySelectorAll('.modal.open').forEach(function(m){m.classList.remove('open')}); return null")

    # 添加用户
    click('btn-add')
    set_input('f-user', 'wangwu'); set_input('f-name', '王大力'); set_input('f-plate', '沪C33333')
    click('btn-edit-ok'); time.sleep(0.2)
    ok('A7 添加后 4 人', txt('row-count') == '共 4 人', txt('row-count'))

    # 重复用户名被拒
    click('btn-add')
    set_input('f-user', 'chen1'); set_input('f-name', '重复'); set_input('f-plate', '沪Z00000')
    click('btn-edit-ok'); time.sleep(0.2)
    ok('A8 重复用户名被拒', txt('edit-err') == '用户名已存在')
    jsx("document.getElementById('modal-edit').classList.remove('open'); return null")

    # 保留名被拒
    click('btn-add')
    set_input('f-user', 'user'); set_input('f-name', '冒名'); set_input('f-plate', '沪Z11111')
    click('btn-edit-ok'); time.sleep(0.2)
    ok('A9 保留名 tww 被拒', txt('edit-err') == '该用户名为管理员保留名')
    jsx("document.getElementById('modal-edit').classList.remove('open'); return null")

    # 编辑 chen1 姓名
    jsx("var b=[].slice.call(document.querySelectorAll('#tbody .row-btn')).filter(function(x){return x.textContent==='编辑'})[0]; b.click(); return null")
    time.sleep(0.2)
    set_input('f-name', '陈大山峰'); set_input('f-plate', '沪A12345')
    click('btn-edit-ok'); time.sleep(0.2)
    ok('A10 编辑生效', '陈大山峰' in txt('tbody') and '沪A12345' in txt('tbody'))
    ok('A10 编辑后仍 4 人', txt('row-count') == '共 4 人')

    # 搜索
    set_input('search-box', '沪A')
    ok('A11 搜索过滤 1/4', txt('row-count') == '匹配 1 / 4 人', txt('row-count'))
    set_input('search-box', '')
    ok('A11 清空搜索恢复', txt('row-count') == '共 4 人')

    # 删除 chen2（确认弹窗走真实点击）
    del2 = ("var row=[].slice.call(document.querySelectorAll('#tbody tr')).filter(function(tr){return tr.cells[0].textContent==='chen2'})[0];"
            "if(row){row.querySelector('.row-btn.del').click()} return row?1:0")
    jsx(del2); time.sleep(0.2)
    ok('A12 删除确认框弹出', jsx("return document.getElementById('modal-confirm').classList.contains('open')"))
    click('btn-confirm-ok'); time.sleep(0.2)
    ok('A12 删除后 3 人', txt('row-count') == '共 3 人', txt('row-count'))

    # 未保存状态条
    ok('A13 未保存提示出现', jsx("return document.getElementById('save-bar').classList.contains('show')"))
    if '--shots' in sys.argv: shot('a13-admin-desktop.png')

    # 密码设置：统一密码改为新值
    click('btn-set')
    ok('A14 设置框预填当前统一密码', jsx("return document.getElementById('set-unified').value") == '12345678')
    set_input('set-unified', 'shdgjy2026ok')
    click('btn-set-ok'); time.sleep(0.2)
    ok('A14 设置弹窗关闭', not jsx("return document.getElementById('modal-settings').classList.contains('open')"))

    # CSV 钩子
    csv = jsx("return window.__t.buildCsv()")
    ok('A15 CSV 含表头与3行(4行3个换行)', isinstance(csv, str) and csv.count('\n') == 3 and '陈大山峰' in csv and csv.startswith('\ufeff用户名,姓名,车牌号'),
       repr(csv)[:80] if isinstance(csv, str) else str(csv))

    # 保存并生成文件（真实点击按钮，再从钩子取产物）
    click('btn-save')
    for _ in range(80):
        if jsx("return document.getElementById('modal-export').classList.contains('open')"): break
        time.sleep(0.25)
    ok('A16 导出弹窗弹出', jsx("return document.getElementById('modal-export').classList.contains('open')"))
    exp = jsx("return window.__t.generateFile()")
    ok('A16 生成文件非空', isinstance(exp, dict) and len(exp.get('html', '')) > 30000, str(type(exp)))
    html = exp['html']
    ok('A16 DOCTYPE+闭合', html.startswith('<!DOCTYPE html>') and html.rstrip().endswith('</html>'))
    ok('A16 含新数据块', '"fmt":"H1"' in html)
    ok('A16 无真实数据明文泄露', ('王大力' not in html) and ('陈大山峰' not in html) and ('chen3' not in html))
    ok('A16 无会话残留(modal open)', 'modal open' not in html and 'save-bar show' not in html)
    ok('A16 管理视图已还原隐藏', 'id="view-admin" class="view hidden"' in html)
    ok('A16 登录视图还原可见', 'id="view-login" class="view"' in html)
    ok('A16 版本号保留', 'shdgjy v0.1.0' in html)
    with open(OUT_TEST, 'w', encoding='utf-8') as f:
        f.write(html)
    st = jsx("return window.__t.state()")
    ok('A16 保存后脏标记清除', st and st['dirty'] is False)

    # ============ 阶段 B：导出文件重新登录 ============
    print('== 阶段B：导出产物 out-test.html ==')
    goto(f'{BASE}/dev/out-test.html')
    ok('B1 登录视图可见', jsx("return !document.getElementById('view-login').classList.contains('hidden')"))
    r, _ = do_login('chen1', '12345678')
    ok('B2 旧统一密码已失效', r == 'err:密码错误', r)
    r, dt = do_login('chen1', 'shdgjy2026ok')
    ok('B3 新统一密码登录成功', r == 'user', f'{r} {dt:.1f}s')
    ok('B3 姓名车牌正确', txt('u-name') == '陈大山峰' and txt('u-plate') == '沪A12345',
       txt('u-name') + '/' + txt('u-plate'))
    ok('B3 用户名显示', txt('u-user') == '用户名 chen1')
    if '--shots' in sys.argv: shot('b3-user-desktop.png')
    click('btn-logout-u'); time.sleep(0.3)

    r, _ = do_login('chen2', 'shdgjy2026ok')
    ok('B4 已删除用户无法登录', r == 'err:用户名不存在', r)

    r, _ = do_login('user', 'admin')
    ok('B5 管理员密码未变可登录', r == 'admin')
    ok('B5 3 人数据完好', txt('row-count') == '共 3 人', txt('row-count'))
    ok('B5 数据时间已更新', len(txt('data-time')) > 8, txt('data-time'))
    ok('B5 初始干净状态(无脏标记)', not jsx("return document.getElementById('save-bar').classList.contains('show')"))
    st = jsx("return window.__t.state()")
    ok('B5 state 钩子一致', st and st['count'] == 3 and st['dirty'] is False)
    if '--shots' in sys.argv: shot('b5-admin-desktop.png')

    # ============ 阶段 C：file:// 离线可用 ============
    print('== 阶段C：file:// 离线打开 ==')
    goto('file://' + os.path.join(ROOT, 'shdgjy.html'))
    r, _ = do_login('user', 'admin')
    ok('C1 file:// 管理员可登录', r == 'admin', r)

    # ============ 手机宽度（iframe 精确 390px，harness 必须走 http 同源，file:// 会跨域）============
    print('== 阶段D：390px 手机布局 ==')
    harness = os.path.join(HERE, 'harness.html')
    with open(harness, 'w', encoding='utf-8') as f:
        f.write('<!DOCTYPE html><html><body style="margin:0">\n'
                f'<iframe id="f" src="{BASE}/dev/out-test.html" style="width:390px;height:844px;border:0"></iframe>\n'
                '</body></html>')
    goto(f'{BASE}/dev/harness.html')
    time.sleep(1.5)
    m = jsx("var d=document.getElementById('f').contentWindow.document;"
            "var r=[d.getElementById('li-user'),d.getElementById('btn-login')].map(function(e){var b=e.getBoundingClientRect();return [Math.round(b.left),Math.round(b.right),Math.round(b.width)]});"
            "return r")
    ok('D1 登录框适配390px(无横向溢出)', m and all(row[1] <= 391 for row in m) and m[0][2] > 200, str(m))
    if '--shots' in sys.argv:
        el = api('POST', f'/session/{sid}/element', {'using': 'css selector', 'value': '#f'})
        if 'value' in el and isinstance(el['value'], dict) and 'elementId' in el['value']:
            eid = el['value']['elementId']
            s2 = api('GET', f'/session/{sid}/element/{eid}/screenshot')
            if isinstance(s2.get('value'), str):
                os.makedirs(SHOTS, exist_ok=True)
                with open(os.path.join(SHOTS, 'd1-login-mobile390.png'), 'wb') as f:
                    f.write(base64.b64decode(s2['value']))

finally:
    print(f'\n结果: {PASS} 通过, {FAIL} 失败')
    try:
        if sid: api('DELETE', f'/session/{sid}')
    except Exception: pass
    gd.terminate(); server.terminate()
    sys.exit(1 if FAIL else 0)
