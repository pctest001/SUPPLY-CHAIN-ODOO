import odoo
from odoo.api import Environment
from odoo import SUPERUSER_ID
odoo.tools.config.parse_config(['-d', 'supplychain', '--db_host', 'db',
                                '--db_port', '5432', '--db_user', 'odoo', '--db_password', 'odoo'])
cr = odoo.registry('supplychain').cursor()
env = Environment(cr, SUPERUSER_ID, {})
for src in ['Log in', 'Purchase', 'Vendor', 'Confirm', 'New', 'Save', 'Supplier']:
    rec = env['ir.translation'].search([('lang', '=', 'zh_CN'),
                                        ('src', '=', src)], limit=1)
    print(repr(src), '->', repr(rec.value) if rec else '（无译文）')
print('zh_CN 译本总数:', env['ir.translation'].search_count([('lang', '=', 'zh_CN')]))
cr.close()
