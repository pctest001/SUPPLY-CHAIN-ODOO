# -*- coding: utf-8 -*-
"""D4 负库存 / 超额收货拦截 端到端自测。

通过 odoo shell 执行，事务退出自动回滚，不污染演示库。
覆盖：
  1) 出向超量(发出量>现有库存) -> D4 负库存拦截(UserError)，库存不变
  2) 出向正常(发出量<=现有库存) -> 成功(done)，库存正确减少
  3) 内部调拨超量 -> D4 负库存拦截(UserError)
  4) 入向超额收货(累计>订购量) -> D4 超额收货拦截(UserError)，作业未 done
  5) 入向正常收货(<=订购量) -> 成功(done)，库存增加
"""
from odoo import fields
from odoo.exceptions import UserError

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
Quant = env['stock.quant']
Picking = env['stock.picking']
PickingType = env['stock.picking.type']

wh = env['stock.warehouse'].search([('company_id', '=', _comp.id)], limit=1)
src_loc = wh.lot_stock_id                 # HNC2/Stock
cust_loc = env.ref('stock.stock_location_customers')
vendor_loc = env.ref('stock.stock_location_suppliers')
out_type = PickingType.search(
    [('code', '=', 'outgoing'), ('warehouse_id', '=', wh.id)], limit=1)
in_type = PickingType.search(
    [('code', '=', 'incoming'), ('warehouse_id', '=', wh.id)], limit=1)
hncf_type = PickingType.search([('sequence_code', '=', 'HNCF')], limit=1)

check(bool(_comp) and bool(wh) and bool(out_type) and bool(in_type) and bool(hncf_type),
      '测试环境就位(华南工厂/仓库/出向/入向/HNCF类型)')


def on_hand(product, loc, lot=None):
    dom = [('product_id', '=', product.id), ('location_id', '=', loc.id)]
    if lot:
        dom.append(('lot_id', '=', lot.id))
    return sum(Quant.search(dom).mapped('quantity'))


def make_out_picking(product, qty):
    p = Picking.create({
        'picking_type_id': out_type.id, 'location_id': src_loc.id,
        'location_dest_id': cust_loc.id, 'company_id': _comp.id,
    })
    env['stock.move'].create({
        'name': product.name, 'product_id': product.id,
        'product_uom_qty': qty, 'product_uom': product.uom_id.id,
        'location_id': src_loc.id, 'location_dest_id': cust_loc.id,
        'picking_id': p.id, 'company_id': _comp.id,
    })
    p.action_confirm()
    return p


# ---- 物料：非流程制造、非批次追踪（避免 C3/D1 干扰，聚焦 D4）----
neg_prod = Product.create({
    'name': 'D4测试-普通物料A', 'type': 'consu', 'is_storable': True,
    'tracking': 'none', 'is_process_mfg': False, 'company_id': _comp.id,
})
Quant.create({'product_id': neg_prod.id, 'location_id': src_loc.id,
              'inventory_quantity': 50}).action_apply_inventory()
check(on_hand(neg_prod, src_loc) == 50, '普通物料A 初始库存 50(来源仓)')

# ---- 测试 1：出向超量 -> 负库存拦截 ----
p1 = make_out_picking(neg_prod, 1000)
p1.move_line_ids[0].write({'quantity': 1000})   # 用户手动填超量
blocked1 = False
try:
    p1.button_validate()
except UserError as e:
    blocked1 = True
    print('   拦截提示:', e.args[0])
check(blocked1, '出向超量(1000>50)被 D4 负库存拦截(UserError)')
check(p1.state != 'done', '被拦截后作业未变成 done')
check(on_hand(neg_prod, src_loc) == 50, '被拦截后库存保持 50(未发生出库)')

# ---- 测试 2：出向正常 -> 成功（独立物料，避免与测试1的预留互相干扰）----
neg_prod2 = Product.create({
    'name': 'D4测试-普通物料A2', 'type': 'consu', 'is_storable': True,
    'tracking': 'none', 'is_process_mfg': False, 'company_id': _comp.id,
})
Quant.create({'product_id': neg_prod2.id, 'location_id': src_loc.id,
              'inventory_quantity': 50}).action_apply_inventory()
check(on_hand(neg_prod2, src_loc) == 50, '普通物料A2 初始库存 50(来源仓)')
p2 = make_out_picking(neg_prod2, 30)
p2.move_line_ids[0].write({'quantity': 30})
st2 = validate(p2)
check(st2 == 'done', '出向正常(30<=50)成功(done)')
check(on_hand(neg_prod2, src_loc) == 20, '正常出库后库存 50->20')

