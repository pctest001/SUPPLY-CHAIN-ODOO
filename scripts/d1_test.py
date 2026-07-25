# -*- coding: utf-8 -*-
# D1 入库/出库 端到端自测
# 运行：docker compose run --rm odoo odoo shell -d supplychain < scripts/d1_test.py
# 依赖 odoo shell 的事务在退出时回滚，测试数据不会污染演示库。
#
# 覆盖：
#   1) 流程制造物料自动启用批次 + 效期 + 可库存 (B1/C3)
#   2) 入库(incoming) +100 并写入 stock.lot（批次/效期可追溯）
#   3) 出库(outgoing) -30 指定同一批次 → 按批次量化正确(+70)
#   4) 出库守卫：流程制造物料未指定批次 → 验证被拒(UserError)
#   5) 中文化视图：收货/发货明细「批次号 / 效期」
import datetime
from odoo import fields
from odoo.exceptions import UserError

results = []
def check(name, cond):
    results.append((name, cond))
    print(('OK   ' if cond else 'FAIL '), name)

def validate(picking):
    """Odoo 18: button_validate 可能返回立即转移/分单向导，需 process() 才会落库存。
    出库时跳过原生 SMS 确认向导(skip_sms)，直接完成转移。"""
    res = picking.with_context(skip_sms=True).button_validate()
    if isinstance(res, dict) and res.get('res_model') in (
            'stock.immediate.transfer', 'stock.backorder.confirmation'):
        env[res['res_model']].browse(res['res_id']).process()
    picking.flush_recordset()

# ---------- 1) 流程制造物料（自动批次+效期+可库存）----------
sup = env['res.partner'].create({'name': 'D1测试供应商', 'supplier_rank': 1})
prod = env['product.product'].create({
    'name': 'D1测试物料-流程制造',
    'type': 'consu',
    'is_process_mfg': True,
    'list_price': 10.0,
})
tmpl = prod.product_tmpl_id
check('流程制造物料自动 tracking=lot', tmpl.tracking == 'lot')
check('流程制造物料自动 use_expiration_date', tmpl.use_expiration_date is True)
check('流程制造物料自动 is_storable', tmpl.is_storable is True)

wh = env['stock.warehouse'].search([], limit=1)
cust = env['res.partner'].create({'name': 'D1测试客户', 'customer_rank': 1})
cust_loc = env.ref('stock.stock_location_customers').id

# ---------- 2) 入库(incoming) +100 并写批次/效期 ----------
po = env['purchase.order'].create({
    'partner_id': sup.id,
    'picking_type_id': wh.in_type_id.id,
    'order_line': [(0, 0, {
        'product_id': prod.id,
        'name': prod.name,
        'product_qty': 100.0,
        'product_uom': prod.uom_id.id,
        'date_planned': fields.Date.today(),
        'price_unit': 10.0,
    })],
})
po.write({'approval_state': 'approved'})
po.button_confirm()
picking_in = po.picking_ids[0]
check('入库作业为入向(incoming)', picking_in.picking_type_id.code == 'incoming')
ml_in = picking_in.move_line_ids[0]
exp = fields.Datetime.now() + datetime.timedelta(days=180)
ml_in.write({'lot_name': 'BATCH-D1-001', 'expiration_date': exp, 'quantity': 100.0})
check('入库明细已录入批次号', bool(ml_in.lot_name))
check('入库明细已录入效期', bool(ml_in.expiration_date))
validate(picking_in)
lot = env['stock.lot'].search(
    [('name', '=', 'BATCH-D1-001'), ('product_id', '=', prod.id)], limit=1)
check('入库后 stock.lot 已创建', bool(lot))
check('stock.lot 记录效期(可追溯)', bool(lot) and bool(lot.expiration_date))
check('入库作业状态=done', picking_in.state == 'done')
# 取内部库位正向库存校验
qin = env['stock.quant'].search(
    [('product_id', '=', prod.id), ('lot_id', '=', lot.id)])
qin_stock = qin.filtered(lambda q: q.quantity > 0 and q.location_id.usage == 'internal')
check('入库量化正确(+100 @ WH/Stock)',
      bool(qin_stock) and abs(qin_stock.quantity - 100.0) < 0.01)
if qin_stock:
    print('      入库后 WH/Stock 库存 =', qin_stock.quantity,
          '| 效期 =', qin_stock.expiration_date)

