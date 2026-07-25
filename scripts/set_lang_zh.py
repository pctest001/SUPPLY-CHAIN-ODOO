# 将 Odoo 数据库默认语言 + admin 用户语言切换为简体中文 (zh_CN)
import odoo
from odoo.api import Environment
from odoo import SUPERUSER_ID

odoo.tools.config.parse_config(['-d', 'supplychain', '--db_host', 'db',
                                '--db_port', '5432', '--db_user', 'odoo', '--db_password', 'odoo'])
cr = odoo.registry('supplychain').cursor()
env = Environment(cr, SUPERUSER_ID, {})

admin = env.ref('base.user_admin')
print('切换前 admin.lang :', admin.lang)

# 1) 确保 zh_CN 语言存在并激活
lang = env['res.lang'].with_context(active_test=False).search([('code', '=', 'zh_CN')], limit=1)
if not lang:
    try:
        env['res.lang']._activate_lang('zh_CN')
        print('zh_CN 已激活（_activate_lang）')
    except Exception as e:
        print('  _activate_lang 失败:', e)
else:
    if not lang.active:
        lang.active = True
        print('zh_CN 重新激活')
    else:
        print('zh_CN 已存在且激活')

# 2) 尽力加载中文翻译包（需联网下载，失败不影响语言切换）
try:
    wiz = env['base.language.install'].create({'lang': 'zh_CN', 'overwrite': False})
    wiz.lang_install()
    print('中文翻译包加载完成')
except Exception as e:
    print('中文翻译包加载跳过（可能离线）:', e)

# 3) 设置 admin 用户语言 + 数据库默认语言
admin.write({'lang': 'zh_CN'})
env['ir.config_parameter'].set_param('lang', 'zh_CN')
env.cr.commit()
print('切换后 admin.lang :', admin.lang)
print('DB 默认语言(lang) :', env['ir.config_parameter'].get_param('lang'))
cr.close()
