import odoo
from odoo.api import Environment
from odoo import SUPERUSER_ID
odoo.tools.config.parse_config(['-d', 'supplychain', '--db_host', 'db',
                                '--db_port', '5432', '--db_user', 'odoo', '--db_password', 'odoo'])
cr = odoo.registry('supplychain').cursor()
env = Environment(cr, SUPERUSER_ID, {})
print('base.language.install fields:', list(env['base.language.install']._fields.keys()))
print('res.lang exists zh_CN:', bool(env['res.lang'].with_context(active_test=False).search([('code','=','zh_CN')], limit=1)))
# 尝试直接调用 res.lang 的加载方法
rl = env['res.lang'].with_context(active_test=False).search([('code','=','zh_CN')], limit=1)
print('zh_CN active:', rl.active if rl else None)
print('res.lang methods with lang:', [m for m in dir(env['res.lang']) if 'lang' in m.lower()])
cr.close()
