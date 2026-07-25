import odoo
from odoo.api import Environment
from odoo import SUPERUSER_ID
odoo.tools.config.parse_config(['-d', 'supplychain', '--db_host', 'db',
                                '--db_port', '5432', '--db_user', 'odoo', '--db_password', 'odoo'])
cr = odoo.registry('supplychain').cursor()
env = Environment(cr, SUPERUSER_ID, {})
print('type selection:', env['product.template']._fields['type'].selection)
print('default type  :', env['product.template']._fields['type'].default)
cr.close()
