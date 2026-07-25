import requests, re

BASE = 'http://odoo:8069'
s = requests.Session()
r = s.post(BASE + '/web/session/authenticate', json={
    'jsonrpc': '2.0', 'method': 'call',
    'params': {'db': 'supplychain', 'login': 'admin@example.com', 'password': 'admin123'}})
print('auth uid =', r.json().get('result', {}).get('uid'))

print('=== 1) static file direct reachability ===')
for p in ['/sc_ai/static/src/sc_ai.js',
          '/sc_ai/static/src/ai_chat_panel/ai_chat_panel.xml',
          '/sc_ai/static/src/sc_ai.scss']:
    rr = s.get(BASE + p)
    print('  STATIC', p, '->', rr.status_code, '| len', len(rr.text),
          '| has AiChatSystray:', 'AiChatSystray' in rr.text)

print('=== 2) all js bundles in /web and sc_ai footprint ===')
rweb = s.get(BASE + '/web')
js_urls = re.findall(r'src="(/web/assets/[^"]*\.js)"', rweb.text)
print('  total js bundles referenced:', len(js_urls), [u.split('/')[-1] for u in js_urls])
keys = ['sc_ai_chat', 'AiChatSystray', 'get_or_create_session', '供应链 AI 助手', 'new_session', 'registry.category']
for u in js_urls:
    c = s.get(BASE + u).text
    hits = {k: (k in c) for k in keys}
    print('  bundle', u.split('/')[-1], '| len', len(c), '|', hits)

print('=== 3) ir_asset registration (Odoo 18 may not use it) ===')
try:
    a = env['ir.asset']
    recs = a.search([('path', 'like', 'sc_ai%')])
    print('  ir_asset sc_ai records:', [(x.bundle, x.path, x.directive) for x in recs])
except Exception as e:
    print('  ir_asset err (expected if Odoo18 dropped it):', e)

print('=== 4) manifest assets as Odoo parses ===')
import odoo.modules.manifest as M
mp = odoo.modules.module.get_module_path('sc_ai')
man = M.read_manifest(mp)
print('  module path:', mp)
print('  assets web.assets_backend:', man.get('assets', {}).get('web.assets_backend'))
