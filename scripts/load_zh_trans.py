# 加载简体中文翻译包（Odoo 18: base.language.install 用 lang_ids 多对多）
import odoo
from odoo.api import Environment
from odoo import SUPERUSER_ID

odoo.tools.config.parse_config(['-d', 'supplychain', '--db_host', 'db',
                                '--db_port', '5432', '--db_user', 'odoo', '--db_password', 'odoo'])
cr = odoo.registry('supplychain').cursor()
env = Environment(cr, SUPERUSER_ID, {})

zh = env['res.lang'].with_context(active_test=False).search([('code', '=', 'zh_CN')], limit=1)
if not zh:
    print('zh_CN 语言不存在，无法加载')
else:
    try:
        wiz = env['base.language.install'].create({'lang_ids': [(4, zh.id)], 'overwrite': False})
        wiz.lang_install()
        env.cr.commit()
        print('简体中文翻译包加载成功')
    except Exception as e:
        print('简体中文翻译包加载失败（可能离线/翻译服务器不可达）:', repr(e))
cr.close()
