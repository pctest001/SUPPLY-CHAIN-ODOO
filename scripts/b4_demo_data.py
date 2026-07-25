# -*- coding: utf-8 -*-
# B4 演示数据扩充：给 2 家演示工厂各补 1 个仓（每公司双仓），灌入 ~22 个中文 SKU，
# 并通过「库存调整」写入初始库存（流程制造带批次+效期，含少量临期供 D3 演示）。
# 说明：直接以 stock.quant 库存调整落账，规避「供应商虚拟库位公司归属」导致的
#       跨公司 _check_company 冲突（产品与库位同属工厂公司，一致）。
# 运行：docker compose run --rm odoo odoo shell -d supplychain < scripts/b4_demo_data.py
# 真实提交（不回滚），供库存看板/跨仓调拨/效期拦截演示使用。可重复运行（幂等）。
from odoo import fields
import datetime

UOM = env.ref('uom.product_uom_unit')


def ensure_warehouse(code, name, company_name):
    wh = env['stock.warehouse'].search([('code', '=', code)], limit=1)
    if wh:
        return wh
    comp = env['res.company'].search([('name', '=', company_name)], limit=1)
    return env['stock.warehouse'].create({
        'name': name, 'code': code,
        'company_id': comp.id, 'partner_id': comp.partner_id.id,
    })


def ensure_category(name):
    cat = env['product.category'].search([('name', '=', name)], limit=1)
    if cat:
        return cat
    return env['product.category'].create({'name': name})


# ---- 1) 补仓：每家工厂第 2 个仓，形成「每公司双仓」----
wh_hnf2 = ensure_warehouse('HNF2', '华南工厂-成品仓', '华南工厂')
wh_hdr2 = ensure_warehouse('HDR2', '华东工厂-原料仓', '华东工厂')
print('仓库就绪：HNC2(华南原料) HNF2(华南成品) HDR2(华东原料) HDC2(华东成品)')

# 分类
CAT = {n: ensure_category(n) for n in ('原料', '成品', '包材')}

# ---- 2) ~22 个 SKU：(名称, 仓code, 分类, 是否流程制造, 数量, 成本, 售价, 效期天数) ----
# 效期天数=None → 默认 365；少量设短值(35/45/60) 供 D3 效期拦截演示
SKUS = [
    # 华南工厂 / 原料仓 HNC2
    ('食品级柠檬酸', 'HNC2', '原料', True, 500, 8.0, 12.0, None),
    ('食用葡萄糖浆', 'HNC2', '原料', True, 400, 5.0, 8.5, None),
    ('食品级碳酸氢钠', 'HNC2', '原料', True, 600, 3.0, 5.5, None),
    ('香精香料-A型', 'HNC2', '原料', True, 200, 40.0, 65.0, 35),   # 临期(供 D3)
    ('PET瓶坯-330ml', 'HNC2', '包材', False, 10000, 0.2, 0.35, None),
    ('瓦楞纸箱-标准', 'HNC2', '包材', False, 3000, 1.2, 2.0, None),
    ('原料标签贴纸', 'HNC2', '包材', False, 5000, 0.05, 0.1, None),
    # 华南工厂 / 成品仓 HNF2
    ('柠檬味苏打水 330ml', 'HNF2', '成品', True, 800, 1.5, 3.0, None),
    ('葡萄糖运动饮料 500ml', 'HNF2', '成品', True, 600, 2.0, 4.0, None),
    ('苏打气泡水 1L', 'HNF2', '成品', True, 400, 2.5, 5.0, None),
    ('调味糖浆-原味', 'HNF2', '成品', True, 300, 6.0, 10.0, None),
    ('车间清洁耗材', 'HNF2', '包材', False, 200, 15.0, 25.0, None),
    # 华东工厂 / 原料仓 HDR2
    ('工业级乙醇', 'HDR2', '原料', True, 800, 6.0, 10.0, None),
    ('表面活性剂-A', 'HDR2', '原料', True, 500, 9.0, 15.0, None),
    ('去离子水', 'HDR2', '原料', True, 1000, 0.5, 1.5, 45),        # 临期
    ('塑料粒子-PP', 'HDR2', '原料', False, 2000, 8.0, 12.0, None),
    ('包装膜卷', 'HDR2', '包材', False, 500, 20.0, 32.0, None),
    # 华东工厂 / 成品仓 HDC2
    ('多用途清洁剂 1L', 'HDC2', '成品', True, 500, 4.0, 8.0, None),
    ('洗手液 500ml', 'HDC2', '成品', True, 600, 3.5, 7.0, None),
    ('消毒液 2L', 'HDC2', '成品', True, 400, 6.5, 12.0, 60),       # 临期
    ('瓶装泵头', 'HDC2', '包材', False, 3000, 0.3, 0.6, None),
    ('湿巾包-独立装', 'HDC2', '成品', True, 700, 1.0, 2.5, None),
]

