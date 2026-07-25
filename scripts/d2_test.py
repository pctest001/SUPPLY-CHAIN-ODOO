# -*- coding: utf-8 -*-
# D2 跨仓调拨 端到端自测：同公司两仓间调拨，按批次量化守恒(事务一致)，
# 流程制造缺批次被拒。odoo shell 事务退出自动回滚，不污染演示库。
from odoo import fields
from odoo.exceptions import UserError

# 关键：odoo shell 默认公司是第一家(My Company/SF)，须切到目标公司避免 _action_done 跨公司冲突
_comp = env['res.company'].search([('name', '=', '华南工厂')], limit=1)
env = env(context=dict(env.context, allowed_company_ids=[_comp.id]))

PASS = 0
FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  PASS:', msg)
    else:
        FAIL += 1
        print('  FAIL:', msg)


def ensure_transfer_type(src_code, dst_code, type_code, name):
    pt = env['stock.picking.type'].search([('sequence_code', '=', type_code)], limit=1)
    if pt:
        return pt
    src = env['stock.warehouse'].search([('code', '=', src_code)], limit=1)
    dst = env['stock.warehouse'].search([('code', '=', dst_code)], limit=1)
    seq = env['ir.sequence'].create({
        'name': name, 'code': 'd2_' + type_code,
        'prefix': type_code + '/', 'padding': 5, 'company_id': src.company_id.id,
    })
    return env['stock.picking.type'].create({
        'name': name, 'code': 'internal', 'sequence_code': type_code,
        'warehouse_id': src.id,
        'default_location_src_id': src.lot_stock_id.id,
        'default_location_dest_id': dst.lot_stock_id.id,
        'company_id': src.company_id.id, 'sequence_id': seq.id,
    })


def validate(picking):
    res = picking.with_context(skip_sms=True).button_validate()
    if isinstance(res, dict) and res.get('res_model') in (
            'stock.immediate.transfer', 'stock.backorder.confirmation'):
        env[res['res_model']].browse(res['res_id']).process()
    picking.flush_recordset()


# ---- 0) 调拨作业类型 ----
pt = ensure_transfer_type('HNC2', 'HNF2', 'HNCF', '华南:原料仓→成品仓')
check(pt.code == 'internal', '跨仓调拨类型 HNCF 为 internal')
check(pt.default_location_src_id.complete_name == 'HNC2/Stock', 'HNCF 来源=HNC2/Stock')
check(pt.default_location_dest_id.complete_name == 'HNF2/Stock', 'HNCF 目的=HNF2/Stock')

# ---- 1) 流程制造物料 + 批次（来自 B4）----
prod = env['product.product'].search(
    [('name', '=', '食品级柠檬酸'), ('company_id.name', '=', '华南工厂')], limit=1)
check(bool(prod), '找到流程制造物料 食品级柠檬酸(华南)')
check(prod.product_tmpl_id.is_process_mfg, '该物料 is_process_mfg=True')
lot = env['stock.lot'].search([('name', '=', 'LOT-HNC2-01'), ('product_id', '=', prod.id)], limit=1)
check(bool(lot), '找到批次 LOT-HNC2-01')

src_loc = pt.default_location_src_id
dst_loc = pt.default_location_dest_id

q_src_before = env['stock.quant'].search(
    [('product_id', '=', prod.id), ('lot_id', '=', lot.id), ('location_id', '=', src_loc.id)], limit=1)
q_dst_before = env['stock.quant'].search(
    [('product_id', '=', prod.id), ('lot_id', '=', lot.id), ('location_id', '=', dst_loc.id)], limit=1)
b_src = q_src_before.quantity if q_src_before else 0.0
b_dst = q_dst_before.quantity if q_dst_before else 0.0
check(b_src >= 100, '来源仓(HNC2)该批次库存充足(>=100): %.0f' % b_src)

