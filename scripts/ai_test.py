import os
import odoo
from odoo.api import Environment
from odoo import SUPERUSER_ID
args = ['-d', 'supplychain']
if os.environ.get('HOST'):
    args += ['--db_host', os.environ['HOST']]
if os.environ.get('PORT'):
    args += ['--db_port', os.environ['PORT']]
if os.environ.get('USER'):
    args += ['--db_user', os.environ['USER']]
if os.environ.get('PASSWORD'):
    args += ['--db_password', os.environ['PASSWORD']]
odoo.tools.config.parse_config(args)
cr = odoo.registry('supplychain').cursor()
env = Environment(cr, SUPERUSER_ID, {})

sess = env['ai.chat.session'].create({})
print('ai.chat.session created id:', sess.id)

print('suppliers count      :', len(sess._tool_query_suppliers(10)))
print('stock sample count   :', len(sess._tool_query_stock(limit=10)))
print('low stock count      :', len(sess._tool_query_low_stock(10)))
print('expiring lots count  :', len(sess._tool_query_expiring_lots(30, 10)))
print('purchase orders count:', len(sess._tool_query_purchase_orders(limit=10)))

# Security: whitelist must REJECT an unknown/out-of-contract tool
bad = sess._dispatch_tool('os_system_rm', {})
print('whitelist rejects unknown tool:', '拒绝' in bad.get('error', '') or 'error' in bad)

# Fallback answer works without an LLM key (graceful degradation)
ans = sess.ask('库存怎么样')
print('ask() returns non-empty (degraded):', bool(ans))
cr.close()
