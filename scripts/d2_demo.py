# -*- coding: utf-8 -*-
# D2 跨仓调拨演示：为每家工厂创建「跨仓调拨」内部作业类型（双向），
# 并提交一笔真实跨仓调拨（华南 HNC2 原料仓 → HNF2 成品仓，流程制造物料带批次）。
# 运行：docker compose run --rm odoo odoo shell -d supplychain < scripts/d2_demo.py
# 真实提交（不回滚），可在 UI 库存 → 作业 → 调拨 查看。可重复运行（幂等）。
from odoo import fields

# 关键：odoo shell 默认公司是第一家(My Company/SF)，会导致 _action_done 时
# 自动生成的记录继承 SF 公司，触发跨公司 _check_company 冲突。
# 须将环境公司上下文切到目标公司（华南工厂），所有自动记录才会归属正确公司。
_comp = env['res.company'].search([('name', '=', '华南工厂')], limit=1)
env = env(context=dict(env.context, allowed_company_ids=[_comp.id]))


def ensure_transfer_type(src_code, dst_code, type_code, name):
    """创建/复用「跨仓调拨」内部作业类型（来源仓→目的仓）。"""
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


# ---- 1) 创建 4 个跨仓调拨类型（每公司双向）----
ensure_transfer_type('HNC2', 'HNF2', 'HNCF', '华南:原料仓→成品仓')
ensure_transfer_type('HNF2', 'HNC2', 'HNFC', '华南:成品仓→原料仓')
ensure_transfer_type('HDR2', 'HDC2', 'HDCF', '华东:原料仓→成品仓')
ensure_transfer_type('HDC2', 'HDR2', 'HDFC', '华东:成品仓→原料仓')
print('跨仓调拨作业类型就绪：HNCF/HNFC(华南) HDCF/HDFC(华东)')

# ---- 2) 演示调拨：HNC2 原料仓 → HNF2 成品仓，流程制造物料带批次 ----
pt = env['stock.picking.type'].search([('sequence_code', '=', 'HNCF')], limit=1)
prod = env['product.product'].search(
    [('name', '=', '食品级柠檬酸'), ('company_id.name', '=', '华南工厂')], limit=1)
lot = env['stock.lot'].search(
    [('name', '=', 'LOT-HNC2-01'), ('product_id', '=', prod.id)], limit=1)

# 幂等：若 HNF2/Stock 已有该批次库存(说明调拨已做过)，跳过
already = env['stock.quant'].search_count([
    ('product_id', '=', prod.id), ('lot_id', '=', lot.id),
    ('location_id', '=', pt.default_location_dest_id.id), ('quantity', '>', 0)])
if already:
    print('演示调拨已存在，跳过（HNF2 已有 %s 批次库存）' % lot.name)
else:
    picking = env['stock.picking'].create({
        'picking_type_id': pt.id,
        'location_id': pt.default_location_src_id.id,
        'location_dest_id': pt.default_location_dest_id.id,
        'company_id': pt.company_id.id,
        'move_ids': [(0, 0, {
            'name': prod.name, 'product_id': prod.id,
            'product_uom_qty': 100.0, 'product_uom': prod.uom_id.id,
            'location_id': pt.default_location_src_id.id,
            'location_dest_id': pt.default_location_dest_id.id,
            'quantity': 100.0,
        })],
    })
    picking.action_confirm()
    mlin = picking.move_line_ids[0]
    mlin.write({'lot_id': lot.id, 'quantity': 100.0})
    validate(picking)
    print('调拨单:', picking.name, '| 状态:', picking.state)
    print('  调出 %s @ %s → 调入 %s @ %s' % (
        prod.name, pt.default_location_src_id.complete_name,
        100, pt.default_location_dest_id.complete_name))

# ---- 3) 验证两仓按批次量化（事务一致）----
q_src = env['stock.quant'].search([
    ('product_id', '=', prod.id), ('lot_id', '=', lot.id),
    ('location_id', '=', pt.default_location_src_id.id)], limit=1)
q_dst = env['stock.quant'].search([
    ('product_id', '=', prod.id), ('lot_id', '=', lot.id),
    ('location_id', '=', pt.default_location_dest_id.id)], limit=1)
print('\n按批次量化（%s / %s）：' % (lot.name, prod.name))
print('  %s: %.0f' % (pt.default_location_src_id.complete_name, q_src.quantity if q_src else 0))
print('  %s: %.0f' % (pt.default_location_dest_id.complete_name, q_dst.quantity if q_dst else 0))
print('  两仓合计: %.0f（调拨前后守恒 = 事务一致）' % (
    (q_src.quantity if q_src else 0) + (q_dst.quantity if q_dst else 0)))

env.cr.commit()
print('\n(D2 演示数据已提交；可在 UI：库存 → 作业 → 调拨 查看 HNCF/xxxx)')
