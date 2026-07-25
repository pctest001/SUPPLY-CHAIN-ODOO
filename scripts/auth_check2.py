import json
import urllib.request
import urllib.error
import http.cookiejar

base = 'http://localhost:8069'
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def rpc(path, params):
    payload = {'jsonrpc': '2.0', 'method': 'call', 'params': params, 'id': 1}
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'})
    return json.loads(opener.open(req, timeout=20).read())


auth = rpc('/web/session/authenticate',
           {'db': 'supplychain', 'login': 'admin@example.com', 'password': 'admin'})
print('uid         :', auth['result'].get('uid'))
print('user_context:', auth['result'].get('user_context'))

res = rpc('/web/dataset/call_kw', {
    'model': 'ir.ui.menu',
    'method': 'search_read',
    'args': [[('name', 'in', ['Purchase', '采购'])]],
    'kwargs': {'fields': ['name'], 'limit': 5},
})
rows = res.get('result') or []
print('菜单命中    :', [(r['id'], r['name']) for r in rows])
zh = any(r['name'] == '采购' for r in rows)
print('结论        :', '会话上下文 = 简体中文(zh_CN)，登录后界面为中文' if zh else '会话上下文 = 英文(en_US)')