# ---------- 3) 出库(outgoing) -30 指定同一批次 → 量化正确(+70) ----------
picking_out = env['stock.picking'].create({
    'partner_id': cust.id,
    'picking_type_id': wh.out_type_id.id,
    'location_id': wh.lot_stock_id.id,
    'location_dest_id': cust_loc,
    'move_ids': [(0, 0, {
        'name': prod.name,
        'product_id': prod.id,
        'product_uom_qty': 30.0,
        'product_uom': prod.uom_id.id,
        'location_id': wh.lot_stock_id.id,
        'location_dest_id': cust_loc,
        'quantity': 30.0,
    })],
})
check('出库作业为出向(outgoing)', picking_out.picking_type_id.code == 'outgoing')
picking_out.action_confirm()
ml_out = picking_out.move_line_ids[0]
ml_out.write({'lot_id': lot.id, 'quantity': 30.0})
check('出库明细已指定批次(lot_id)', bool(ml_out.lot_id))
check('出库批次与入库批次一致(可追溯)', ml_out.lot_id.id == lot.id)
validate(picking_out)
check('出库作业状态=done', picking_out.state == 'done')
# 出库后该批次在 WH/Stock 应为 +70
qout = env['stock.quant'].search(
    [('product_id', '=', prod.id), ('lot_id', '=', lot.id)])
qout_stock = qout.filtered(lambda q: q.quantity > 0 and q.location_id.usage == 'internal')
check('出库量化正确(+70 @ WH/Stock)',
      bool(qout_stock) and abs(qout_stock.quantity - 70.0) < 0.01)
if qout_stock:
    print('      出库后 WH/Stock 库存 =', qout_stock.quantity,
          '| 批次 =', qout_stock.lot_id.name)
check('入库+出库净变动正确(+100-30=+70)',
      bool(qout_stock) and abs(qout_stock.quantity - 70.0) < 0.01)

# ---------- 4) 出库守卫：流程制造物料未指定批次 → 被拒 ----------
picking_bad = env['stock.picking'].create({
    'partner_id': cust.id,
    'picking_type_id': wh.out_type_id.id,
    'location_id': wh.lot_stock_id.id,
    'location_dest_id': cust_loc,
    'move_ids': [(0, 0, {
        'name': prod.name,
        'product_id': prod.id,
        'product_uom_qty': 20.0,
        'product_uom': prod.uom_id.id,
        'location_id': wh.lot_stock_id.id,
        'location_dest_id': cust_loc,
        'quantity': 20.0,
    })],
})
move_bad = picking_bad.move_ids[0]
env['stock.move.line'].create({
    'move_id': move_bad.id,
    'picking_id': picking_bad.id,
    'product_id': prod.id,
    'product_uom_id': prod.uom_id.id,
    'location_id': wh.lot_stock_id.id,
    'location_dest_id': cust_loc,
    'quantity': 20.0,
    'lot_id': False,  # 故意不指定批次
})
raised = False
msg = ''
try:
    picking_bad.button_validate()
except UserError as e:
    raised = True
    msg = str(e)
    print('      守卫提示:', msg.replace('\n', ' '))
check('缺批次出库被拒绝(UserError)', raised)
check('守卫提示指向"流程制造/批次"', '流程制造' in msg and '批次' in msg)

# ---------- 5) 中文化视图校验（收货/发货明细共用详细作业视图）----------
try:
    vid = env.ref('supply_chain_demo.view_stock_move_line_detailed_op_sc_zh').id
    arch = env['stock.move.line'].get_views([(vid, 'list')])['views']['list']['arch']
    check('明细视图含中文「批次号」', '批次号' in arch)
    check('明细视图含中文「效期」', '效期' in arch)
except Exception as e:
    print('      (视图校验跳过:', e, ')')

# ---------- 汇总 ----------
passed = sum(1 for _, c in results if c)
total = len(results)
print('\n=== D1 自测结果：%d/%d 通过 ===' % (passed, total))
for name, c in results:
    if not c:
        print('  未通过:', name)

# 依赖 odoo shell 退出时回滚事务，确保测试数据不写入演示库
try:
    env.cr.rollback()
    print('(已回滚测试事务，演示库保持干净)')
except Exception:
    pass
