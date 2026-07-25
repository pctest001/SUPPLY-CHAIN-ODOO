from . import models
from odoo import SUPERUSER_ID
import os


def _post_init_set_admin(env):
    """可复现的管理员初始化：通过 Odoo 自身哈希设置已知 login / 密码。

    Odoo 18 的 post_init_hook 签名是 (env)。一条命令即可得到一个「可直接登录」的库，
    无需任何手动补密码的售后步骤，也不会为了绕过登录锁定而去削弱安全机制
    （如关闭 base.login_cooldown）。

    默认凭据：admin@example.com / admin
    可用环境变量覆盖：ADMIN_LOGIN / ADMIN_PASSWORD
    """
    admin = env.ref('base.user_admin', raise_if_not_found=False)
    if not admin:
        return
    login = os.environ.get('ADMIN_LOGIN', 'admin@example.com')
    pwd = os.environ.get('ADMIN_PASSWORD', 'admin')
    # login 字段即登录页的「Email」；同时同步伙伴邮箱，保证档案完整
    admin.write({'login': login})
    if admin.partner_id:
        admin.partner_id.email = login
    # 关键：用 write({'password': 明文}) 让 Odoo 在写入时自动走
    # 内部 pbkdf2_sha512(600000) 哈希（单次），避免手写哈希不匹配，
    # 也避免「赋值 + 显式 _set_password()」导致的二次加密（那样永远校验不过）。
    admin.write({'password': pwd})

    # C3：收货作业类型开启「详细作业」，使批次/效期录入界面可用
    # （原生 Receipts 类型默认 show_operations=False，会导致不显示详细作业页签）
    env['stock.picking.type'].search([('code', '=', 'incoming')]).write(
        {'show_operations': True})

    # 多公司兼容：Vendors / Customers 虚拟库位默认归属「默认公司」，
    # 会导致非默认公司(华南/华东工厂)的仓库入/出库因公司不一致被 _check_company 拒绝。
    # 改为共享(company_id=False)后，任意公司仓库均可使用。
    for xmlid in ('stock.stock_location_suppliers', 'stock.stock_location_customers'):
        loc = env.ref(xmlid, raise_if_not_found=False)
        if loc and loc.company_id:
            loc.write({'company_id': False})
    env.cr.commit()
