# -*- coding: utf-8 -*-
# 验证 B4 数据持久化 + 关键约束（每公司双仓、SKU 归属、批次+效期、临期项）
print('== 演示仓（每公司双仓）==')
for wh in env['stock.warehouse'].search([('company_id.name', 'in', ('华南工厂', '华东工厂'))], order='code'):
    print('  %s | %s | company=%s' % (wh.code, wh.name, wh.company_id.name))

print('\n== 演示公司下产品数 ==', env['product.product'].search_count(
    [('company_id.name', 'in', ('华南工厂', '华东工厂'))]))

print('\n== 各仓内部库存(SKU数 / 批次库存数 / 临期<90天) ==')
import datetime
from odoo import fields
cut = fields.Datetime.now() + datetime.timedelta(days=90)
for wh in env['stock.warehouse'].search([('company_id.name', 'in', ('华南工厂', '华东工厂'))], order='code'):
    qs = env['stock.quant'].search([('location_id', '=', wh.lot_stock_id.id), ('quantity', '>', 0)])
    lots = qs.filtered(lambda q: q.lot_id)
    exp = lots.filtered(lambda q: q.expiration_date and q.expiration_date < cut)
    print('  %s %s: SKU=%d, 批次库存=%d, 临期=%d, 总量=%.0f' % (
        wh.code, wh.name, len(qs), len(lots), len(exp), sum(q.quantity for q in qs)))

print('\n== 临期批次(lot)明细（供 D3 效期拦截演示）==')
for lot in env['stock.lot'].search([('expiration_date', '<', cut)], order='expiration_date'):
    print('  %s | %s | 效期 %s | 公司 %s' % (
        lot.name, lot.product_id.name, lot.expiration_date.date(),
        lot.company_id.name if lot.company_id else '-'))

print('\n== 流程制造产品数（应含批次追踪）==', env['product.product'].search_count(
    [('is_process_mfg', '=', True), ('company_id.name', 'in', ('华南工厂', '华东工厂'))]))
