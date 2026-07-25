import odoo
from odoo.api import Environment
from odoo import SUPERUSER_ID
odoo.tools.config.parse_config(['-d', 'supplychain', '--db_host', 'db',
                                '--db_port', '5432', '--db_user', 'odoo', '--db_password', 'odoo'])
cr = odoo.registry('supplychain').cursor()
env = Environment(cr, SUPERUSER_ID, {})

admin = env.ref('base.user_admin')
print('base.user_admin id   :', admin.id)
print('base.user_admin login:', admin.login)
print('base.user_admin lang :', admin.lang)

# 模拟登录会话上下文（context_get 返回用户 lang）
print('context_get lang     :', admin.context_get().get('lang'))

# 是否还有别的 lang=en_US 的管理员账号
admins = env['res.users'].search([('groups_id', 'in', env.ref('base.group_system').id)])
for u in admins:
    print('  系统用户:', u.id, u.login, 'lang=', u.lang)
cr.close()
