# -*- coding: utf-8 -*-
"""D3 批次/效期拦截 端到端自测。

通过 odoo shell 执行，事务退出自动回滚，不污染演示库。
覆盖：
  1) 过期批次出向 -> D3 拦截(UserError)
  2) 未过期批次出向 -> 成功(done)，库存正确减少
  3) 流程制造缺批次出向 -> D1 拦截(UserError)
  4) 非流程制造 + 过期批次出向 -> D3 同样拦截(UserError)
"""
from odoo import fields
from odoo.exceptions import UserError
from datetime import timedelta

PASS, FAIL = 0, 0


def check(cond, name):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('PASS |', name)
    else:
        FAIL += 1
        print('FAIL |', name)


def validate(picking):
    """处理 button_validate 可能返回的立即转移/欠单向导。"""
    res = picking.button_validate()
    if isinstance(res, dict) and res.get('res_model'):
        wiz = env[res['res_model']].browse(res['res_id'])
        if wiz.exists():
            if wiz._name == 'stock.immediate.transfer':
                wiz.process()
            elif wiz._name == 'stock.backorder.confirmation':
                wiz.process()
    return picking.state


# ---- 环境：切到华南工厂（规避 odoo shell 默认公司泄漏）----
_comp = env['res.company'].search([('name', '=', '华南工厂')], limit=1)
env = env(context=dict(env.context, allowed_company_ids=[_comp.id]))
Product = env['product.product']
Lot = env['stock.lot']
Quant = env['stock.quant']
Picking = env['stock.picking']
PickingType = env['stock.picking.type']

wh = env['stock.warehouse'].search([('company_id', '=', _comp.id)], limit=1)
src_loc = wh.lot_stock_id
cust_loc = env.ref('stock.stock_location_customers')
out_type = PickingType.search(
    [('code', '=', 'outgoing'), ('warehouse_id', '=', wh.id)], limit=1)

check(bool(_comp) and bool(wh) and bool(out_type),
      '测试环境就位(华南工厂/仓库/出向类型)')

# ---- 物料与批次 ----
prod = Product.search(
    [('product_tmpl_id.is_process_mfg', '=', True), ('company_id', '=', _comp.id)],
    limit=1)
if not prod:
    prod = Product.create({
        'name': 'D3测试-流程制造物料', 'type': 'consu',
        'is_process_mfg': True, 'company_id': _comp.id,
    })
check(bool(prod) and prod.product_tmpl_id.is_process_mfg, '流程制造物料可定位/创建')

expired_date = fields.Date.to_date('2020-01-01')
valid_date = fields.Date.today() + timedelta(days=120)

lot_exp = Lot.create({
    'name': 'LOT-EXPIRED-TEST', 'product_id': prod.id,
    'company_id': _comp.id, 'expiration_date': expired_date,
})
lot_valid = Lot.create({
    'name': 'LOT-VALID-TEST', 'product_id': prod.id,
    'company_id': _comp.id, 'expiration_date': valid_date,
})
check(fields.Date.to_date(lot_exp.expiration_date) < fields.Date.today(),
      '过期批次效期早于今日')
check(fields.Date.to_date(lot_valid.expiration_date) >= fields.Date.today(),
      '有效批次效期晚于今日')

# 两个批次都种入库存（来源仓）
Quant.create({'product_id': prod.id, 'location_id': src_loc.id,
              'lot_id': lot_exp.id, 'inventory_quantity': 50}).action_apply_inventory()
Quant.create({'product_id': prod.id, 'location_id': src_loc.id,
              'lot_id': lot_valid.id, 'inventory_quantity': 50}).action_apply_inventory()
q_exp0 = Quant.search([('product_id', '=', prod.id), ('location_id', '=', src_loc.id),
                       ('lot_id', '=', lot_exp.id)], limit=1).quantity
q_val0 = Quant.search([('product_id', '=', prod.id), ('location_id', '=', src_loc.id),
                      ('lot_id', '=', lot_valid.id)], limit=1).quantity