# ---- 测试 3：内部调拨超量 -> 负库存拦截 ----
int_prod = Product.create({
    'name': 'D4测试-普通物料B', 'type': 'consu', 'is_storable': True,
    'tracking': 'none', 'is_process_mfg': False, 'company_id': _comp.id,
})
Quant.create({'product_id': int_prod.id, 'location_id': src_loc.id,
              'inventory_quantity': 40}).action_apply_inventory()
check(on_hand(int_prod, src_loc) == 40, '普通物料B 初始库存 40(来源仓)')

pi = Picking.create({
    'picking_type_id': hncf_type.id, 'location_id': src_loc.id,
    'location_dest_id': hncf_type.default_location_dest_id.id,
    'company_id': _comp.id,
})
env['stock.move'].create({
    'name': int_prod.name, 'product_id': int_prod.id, 'product_uom_qty': 1000,
    'product_uom': int_prod.uom_id.id, 'location_id': src_loc.id,
    'location_dest_id': hncf_type.default_location_dest_id.id,
    'picking_id': pi.id, 'company_id': _comp.id,
})
pi.action_confirm()
pi.move_line_ids[0].write({'quantity': 1000})
blocked3 = False
try:
    pi.button_validate()
except UserError as e:
    blocked3 = True
    print('   拦截提示:', e.args[0])
check(blocked3, '内部调拨超量(1000>40)被 D4 负库存拦截(UserError)')
check(pi.state != 'done', '内部调拨被拦截后未 done')
check(on_hand(int_prod, src_loc) == 40, '内部调拨被拦截后库存保持 40')

# ---- 测试 4 & 5：超额收货（绑定采购订单行）----
supplier = env['res.partner'].create({
    'name': 'D4测试-供应商', 'supplier_rank': 1, 'company_id': _comp.id,
})
po_prod = Product.create({
    'name': 'D4测试-采购物料', 'type': 'consu', 'is_storable': True,
    'tracking': 'none', 'is_process_mfg': False, 'company_id': _comp.id,
})
# 订购 10
po = env['purchase.order'].create({
    'partner_id': supplier.id, 'company_id': _comp.id,
    'order_line': [(0, 0, {
        'product_id': po_prod.id, 'product_qty': 10, 'price_unit': 5.0,
        'product_uom': po_prod.uom_id.id, 'date_planned': fields.Datetime.now(),
    })],
})
po_line = po.order_line[0]
check(po_line.product_qty == 10, '采购订单行订购量 = 10')


def make_in_picking(po_line_rec, qty):
    p = Picking.create({
        'picking_type_id': in_type.id, 'location_id': vendor_loc.id,
        'location_dest_id': src_loc.id, 'company_id': _comp.id,
    })
    mv = env['stock.move'].create({
        'name': po_line_rec.product_id.name, 'product_id': po_line_rec.product_id.id,
        'product_uom_qty': qty, 'product_uom': po_line_rec.product_uom.id,
        'location_id': vendor_loc.id, 'location_dest_id': src_loc.id,
        'picking_id': p.id, 'company_id': _comp.id,
        'purchase_line_id': po_line_rec.id,
    })
    p.action_confirm()
    p.move_line_ids[0].write({'quantity': qty})
    return p


# 测试 4：到货 20 > 订购 10 -> 超额收货拦截
ph = make_in_picking(po_line, 20)
blocked4 = False
try:
    ph.button_validate()
except UserError as e:
    blocked4 = True
    print('   拦截提示:', e.args[0])
check(blocked4, '入向超额收货(20>10)被 D4 超额收货拦截(UserError)')
check(ph.state != 'done', '超额收货被拦截后作业未 done')

# 测试 5：到货 8 <= 订购 10 -> 成功
pl2 = env['purchase.order.line'].create({
    'order_id': po.id, 'product_id': po_prod.id, 'product_qty': 10,
    'price_unit': 5.0, 'product_uom': po_prod.uom_id.id,
    'date_planned': fields.Datetime.now(),
})
pok = make_in_picking(pl2, 8)
st5 = validate(pok)
check(st5 == 'done', '入向正常收货(8<=10)成功(done)')
check(on_hand(po_prod, src_loc) == 8, '正常收货后库存 +8')

print('\nD4 自测结果: %d PASS / %d FAIL' % (PASS, FAIL))
