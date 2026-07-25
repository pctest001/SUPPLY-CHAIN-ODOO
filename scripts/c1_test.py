"""C1 自测：采购申请 PR -> 采购订单 PO 状态机与转换。

运行（容器内）：
  docker compose run --rm -v "$PWD/scripts:/opt/scripts" odoo python3 /opt/scripts/c1_test.py

以 SUPERUSER 连接 supplychain 库，模拟完整业务流并断言关键不变量。
本脚本可重复运行：开头与结尾都会清理所有 "C1自测" 标签的测试数据，不污染演示库。
"""
import os
import sys
import odoo
from odoo.api import Environment
from odoo import SUPERUSER_ID
from odoo.exceptions import UserError

args = ['-d', 'supplychain']
for envk, flag in [('HOST', '--db_host'), ('PORT', '--db_port'),
                   ('USER', '--db_user'), ('PASSWORD', '--db_password')]:
    if os.environ.get(envk):
        args += [flag, os.environ[envk]]
odoo.tools.config.parse_config(args)

cr = odoo.registry('supplychain').cursor()
env = Environment(cr, SUPERUSER_ID, {})

fails = []


def check(cond, msg):
    print(('PASS' if cond else 'FAIL') + ' - ' + msg)
    if not cond:
        fails.append(msg)


def purge_c1_data():
    """清理所有 C1自测 标签的残留数据，保证可重复运行。"""
    partners = env['res.partner'].search([('name', 'like', 'C1自测%')])
    for p in partners:
        for po in env['purchase.order'].search([('partner_id', '=', p.id)]):
            try:
                if po.state != 'cancel':
                    po.button_cancel()
                po.unlink()
            except Exception:
                pass
        for pr in env['sc.purchase.request'].search([('partner_id', '=', p.id)]):
            try:
                pr.unlink()
            except Exception:
                pass
        try:
            p.unlink()
        except Exception:
            pass
    for prod in env['product.product'].search([('name', 'like', 'C1自测%')]):
        try:
            prod.unlink()
        except Exception:
            pass


purge_c1_data()  # 运行前先清，避免历史残留干扰

# ---- 准备测试数据 ----
wh = env['stock.warehouse'].search([], limit=1)
check(bool(wh), '存在可用仓库(作为收货仓)')
company = wh.company_id

supplier = env['res.partner'].create({'name': 'C1自测供应商', 'supplier_rank': 1})
check(bool(supplier), '供应商可用(用于生成 PO)')

prod = env['product.product'].create({'name': 'C1自测物料'})
uom = prod.uom_id or env.ref('uom.product_uom_unit')
check(bool(prod), '测试物料已创建')

# ---- 创建 PR（草稿）----
pr = env['sc.purchase.request'].create({
    'partner_id': supplier.id,
    'company_id': company.id,
    'warehouse_id': wh.id,
    'line_ids': [(0, 0, {
        'product_id': prod.id,
        'product_uom_qty': 10.0,
        'product_uom': uom.id,
        'price_unit': 5.0,
    })],
})
check(pr.name.startswith('PR/'), 'PR 单号已通过序列生成: %s' % pr.name)
check(pr.state == 'draft', '初始状态为草稿')
check(len(pr.line_ids) == 1, 'PR 含 1 条明细')

# ---- 拦截：草稿态不可直接生成 PO ----
guard_ok = False
try:
    pr.action_generate_po()
except UserError:
    guard_ok = True
check(guard_ok, '状态机拦截：草稿态禁止生成 PO(UserError)')

# ---- 提交 ----
pr.action_submit()
check(pr.state == 'confirmed', '提交后状态=已提交')

# ---- 生成 PO ----
res = pr.action_generate_po()
check(pr.state == 'done', '生成 PO 后状态=已转PO')
check(len(pr.po_ids) == 1, 'PR 关联到 1 张 PO')
po = pr.po_ids[0]
check(po.partner_id.id == supplier.id, 'PO 供应商与 PR 一致')
check(po.origin == pr.name, 'PO origin 回写 PR 单号')
check(len(po.order_line) == 1, 'PO 含 1 条订单行')
pol = po.order_line[0]
check(pol.product_id.id == prod.id, 'PO 订单行物料与 PR 一致')
check(abs(pol.product_qty - 10.0) < 1e-6, 'PO 订单行数量与 PR 一致')
check(pol.price_unit == 5.0, 'PO 订单行预估单价已带入')
check(po.picking_type_id.id == wh.in_type_id.id, 'PO 收货作业类型指向收货仓入向')

# ---- 已转PO 不可再次生成 ----
dup_guard = False
try:
    pr.action_generate_po()
except UserError:
    dup_guard = True
check(dup_guard, '状态机拦截：已转PO 不可重复生成')

# ---- 清理测试数据（避免污染演示库）----
purge_c1_data()
cr.commit()
cr.close()

print('\n==== C1 自测结果 ====')
if fails:
    print('FAILED (%d): %s' % (len(fails), fails))
    sys.exit(1)
print('ALL PASSED')