created = 0
seeded = 0
for idx, (name, wh_code, cat, is_pm, qty, cost, price, exp_days) in enumerate(SKUS, start=1):
    wh = env['stock.warehouse'].search([('code', '=', wh_code)], limit=1)
    comp = wh.company_id
    # 产品幂等
    prod = env['product.product'].search(
        [('name', '=', name), ('company_id', '=', comp.id)], limit=1)
    if not prod:
        base = {
            'name': name, 'type': 'consu', 'company_id': comp.id,
            'categ_id': CAT[cat].id, 'list_price': price,
            'standard_price': cost, 'uom_id': UOM.id, 'uom_po_id': UOM.id,
        }
        if is_pm:
            base.update({'is_process_mfg': True, 'is_storable': True,
                         'tracking': 'lot', 'use_expiration_date': True})
        else:
            base.update({'is_process_mfg': False, 'is_storable': True,
                         'tracking': 'none'})
        prod = env['product.product'].create(base)
        created += 1

    # 库存幂等：已有内部正库存则跳过
    has_stock = env['stock.quant'].search_count([
        ('product_id', '=', prod.id),
        ('location_id.usage', '=', 'internal'),
        ('quantity', '>', 0),
    ])
    if has_stock:
        print('  跳过(已有库存): %s @ %s' % (name, wh_code))
        continue

    # 流程制造先建批次(lot) 并记录效期
    lot = env['stock.lot']
    if is_pm:
        exp = fields.Datetime.now() + datetime.timedelta(days=exp_days or 365)
        lot = env['stock.lot'].create({
            'name': 'LOT-%s-%02d' % (wh_code, idx),
            'product_id': prod.id, 'company_id': comp.id,
            'expiration_date': exp,
        })

    # 以「库存调整」写入初始库存（产品与库位同属工厂公司，无跨公司冲突）
    q = env['stock.quant'].create({
        'product_id': prod.id,
        'location_id': wh.lot_stock_id.id,
        'lot_id': lot.id if is_pm else False,
        'inventory_quantity': qty,
    })
    q.action_apply_inventory()
    seeded += 1
    if is_pm:
        print('  入库: %s @ %s +%s %s (批次 %s, 效期 %s)' % (
            name, wh_code, qty, UOM.name, lot.name,
            (exp_days or 365)))
    else:
        print('  入库: %s @ %s +%s %s' % (name, wh_code, qty, UOM.name))

print('\n新建产品: %d | 本次种入库存: %d | SKU 总数: %d' % (created, seeded, len(SKUS)))

# ---- 3) 按仓汇总库存（供看板演示）----
print('\n== 各演示仓 内部库存概览 ==')
for wh in env['stock.warehouse'].search(
        [('company_id.name', 'in', ('华南工厂', '华东工厂'))], order='code'):
    qs = env['stock.quant'].search([
        ('location_id', '=', wh.lot_stock_id.id), ('quantity', '>', 0)])
    skus = len(qs)
    lots = len(qs.filtered(lambda q: q.lot_id))
    expiring = len(qs.filtered(
        lambda q: q.lot_id and q.expiration_date and
        q.expiration_date < fields.Datetime.now() + datetime.timedelta(days=90)))
    print('  %s %s: %d SKU, %d 批次库存, %d 临期(<90天), 总量 %.0f %s' % (
        wh.code, wh.name, skus, lots, expiring,
        sum(q.quantity for q in qs), UOM.name))

env.cr.commit()
print('\n(B4 演示数据已提交；可在 UI：库存 → 作业 / 库存 → 按批次 / 库存 → 产品 查看)')