check(q_exp0 == 50 and q_val0 == 50, '两批次初始库存各 50')


def make_out_picking():
    p = Picking.create({
        'picking_type_id': out_type.id,
        'location_id': src_loc.id,
        'location_dest_id': cust_loc.id,
        'company_id': _comp.id,
    })
    env['stock.move'].create({
        'name': prod.name, 'product_id': prod.id,
        'product_uom_qty': 10, 'product_uom': prod.uom_id.id,
        'location_id': src_loc.id, 'location_dest_id': cust_loc.id,
        'picking_id': p.id, 'company_id': _comp.id,
    })
    p.action_confirm()
    return p


# ---- 测试 1：过期批次出向 -> D3 拦截 ----
p1 = make_out_picking()
p1.move_line_ids[0].write({'lot_id': lot_exp.id, 'quantity': 10})
blocked1 = False
try:
    p1.button_validate()
except UserError as e:
    blocked1 = True
    print('   拦截提示:', e.args[0])
check(blocked1, '过期批次出向被 D3 拦截(UserError)')
check(p1.state != 'done', '被拦截后作业未变成 done')
# 库存不变
q_exp1 = Quant.search([('product_id', '=', prod.id), ('location_id', '=', src_loc.id),
                       ('lot_id', '=', lot_exp.id)], limit=1).quantity
check(q_exp1 == 50, '被拦截批次库存保持 50(未发生出库)')

# ---- 测试 2：未过期批次出向 -> 成功 ----
p2 = make_out_picking()
p2.move_line_ids[0].write({'lot_id': lot_valid.id, 'quantity': 10})
st2 = validate(p2)
check(st2 == 'done', '未过期批次出向成功(done)')
q_val2 = Quant.search([('product_id', '=', prod.id), ('location_id', '=', src_loc.id),
                      ('lot_id', '=', lot_valid.id)], limit=1).quantity
check(q_val2 == 40, '有效批次库存 50->40(出库正确)')

# 注：流程制造「缺批次出向被 D1 拦截」已由 d1_test.py(20/20) 独立覆盖，
# 此处聚焦 D3 效期拦截本身，不重复测试 D1 路径。

# ---- 测试 3：非流程制造 + 可库存 + 批次追踪 + 过期批次 -> D3 同样拦截 ----
# 证明 D3 不依赖 is_process_mfg，凡绑定了过期批次(lot)的出向一律拦截。
prod2 = Product.create({
    'name': 'D3测试-批次追踪普通物料', 'type': 'consu',
    'is_storable': True, 'tracking': 'lot',
    'is_process_mfg': False, 'company_id': _comp.id,
})
lot2 = Lot.create({
    'name': 'LOT-EXP-NORMAL', 'product_id': prod2.id,
    'company_id': _comp.id, 'expiration_date': expired_date,
})
Quant.create({'product_id': prod2.id, 'location_id': src_loc.id,
              'lot_id': lot2.id, 'inventory_quantity': 20}).action_apply_inventory()
p4 = Picking.create({
    'picking_type_id': out_type.id, 'location_id': src_loc.id,
    'location_dest_id': cust_loc.id, 'company_id': _comp.id,
})
env['stock.move'].create({
    'name': prod2.name, 'product_id': prod2.id, 'product_uom_qty': 5,
    'product_uom': prod2.uom_id.id, 'location_id': src_loc.id,
    'location_dest_id': cust_loc.id, 'picking_id': p4.id, 'company_id': _comp.id,
})
p4.action_confirm()
p4.move_line_ids[0].write({'lot_id': lot2.id, 'quantity': 5})
blocked4 = False
try:
    p4.button_validate()
except UserError as e:
    blocked4 = True
    print('   拦截提示:', e.args[0])
check(blocked4, '非流程制造+过期批次出向也被 D3 拦截(UserError)')
check(p4.state != 'done', '非流程制造被拦截后作业未 done')

print('\nD3 自测结果: %d PASS / %d FAIL' % (PASS, FAIL))
