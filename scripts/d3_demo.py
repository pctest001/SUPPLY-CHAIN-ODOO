# -*- coding: utf-8 -*-
"""D3 批次/效期拦截 —— 持久化演示。

在华南工厂造一个「已过期批次」+ 一张待验证的出向交付单：
  - 该批次效期早于今日；
  - 出向交付单绑定此过期批次并执行 button_validate，预期被 D3 拦截(UserError)；
  - 拦截不发生真实出库，但「过期批次 / 库存 / 交付单草稿」均 commit 持久化，
    可在 UI（华南工厂 → 库存 → 交货）中手动点「验证」复现拦截。
幂等：重复运行不重复建单。
"""
from odoo import fields
from odoo.exceptions import UserError
from datetime import date

_comp = env['res.company'].search([('name', '=', '华南工厂')], limit=1)
env = env(context=dict(env.context, allowed_company_ids=[_comp.id]))
Product = env['product.product']
Lot = env['stock.lot']
Quant = env['stock.quant']
Picking = env['stock.picking']
PickingType = env['stock.picking.type']

wh = env['stock.warehouse'].search([('company_id', '=', _comp.id)], limit=1)
out_type = PickingType.search(
    [('code', '=', 'outgoing'), ('warehouse_id', '=', wh.id)], limit=1)
src_loc = out_type.default_location_src_id or wh.lot_stock_id
dst_loc = out_type.default_location_dest_id

# 选一个华南工厂的流程制造物料（优先用演示品，否则新建）
prod = Product.search(
    [('name', '=', '食品级柠檬酸'), ('company_id', '=', _comp.id)], limit=1)
if not prod:
    prod = Product.search(
        [('product_tmpl_id.is_process_mfg', '=', True),
         ('company_id', '=', _comp.id)], limit=1)
if not prod:
    prod = Product.create({
        'name': 'D3演示-流程制造物料', 'type': 'consu',
        'is_process_mfg': True, 'company_id': _comp.id,
    })

# 1) 过期批次（幂等）
lot = Lot.search(
    [('name', '=', 'LOT-EXPIRED-DEMO'), ('product_id', '=', prod.id)], limit=1)
if not lot:
    lot = Lot.create({
        'name': 'LOT-EXPIRED-DEMO', 'product_id': prod.id,
        'company_id': _comp.id,
        'expiration_date': fields.Date.to_date('2025-01-01'),
    })
    print('已创建过期批次:', lot.name, '效期', lot.expiration_date)

# 2) 给该批次种入库存（幂等）
quant = Quant.search(
    [('product_id', '=', prod.id), ('location_id', '=', src_loc.id),
     ('lot_id', '=', lot.id)], limit=1)
if not quant:
    Quant.create({'product_id': prod.id, 'location_id': src_loc.id,
                  'lot_id': lot.id, 'inventory_quantity': 30}).action_apply_inventory()
    print('已为该过期批次种入库存 30 @', src_loc.complete_name)

# 3) 出向交付单（绑定过期批次，待验证）——幂等按 origin 去重
pick = Picking.search([('origin', '=', 'D3-DEMO-EXPIRED')], limit=1)
if not pick:
    pick = Picking.create({
        'picking_type_id': out_type.id,
        'location_id': src_loc.id,
        'location_dest_id': dst_loc.id,
        'company_id': _comp.id,
        'origin': 'D3-DEMO-EXPIRED',
    })
    env['stock.move'].create({
        'name': prod.name, 'product_id': prod.id, 'product_uom_qty': 5,
        'product_uom': prod.uom_id.id, 'location_id': src_loc.id,
        'location_dest_id': dst_loc.id, 'picking_id': pick.id,
        'company_id': _comp.id,
    })
    pick.action_confirm()
    pick.move_line_ids[0].write({'lot_id': lot.id, 'quantity': 5})
    print('已创建出向交付单草稿:', pick.name, '(绑定过期批次)')

# 4) 演示拦截：执行验证，预期被 D3 拒绝
print('\n>>> 尝试对过期批次执行 button_validate() ...')
blocked = False
try:
    pick.button_validate()
except UserError as e:
    blocked = True
    print('>>> D3 拦截生效 ✅ UserError:', e.args[0])
if not blocked:
    print('>>> 警告：未触发拦截（异常）')

# 5) 持久化演示数据（批次/库存/交付单草稿），拦截本身不落库
env.cr.commit()
print('\n演示数据已持久化：')
print('  公司   :', _comp.name)
print('  物料   :', prod.display_name)
print('  过期批次:', lot.name, '(效期', fields.Date.to_string(lot.expiration_date), ')')
print('  交付单 :', pick.name, '| 状态', pick.state,
      '| 可在 UI 手动「验证」复现拦截')
