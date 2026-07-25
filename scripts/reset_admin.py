#!/usr/bin/env python3
"""在 odoo 容器内（重新）设置管理员凭据 —— 可重复执行，不削弱安全机制。

用法（在仓库根目录执行）：
  docker compose run --rm -v ./scripts:/scripts \
    -e ADMIN_LOGIN=admin@example.com -e ADMIN_PASSWORD=admin \
    odoo python3 /scripts/reset_admin.py

默认：admin@example.com / admin。会读取服务环境变量 HOST/PORT/USER/PASSWORD 连接数据库。
密码通过 Odoo 自身 _set_password() 哈希（pbkdf2_sha512），与登录校验完全一致。
"""
import os
import odoo
from odoo import SUPERUSER_ID
from odoo.api import Environment

DB = os.environ.get('DB_NAME', 'supplychain')


def main():
    args = ['-d', DB, '-c', '/etc/odoo/odoo.conf']
    if os.environ.get('HOST'):
        args += ['--db_host', os.environ['HOST']]
    if os.environ.get('PORT'):
        args += ['--db_port', os.environ['PORT']]
    if os.environ.get('USER'):
        args += ['--db_user', os.environ['USER']]
    if os.environ.get('PASSWORD'):
        args += ['--db_password', os.environ['PASSWORD']]
    odoo.tools.config.parse_config(args)

    with odoo.registry(DB).cursor() as cr:
        env = Environment(cr, SUPERUSER_ID, {})
        admin = env.ref('base.user_admin', raise_if_not_found=False)
        if not admin:
            print('未找到 admin 用户，请先执行初始化（./init.sh）。')
            return
        login = os.environ.get('ADMIN_LOGIN', 'admin@example.com')
        pwd = os.environ.get('ADMIN_PASSWORD', 'admin')
        admin.write({'login': login})
        if admin.partner_id:
            admin.partner_id.email = login
        # 用 write({'password': 明文}) 让 Odoo 单次 pbkdf2 哈希（避免二次加密）
        admin.write({'password': pwd})
        cr.commit()
        print('管理员凭据已重置: %s / %s' % (login, pwd))


if __name__ == '__main__':
    main()
