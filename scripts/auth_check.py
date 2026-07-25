import json
import urllib.request
import urllib.error

base = 'http://localhost:8069'
payload = {'jsonrpc': '2.0', 'method': 'call',
           'params': {'db': 'supplychain', 'login': 'admin@example.com', 'password': 'admin'},
           'id': 1}
req = urllib.request.Request(base + '/web/session/authenticate',
                              data=json.dumps(payload).encode(),
                              headers={'Content-Type': 'application/json'})
try:
    resp = json.loads(urllib.request.urlopen(req, timeout=20).read())
except urllib.error.HTTPError as e:
    print('HTTP', e.code, e.read()[:200])
    raise
res = resp.get('result', {})
print('uid          :', res.get('uid'))
print('user_context :', res.get('user_context'))
print('结论         :', '会话语言=zh_CN，登录后界面为简体中文' if res.get('user_context', {}).get('lang') == 'zh_CN' else '会话语言非中文')
