import requests, re

BASE = 'http://odoo:8069'
s = requests.Session()
r = s.post(BASE + '/web/session/authenticate', json={
    'jsonrpc': '2.0', 'method': 'call',
    'params': {'db': 'supplychain', 'login': 'admin@example.com', 'password': 'admin123'}})
print('auth uid =', r.json().get('result', {}).get('uid'))

rweb = s.get(BASE + '/web')
js_urls = re.findall(r'src="(/web/assets/[^"]*\.js)"', rweb.text)
print('bundles:', [u.split('/')[-1] for u in js_urls])
for u in js_urls:
    c = s.get(BASE + u).text
    print('=== bundle', u.split('/')[-1], 'len', len(c), '===')
    for kw in ['get_or_create_session', 'new_session', '_loadSession', 'sc_ai_chat',
              'AiChatSystray', 'ai.chat.session', 'toggle']:
        idx = c.find(kw)
        if idx >= 0:
            snippet = c[idx-30:idx+70].replace('\n', ' ')
            print('  FOUND', kw, '@', idx, '::', snippet)
        else:
            print('  MISSING', kw)
