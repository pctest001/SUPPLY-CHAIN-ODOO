import requests, re

BASE = 'http://odoo:8069'
s = requests.Session()
r = s.post(BASE + '/web/session/authenticate', json={
    'jsonrpc': '2.0', 'method': 'call',
    'params': {'db': 'supplychain', 'login': 'admin@example.com', 'password': 'admin123'}})
print('auth uid =', r.json().get('result', {}).get('uid'))

print('=== A) static ai_chat_panel.js integrity ===')
rjs = s.get(BASE + '/sc_ai/static/src/ai_chat_panel/ai_chat_panel.js')
print('  static len =', len(rjs.text))
for kw in ['_loadSession', 'get_or_create_session', 'new_session', 'toggle', 'send', 'AiChatSystray']:
    print('  static has', kw, ':', kw in rjs.text)

print('=== B) bundled footprint ===')
rweb = s.get(BASE + '/web')
js_urls = re.findall(r'src="(/web/assets/[^"]*\.js)"', rweb.text)
print('  bundles:', [u.split('/')[-1] for u in js_urls])
for u in js_urls:
    c = s.get(BASE + u).text
    print('  bundle', u.split('/')[-1], 'len', len(c))
    for kw in ['_loadSession', 'get_or_create_session', 'new_session', 'sc_ai_chat', 'AiChatSystray']:
        idx = c.find(kw)
        if idx >= 0:
            print('    FOUND', kw, '@', idx, '::', c[idx-25:idx+55].replace('\n', ' '))
        else:
            print('    MISSING', kw)
