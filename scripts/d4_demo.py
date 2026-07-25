# -*- coding: utf-8 -*-
"""D4 负库存 / 超额收货拦截 —— 持久化演示脚本。

与 d4_test.py 不同，本脚本会 commit 持久化，生成的演示数据可在 Odoo UI 复现：
  1) 负库存拦截演示：华南工厂出向交付单（D4-NEG-DEMO），来源仅有 30，发出 100 -> 验证被 D4 拦截
  2) 超额收货拦截演示：采购订单（D4-PO-OVER-001，订购 5），到货 50 -> 验证被 D4 拦截

幂等：重跑不会重复创建同一条演示单。
"""
from odoo import fields
from odoo.exceptions import UserError

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


def on_hand(product, loc, lot=None):
    dom = [('product_id', '=', product.id), ('location_id', '=', loc.id)]
    if lot:
        dom.append(('lot_id', '=', lot.id))
    return sum(Quant.search(dom).mapped('quantity'))


print('=== D4 持久化演示开始 ===')

# ========== 1) 负库存拦截演示 ==========
neg_demo = Product.search([('name', '=', 'D4演示-负库存物料')], limit=1)
if not neg_demo:
    neg_demo = Product.create({
        'name': 'D4演示-负库存物料', 'type': 'consu', 'is_storable': True,
        'tracking': 'none', 'is_process_mfg': False, 'company_id': _comp.id,
    })
    # 来源仅有 30
    Quant.create({'product_id': neg_demo.id, 'location_id': src_loc.id,
                  'inventory_quantity': 30}).action_apply_inventory()
    print('  创建演示物料「D4演示-负库存物料」，来源库存 = 30')

# 幂等：已存在演示单则跳过
neg_pick = Picking.search([('origin', '=', 'D4-NEG-DEMO')], limit=1)
if not neg_pick:
    neg_pick = Picking.create({
        'picking_type_id': out_type.id, 'location_id': src_loc.id,
        'location_dest_id': cust_loc.id, 'company_id': _comp.id,
        'origin': 'D4-NEG-DEMO',
    })
    env['stock.move'].create({
        'name': neg_demo.name, 'product_id': neg_demo.id,
        'product_uom_qty': 100, 'product_uom': neg_demo.uom_id.id,
        'location_id': src_loc.id, 'location_dest_id': cust_loc.id,
        'picking_id': neg_pick.id, 'company_id': _comp.id,
    })
    neg_pick.action_confirm()
    neg_pick.move_line_ids[0].write({'quantity': 100})   # 发出 100 > 现有 30
    print('  创建出向交付单 %s，发出量=100（现有库存=30）' % neg_pick.name)

# 演示拦截：尝试验证，应被 D4 拒
try:
    neg_pick.button_validate()
    print('  [异常] 负库存单竟然验证通过！')
except UserError as e:
    print('  D4 拦截成功：', e.args[0])
print('  演示单状态=%s，来源库存仍=%s（未出库）'
      % (neg_pick.state, on_hand(neg_demo, src_loc)))

# ========== 2) 超额收货拦截演示 ==========
supplier = env['res.partner'].search([('name', '=', 'D4演示供应商')], limit=1)
if not supplier:
    supplier = env['res.partner'].create({
        'name': 'D4演示供应商', 'supplier_rank': 1, 'company_id': _comp.id,
    })

po_demo = Product.search([('name', '=', 'D4演示-超额收货物料')], limit=1)
if not po_demo:
    po_demo = Product.create({
        'name': 'D4演示-超额收货物料', 'type': 'consu', 'is_storable': True,
        'tracking': 'none', 'is_process_mfg': False, 'company_id': _comp.id,
    })

po = env['purchase.order'].search([('name', '=', 'D4-PO-OVER-001')], limit=1)
if not po:
    po = env['purchase.order'].create({
        'name': 'D4-PO-OVER-001', 'partner_id': supplier.id,
        'company_id': _comp.id,
        'order_line': [(0, 0, {
            'product_id': po_demo.id, 'product_qty': 5, 'price_unit': 5.0,
            'product_uom': po_demo.uom_id.id, 'date_planned': fields.Datetime.now(),
        })],
    })
    po.write({'approval_state': 'approved'})
    po.button_confirm()   # 生成入向收货作业
    print('  创建采购订单 %s，订购量=5，已审批并确认' % po.name)

# 找到入向收货单，把到货量改成 50（> 订购 5）
recv = po.picking_ids.filtered(lambda p: p.picking_type_id.code == 'incoming')
if recv:
    recv = recv[0]
    recv.move_line_ids[0].write({'quantity': 50})   # 到货 50 > 订购 5
    print('  入向收货单 %s 到货量=50（订购=5）' % recv.name)
    try:
        recv.button_validate()
        print('  [异常] 超额收货单竟然验证通过！')
    except UserError as e:
        print('  D4 拦截成功：', e.args[0])
    print('  收货单状态=%s' % recv.state)

env.cr.commit()
print('=== D4 持久化演示完成（已 commit）===')
