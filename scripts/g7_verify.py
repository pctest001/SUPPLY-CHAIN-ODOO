import requests, json

# 1) 动态定位系统管理员（不假设 login 名），设演示密码
sys_group = env.ref('base.group_system', raise_if_not_found=False)
if sys_group:
    admin = env['res.users'].search([('groups_id', 'in', [sys_group.id])], limit=1)
else:
    admin = env['res.users'].search([], limit=1, order='id')
print('[1] admin login =', admin.login, '| name =', admin.name)
admin.sudo().write({'password': 'admin123'})
env.cr.commit()
print('    password set -> admin123')

BASE = 'http://odoo:8069'
s = requests.Session()

# 2) 登录拿 session
r = s.post(BASE + '/web/session/authenticate', json={
    'jsonrpc': '2.0', 'method': 'call',
    'params': {'db': 'supplychain', 'login': admin.login, 'password': 'admin123'}})
res = r.json().get('result', {})
print('[2] auth uid =', res.get('uid'))
assert res.get('uid'), 'login failed'

# 3) 触发后台页面（编译 web.assets_backend：sc_ai.scss/js 必须不崩）
r2 = s.get(BASE + '/web')
print('[3] GET /web status =', r2.status_code, '| references /web/assets =', ('/web/assets/' in r2.text))

# 3b) 确认 sc_ai 前端代码被打包进 web.assets_backend JS bundle（浏览器会真正加载）
import re
js_urls = re.findall(r'src="(/web/assets/[^"]*\.js)"', r2.text)
print('[3b] js bundles referenced =', len(js_urls))
found_any = False
for u in js_urls:
    if 'web.assets_backend' not in u:
        continue
    c = s.get(BASE + u).text
    hits = {k: (k in c) for k in ['sc_ai_chat', 'AiChatSystray',
                                  'get_or_create_session', '供应链 AI 助手', 'new_session']}
    print('   bundle', u.split('/')[-1], '| len', len(c), '| hits', hits)
    if any(hits.values()):
        found_any = True
print('[3b] frontend code bundled into web.assets_backend =', found_any)

# 4) 模拟前端 call_kw：get_or_create_session
def call_kw(method, args, kwargs=None):
    return s.post(BASE + '/web/dataset/call_kw', json={
        'jsonrpc': '2.0', 'method': 'call',
        'params': {'model': 'ai.chat.session', 'method': method,
                   'args': args, 'kwargs': kwargs or {}}})

r3 = call_kw('get_or_create_session', [])
j3 = r3.json()
print('[4] get_or_create_session http =', r3.status_code, '| has result =', 'result' in j3)
sid = j3.get('result', {}).get('id')
print('    session id =', sid, '| history msgs =', len(j3.get('result', {}).get('messages', [])))

# 5) chat：发送一条问库存，验证真实 LLM 链路
r4 = call_kw('chat', [sid, '当前有哪些物料库存？'])
rr = r4.json().get('result', {})
ans = rr.get('answer', '') or ''
print('[5] chat http =', r4.status_code, '| answer len =', len(ans))
print('    answer preview =', ans[:160].replace(chr(10), ' '))

# 6) new_session
r5 = call_kw('new_session', [])
print('[6] new_session id =', r5.json().get('result', {}).get('id'))
print('=== G7 BACKEND + RPC VERIFY DONE ===')
