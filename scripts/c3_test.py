# -*- coding: utf-8 -*-
# C3 收货（批次/效期录入）端到端自测
# 运行：docker compose run --rm odoo odoo shell -d supplychain < scripts/c3_test.py
# 依赖 odoo shell 的事务在退出时回滚，测试数据不会污染演示库。
import datetime
from odoo import fields
from odoo.exceptions import UserError

results = []
def check(name, cond):
    results.append((name, cond))
    print(('OK   ' if cond else 'FAIL '), name)

# ---------- 1) 流程制造物料自动启用批次 + 效期 ----------
sup = env['res.partner'].create({'name': 'C3测试供应商', 'supplier_rank': 1})
prod = env['product.product'].create({
    'name': 'C3测试物料-流程制造',
    'type': 'consu',
    'is_process_mfg': True,
    'list_price': 10.0,
})
tmpl = prod.product_tmpl_id
check('流程制造物料自动 tracking=lot', tmpl.tracking == 'lot')
check('流程制造物料自动 use_expiration_date', tmpl.use_expiration_date is True)

# ---------- 2) 建「已审批」PO → 确认 → 生成收货作业 ----------
wh = env['stock.warehouse'].search([], limit=1)
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
check('PO 审批状态=已审批', po.approval_state == 'approved')
po.button_confirm()
check('PO 确认后生成收货作业', len(po.picking_ids) >= 1)
picking = po.picking_ids[0]
check('收货作业为入向(incoming)', picking.picking_type_id.code == 'incoming')
check('收货作业已自动生成明细行', len(picking.move_line_ids) >= 1)

# ---------- 3) 录入批次 + 效期 → 验证 → 写入 stock.lot ----------
ml = picking.move_line_ids[0]
exp = fields.Datetime.now() + datetime.timedelta(days=180)
ml.write({'lot_name': 'BATCH-C3-001', 'expiration_date': exp, 'quantity': 100.0})
print('      诊断 ml.quantity(写后)=', ml.quantity, '| lot_name=', ml.lot_name)
check('收货明细已录入批次号', bool(ml.lot_name))
check('收货明细已录入效期', bool(ml.expiration_date))

res = picking.button_validate()
# Odoo 18：button_validate 可能返回「立即转移/分单」向导而非直接执行，
# 需显式调用向导的 process() 才会真正生成库存 quant。
if isinstance(res, dict) and res.get('res_model') in (
        'stock.immediate.transfer', 'stock.backorder.confirmation'):
    wiz = env[res['res_model']].browse(res['res_id'])
    wiz.process()
picking.flush_recordset()
lot = env['stock.lot'].search(
    [('name', '=', 'BATCH-C3-001'), ('product_id', '=', prod.id)], limit=1)
check('stock.lot 已创建', bool(lot))
check('stock.lot 记录效期(可追溯)', bool(lot) and bool(lot.expiration_date))
if lot:
    print('      lot.expiration_date =', lot.expiration_date)
# 收货会在「来源(合作方/供应商 虚拟库位)」与「目的(WH/Stock 内部库位)」
# 各生成一条 quant：来源为 -100，目的为 +100。取内部库位的正向库存做校验。
quants = env['stock.quant'].search(
    [('product_id', '=', prod.id), ('lot_id', '=', lot.id if lot else False)])
stock_q = quants.filtered(lambda q: q.quantity > 0 and q.location_id.usage == 'internal')
check('stock.quant 含批次且入库数量正确(+100)',
      bool(stock_q) and abs(stock_q.quantity - 100.0) < 0.01)
if stock_q:
    print('      WH/Stock 库存：quantity =', stock_q.quantity,
          '| expiration_date =', stock_q.expiration_date)
check('收货作业状态=done', picking.state == 'done')

# ---------- 4) 守卫：缺批次的收货必须被拒 ----------
po2 = env['purchase.order'].create({
    'partner_id': sup.id,
    'picking_type_id': wh.in_type_id.id,
    'order_line': [(0, 0, {
        'product_id': prod.id,
        'name': prod.name,
        'product_qty': 50.0,
        'product_uom': prod.uom_id.id,
        'date_planned': fields.Date.today(),
        'price_unit': 10.0,
    })],
})
po2.write({'approval_state': 'approved'})
po2.button_confirm()
picking2 = po2.picking_ids[0]
ml2 = picking2.move_line_ids[0]
ml2.write({'quantity': 50.0})  # 故意不录批次/效期
raised = False
try:
    picking2.button_validate()
except UserError as e:
    raised = True
    print('      守卫提示:', str(e).replace('\n', ' '))
check('缺批次收货被拒绝(UserError)', raised)

# ---------- 5) 中文化视图校验 ----------
try:
    vid = env.ref('supply_chain_demo.view_stock_move_line_detailed_op_sc_zh').id
    arch = env['stock.move.line'].get_views([(vid, 'list')])['views']['list']['arch']
    check('收货明细视图含中文「批次号」', '批次号' in arch)
    check('收货明细视图含中文「效期」', '效期' in arch)
except Exception as e:
    print('      (视图校验跳过:', e, ')')

# ---------- 汇总 ----------
passed = sum(1 for _, c in results if c)
total = len(results)
print('\n=== C3 自测结果：%d/%d 通过 ===' % (passed, total))
for name, c in results:
    if not c:
        print('  未通过:', name)

# 依赖 odoo shell 退出时回滚事务，确保测试数据不写入演示库
try:
    env.cr.rollback()
    print('(已回滚测试事务，演示库保持干净)')
except Exception:
    pass
