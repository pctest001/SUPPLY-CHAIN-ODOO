import odoo
from odoo.api import Environment
from odoo import SUPERUSER_ID
odoo.tools.config.parse_config(['-d', 'supplychain', '--db_host', 'db',
                                '--db_port', '5432', '--db_user', 'odoo', '--db_password', 'odoo'])
cr = odoo.registry('supplychain').cursor()
env = Environment(cr, SUPERUSER_ID, {})

admin = env.ref('base.user_admin')
print('before admin.lang     :', admin.lang)
print('before partner.lang   :', admin.partner_id.lang)

# Odoo 18: res.users.lang 委托到 partner_id.lang，直接写 partner 最稳
admin.partner_id.write({'lang': 'zh_CN'})
admin.write({'lang': 'zh_CN'})
env.cr.commit()

admin2 = env['res.users'].browse(admin.id)
print('after  admin.lang     :', admin2.lang)
print('after  partner.lang   :', admin2.partner_id.lang)
print('DB lang 参数          :', env['ir.config_parameter'].get_param('lang'))
cr.close()
