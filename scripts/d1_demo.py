# -*- coding: utf-8 -*-
# D1 演示：流程制造物料「入库(+100, 批次/效期) → 出库(-30, 指定批次)」
# 运行：docker compose run --rm odoo odoo shell -d supplychain < scripts/d1_demo.py
# 真实提交（不回滚），供在 UI 中查看 入库/出库 作业与库存量化。可重复运行（幂等）。
from odoo import fields
import datetime

def validate(picking):
    # 程序化校验出库时跳过原生 SMS 确认向导（演示/测试不真正发短信），直接走立即转移向导
    res = picking.with_context(skip_sms=True).button_validate()
    if isinstance(res, dict) and res.get('res_model') in (
            'stock.immediate.transfer', 'stock.backorder.confirmation'):
        env[res['res_model']].browse(res['res_id']).process()
    picking.flush_recordset()

wh = env['stock.warehouse'].search([], limit=1)
sup = env['res.partner'].search([('supplier_rank', '>', 0)], limit=1)
if not sup:
    sup = env['res.partner'].create({'name': '演示供应商', 'supplier_rank': 1})
cust = env['res.partner'].search([('customer_rank', '>', 0)], limit=1)
if not cust:
    cust = env['res.partner'].create({'name': '演示客户', 'customer_rank': 1})

# 流程制造物料（自动批次+效期+可库存），幂等复用
prod = env['product.product'].search([('name', '=', '演示流程制造物料-D1')], limit=1)
if not prod:
    prod = env['product.product'].create({
        'name': '演示流程制造物料-D1', 'type': 'consu',
        'is_process_mfg': True, 'list_price': 12.0,
    })

# 1) 入库：幂等——若批次已存在则跳过；否则审批 PO → 收货 +100
lot = env['stock.lot'].search(
    [('name', '=', 'BATCH-DEMO-D1'), ('product_id', '=', prod.id)], limit=1)
if not lot:
    po = env['purchase.order'].create({
        'partner_id': sup.id, 'picking_type_id': wh.in_type_id.id,
        'order_line': [(0, 0, {
            'product_id': prod.id, 'name': prod.name,
            'product_qty': 100.0, 'product_uom': prod.uom_id.id,
            'date_planned': fields.Date.today(), 'price_unit': 12.0,
        })],
    })
    po.write({'approval_state': 'approved'})
    po.button_confirm()
    pin = po.picking_ids[0]
    mlin = pin.move_line_ids[0]
    exp = fields.Datetime.now() + datetime.timedelta(days=365)
    mlin.write({'lot_name': 'BATCH-DEMO-D1', 'expiration_date': exp, 'quantity': 100.0})
    validate(pin)
    lot = env['stock.lot'].search(
        [('name', '=', 'BATCH-DEMO-D1'), ('product_id', '=', prod.id)], limit=1)
else:
    pin = env['stock.picking'].search(
        [('picking_type_id.code', '=', 'incoming'),
         ('move_ids.product_id', '=', prod.id)], limit=1)

# 2) 出库：幂等——若已有未完成的同物料出库则补全并校验，否则新建
pout = env['stock.picking'].search([
    ('picking_type_id.code', '=', 'outgoing'),
    ('move_ids.product_id', '=', prod.id),
    ('state', '!=', 'done'),
], limit=1)
if not pout:
    pout = env['stock.picking'].create({
        'partner_id': cust.id, 'picking_type_id': wh.out_type_id.id,
        'location_id': wh.lot_stock_id.id,
        'location_dest_id': env.ref('stock.stock_location_customers').id,
        'move_ids': [(0, 0, {
            'name': prod.name, 'product_id': prod.id,
            'product_uom_qty': 30.0, 'product_uom': prod.uom_id.id,
            'location_id': wh.lot_stock_id.id,
            'location_dest_id': env.ref('stock.stock_location_customers').id,
            'quantity': 30.0,
        })],
    })
    pout.action_confirm()
mlout = pout.move_line_ids.filtered(lambda m: m.product_id == prod)[:1]
if mlout and not mlout.lot_id:
    mlout.write({'lot_id': lot.id, 'quantity': 30.0})
if pout.state != 'done':
    validate(pout)

# 库存量化结果
q = env['stock.quant'].search([('product_id', '=', prod.id), ('lot_id', '=', lot.id)])
qs = q.filtered(lambda x: x.quantity > 0 and x.location_id.usage == 'internal')
print('入库单:', pin.name if pin else '—', '| 状态:', pin.state if pin else '—')
print('出库单:', pout.name, '| 状态:', pout.state)
print('批次:', lot.name, '| 效期:', lot.expiration_date)
print('WH/Stock 当前库存(按批次):', qs.quantity if qs else '—')
env.cr.commit()
print('(演示数据已提交，可在 UI：库存 → 作业 / 库存 → 按批次 查看)')
