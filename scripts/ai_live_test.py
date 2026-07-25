# A4 实时联调：用 compose 注入的真实 SUPPLY_AI_API_KEY 让 Odoo 实调 DeepSeek
import os
import odoo
from odoo.api import Environment
from odoo import SUPERUSER_ID

odoo.tools.config.parse_config(['-d', 'supplychain', '--db_host', 'db',
                                '--db_port', '5432', '--db_user', 'odoo', '--db_password', 'odoo'])
cr = odoo.registry('supplychain').cursor()
env = Environment(cr, SUPERUSER_ID, {})

key = os.environ.get('SUPPLY_AI_API_KEY', '')
print('env key present :', bool(key))
print('env key prefix  :', (key[:6] + '...') if key else '缺失')
cfg = env['ai.config'].get_active()
print('ai.config       :', (cfg.name if cfg else None), (cfg.provider if cfg else None))

sess = env['ai.chat.session'].create({})
ans = sess.ask('用一句话说明：做好库存管理最关键的三个点是什么？')
print('--- AI 回答 ---')
print(ans)

low = any(k in ans for k in ('AI 暂时不可用', '规则引擎', 'AI 未配置', '降级'))
print('--- 是否降级(fallback):', low)
print('结论:', 'Key 有效，已返回真实 LLM 回答' if not low else 'Key 可能无效或网络受限，已走降级')
cr.close()