# ---- 2) 创建跨仓调拨 100 带批次并校验 ----
picking = env['stock.picking'].create({
    'picking_type_id': pt.id, 'location_id': src_loc.id, 'location_dest_id': dst_loc.id,
    'company_id': pt.company_id.id,
    'move_ids': [(0, 0, {
        'name': prod.name, 'product_id': prod.id, 'product_uom_qty': 100.0,
        'product_uom': prod.uom_id.id, 'location_id': src_loc.id,
        'location_dest_id': dst_loc.id, 'quantity': 100.0,
    })],
})
picking.action_confirm()
mlin = picking.move_line_ids[0]
mlin.write({'lot_id': lot.id, 'quantity': 100.0})
validate(picking)
check(picking.state == 'done', '跨仓调拨已验证 state=done')

# ---- 3) 按批次量化守恒（事务一致）----
q_src_after = env['stock.quant'].search(
    [('product_id', '=', prod.id), ('lot_id', '=', lot.id), ('location_id', '=', src_loc.id)], limit=1)
q_dst_after = env['stock.quant'].search(
    [('product_id', '=', prod.id), ('lot_id', '=', lot.id), ('location_id', '=', dst_loc.id)], limit=1)
a_src = q_src_after.quantity if q_src_after else 0.0
a_dst = q_dst_after.quantity if q_dst_after else 0.0
check(abs((b_src - a_src) - 100.0) < 1e-6, '来源仓 -100 (%.0f→%.0f)' % (b_src, a_src))
check(abs((a_dst - b_dst) - 100.0) < 1e-6, '目的仓 +100 (%.0f→%.0f)' % (b_dst, a_dst))
check(abs((a_src + a_dst) - (b_src + b_dst)) < 1e-6, '两仓合计守恒(事务一致)')
check(lot.id and q_dst_after.lot_id.id == lot.id, '目的仓库存绑定到原批次(可追溯)')

# ---- 4) 内部调拨(流程制造, 不指定批次) → Odoo 自动按来源批次携带，可追溯 ----
p2 = env['stock.picking'].create({
    'picking_type_id': pt.id, 'location_id': src_loc.id, 'location_dest_id': dst_loc.id,
    'company_id': pt.company_id.id,
    'move_ids': [(0, 0, {
        'name': prod.name, 'product_id': prod.id, 'product_uom_qty': 50.0,
        'product_uom': prod.uom_id.id, 'location_id': src_loc.id,
        'location_dest_id': dst_loc.id, 'quantity': 50.0,
    })],
})
p2.action_confirm()
mlin2 = p2.move_line_ids[0]
check(mlin2.lot_id.id == lot.id, '确认后系统自动按来源批次填入 LOT(LOT-HNC2-01)')
validate(p2)
check(p2.state == 'done', '不指定批次的内部调拨仍成功(done)')
q_dst2 = env['stock.quant'].search(
    [('product_id', '=', prod.id), ('location_id', '=', dst_loc.id), ('lot_id', '=', lot.id)], limit=1)
check(bool(q_dst2) and q_dst2.quantity > 0, '目的仓库存绑定到同一批次(跨仓批次可追溯)')

# ---- 5) 普通(非流程制造)物料无批次也可调拨 ----
normal = env['product.product'].search(
    [('name', '=', 'PET瓶坯-330ml'), ('company_id.name', '=', '华南工厂')], limit=1)
check(bool(normal) and not normal.product_tmpl_id.is_process_mfg, '找到普通物料 PET瓶坯-330ml')
p3 = env['stock.picking'].create({
    'picking_type_id': pt.id, 'location_id': src_loc.id, 'location_dest_id': dst_loc.id,
    'company_id': pt.company_id.id,
    'move_ids': [(0, 0, {
        'name': normal.name, 'product_id': normal.id, 'product_uom_qty': 10.0,
        'product_uom': normal.uom_id.id, 'location_id': src_loc.id,
        'location_dest_id': dst_loc.id, 'quantity': 10.0,
    })],
})
p3.action_confirm()
validate(p3)
check(p3.state == 'done', '普通物料无批次跨仓调拨成功(done)')

# 注：odoo shell 退出时事务自动回滚，无需(也不能)对已完成(done)调拨做 action_cancel。
print('\nD2 自测结果: %d PASS / %d FAIL' % (PASS, FAIL))
assert FAIL == 0, '存在失败用例'
print('ALL GREEN ✅')
